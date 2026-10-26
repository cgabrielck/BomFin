"""Phase 1 paper closed loop — method §6.1 acceptance.

Fake broker only. No network. Not a seal and not a live path.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from backend.trading.alpaca_broker import AlpacaBroker
from backend.trading.engine.order_manager import InMemoryOrderStore, OrderManager
from backend.trading.engine.session_card import build_session_card, scout_env_requested
from backend.trading.engine.worker import TradingWorker
from backend.trading.engine import worker as worker_module
from backend.trading.intents.store import JSONIntentStore
from backend.trading.models import AccountSummary, OrderSide, OrderStatus, Position
from backend.trading.risk.gates import RiskLimits
from backend.trading.safety import audit, kill_switch
from backend.trading.safety.mandate import TradingMandate
from backend.trading.strategies.base import ExitSignal, Signal
from backend.utils.constants import STOCK_UNIVERSE
from backend.utils.provenance import journal_store

ROOT = Path(__file__).resolve().parents[3]
WORKER_PY = ROOT / "backend" / "trading" / "engine" / "worker.py"
HARNESS_PY = ROOT / "backend" / "trading" / "engine" / "harness_realtime.py"

_SOURCE = {
    "type": "filing",
    "ref": "https://example.test/source",
    "asof": "2026-10-26T00:00:00Z",
}
JOURNAL_OK = {"submitted", "filled", "risk_rejected", "canceled", "shadow"}


def _bars(price: float = 100.0, n: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [price] * n,
            "High": [price * 1.01] * n,
            "Low": [price * 0.99] * n,
            "Close": [price] * n,
            "Volume": [1_000_000] * n,
        },
        index=pd.bdate_range(end=pd.Timestamp("2026-10-23"), periods=n),
    )


def _account(positions=None) -> AccountSummary:
    return AccountSummary(
        cash=50_000.0,
        buying_power=50_000.0,
        portfolio_value=100_000.0,
        positions=list(positions or []),
    )


def _buy_signal(ticker, df, fundamental_score, llm_signal, current_positions):
    close = float(df["Close"].iloc[-1])
    return Signal(
        ticker=ticker,
        side="buy",
        strategy_id="stable",
        confidence=0.7,
        reason="phase1 closed loop",
        entry_price=close,
        stop_loss_price=round(close * 0.95, 4),
        take_profit_price=round(close * 1.05, 4),
        avg_win_pct=0.05,
        avg_loss_pct=0.035,
    )


def _function_def(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path.name} missing {name}")


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _first_call_lineno(node: ast.AST, needle: str) -> int:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name == needle:
            return child.lineno
    raise AssertionError(f"no call to {needle}")


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "0")
    monkeypatch.setenv("APCA_PAPER", "true")
    monkeypatch.delenv("SCOUT_ENABLED", raising=False)
    monkeypatch.delenv("WORKER_UNIVERSE_CAP", raising=False)
    monkeypatch.delenv("IGNORE_MARKET_HOURS", raising=False)
    monkeypatch.setattr(kill_switch, "KILL_SWITCH_FILE", tmp_path / "KILL_SWITCH")
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path / "audit")
    (tmp_path / "audit").mkdir()
    monkeypatch.setattr(journal_store, "JOURNAL_PATH", tmp_path / "trade_journal.json")
    monkeypatch.setattr(
        "backend.trading.risk.shared_state.COOLDOWN_FILE",
        tmp_path / "risk_cooldown.json",
    )
    monkeypatch.setattr(
        "backend.trading.risk.shared_state.DAY_START_FILE",
        tmp_path / "risk_day_start.json",
    )
    monkeypatch.setattr(
        "backend.trading.safety.mandate.DAILY_ORDERS_FILE",
        tmp_path / "mandate_daily_orders.json",
    )
    return tmp_path


def _arm(tmp_path, *, universe=None, positions=None, signal=None):
    from unittest.mock import MagicMock

    broker = MagicMock()
    store = InMemoryOrderStore()
    manager = OrderManager(broker=broker, store=store)
    account = _account(positions)
    broker.get_account_summary.return_value = account

    def _submit(order):
        order.status = OrderStatus.SUBMITTED
        order.id = "broker-sell" if order.side == OrderSide.SELL else "broker-buy"
        return order

    broker.submit_order.side_effect = _submit
    worker = TradingWorker(
        broker=broker,
        store=store,
        manager=manager,
        reconciler=MagicMock(),
        strategy_id="stable",
        ticker_universe=universe or ["AAPL"],
        mandate=TradingMandate.permissive(),
        execution_mode="paper",
    )
    worker.intent_store = JSONIntentStore(filepath=str(tmp_path / "intents.json"))
    worker._notify_trade = lambda *a, **k: None
    worker._notify_kill_switch = lambda *a, **k: None
    worker._detect_regime = lambda: {"regime": "neutral", "target_allocation": 0.70, "vix": 15.0}
    worker._fetch_vix = lambda: 15.0
    worker._resolve_cadence = lambda: "intraday"
    worker._fetch_ohlcv = lambda *a, **k: _bars()
    worker._get_fundamental_score_info = lambda t: {"score": 80.0, "source": "cache", "stale": False}
    worker._get_top5_tickers = lambda: []
    worker._get_deep_trade_plan = lambda t: None
    worker._safe_get_account = lambda: account
    worker.strategy.generate_signal = signal or _buy_signal
    worker.strategy.diagnose_entry = lambda *a, **k: "no_setup"
    worker.strategy.check_exit = lambda **kwargs: None
    return worker, broker, account


def _spy_process(worker):
    calls = []
    orig = worker.signal_processor.process_signal

    def _wrapped(signal, **kwargs):
        calls.append(
            {
                "symbol": signal.get("symbol"),
                "side": signal.get("side"),
                "quantity": signal.get("quantity"),
            }
        )
        return orig(signal, **kwargs)

    worker.signal_processor.process_signal = _wrapped
    return calls


def test_risk_defaults_unchanged():
    limits = RiskLimits()
    assert limits.kelly_scale == 0.5
    assert limits.max_order_notional == 10_000.0
    assert limits.max_position_concentration == 0.25
    assert limits.daily_loss_limit_percent == 0.03
    assert limits.max_total_exposure == 0.90


def test_once_cycle_journals_order_and_does_not_double_submit(isolated, monkeypatch):
    """§6.1.1–2: one --once cycle journals an outcome and does not write an active intent."""
    worker, _broker, _account_obj = _arm(isolated)
    calls = _spy_process(worker)
    hb = isolated / "heartbeat.json"

    def _build(*_a, **_k):
        return worker

    monkeypatch.setattr(worker_module, "_build_worker", _build)
    code = worker_module.main(
        ["--once", "--mode", "paper", "--strategy", "stable", "--tickers", "AAPL", "--heartbeat-file", str(hb)]
    )
    assert code == 0
    assert "--allow-live" not in ["--once", "--mode", "paper"]

    rows = journal_store.load_raw_entries()
    statuses = {str(row.get("status")) for row in rows}
    assert statuses & JOURNAL_OK, rows
    buys = [row for row in calls if row["side"] == "buy"]
    assert len(buys) == 1
    assert buys[0]["quantity"] > 0
    assert worker.intent_store.list(status="active") == []
    assert worker.intent_store.list(status="consumed") == []

    card = json.loads(hb.read_text(encoding="utf-8"))["session_card"]
    assert card["seal"] is False
    assert card["claims_beat_spy"] is False
    assert card["scout_enabled"] is False
    assert card["candidate_size"] == 0
    assert card["universe_requested"] == 1
    assert card["fetched_count"] == 1
    assert card["order_statuses"][0]["status"] in JOURNAL_OK
    blob = json.dumps(card).lower()
    assert "beat spy" not in blob
    assert "beats_spy" not in blob


def test_once_quiet_cycle_writes_why_no_trade(isolated, monkeypatch):
    """Silence with a written skip is success."""
    worker, broker, _account_obj = _arm(isolated, signal=lambda **k: None)
    hb = isolated / "heartbeat.json"

    monkeypatch.setattr(worker_module, "_build_worker", lambda *_a, **_k: worker)
    code = worker_module.main(
        ["--once", "--mode", "shadow", "--heartbeat-file", str(hb)]
    )
    assert code == 0
    broker.submit_order.assert_not_called()
    card = json.loads(hb.read_text(encoding="utf-8"))["session_card"]
    assert card["why_no_trade"].get("no_setup") == 1
    assert card["order_statuses"] == []
    assert card["seal"] is False
    assert worker.intent_store.list(status="active") == []


def test_kill_blocks_new_buys_and_still_exits(isolated):
    kill_switch.engage("phase1-test", actor="test", source="phase1")
    position = Position(
        id="p1",
        symbol="AAPL",
        quantity=10.0,
        average_entry_price=90.0,
        current_price=100.0,
    )
    worker, broker, account = _arm(
        isolated,
        universe=["AAPL", "MSFT"],
        positions=[position],
    )
    calls = _spy_process(worker)

    def _exit(**kwargs):
        if kwargs.get("ticker") == "AAPL":
            return ExitSignal(ticker="AAPL", reason="stop_loss", exit_price=100.0)
        return None

    worker.strategy.check_exit = _exit
    worker._run_strategy_signals(account)

    assert calls == []
    broker.submit_order.assert_called_once()
    sent = broker.submit_order.call_args[0][0]
    assert sent.side == OrderSide.SELL
    assert sent.symbol == "AAPL"
    actions = {row.get("action") for row in worker.last_signal_summary}
    assert "BLOCKED" in actions
    assert any(str(a).startswith("EXIT:") for a in actions)
    assert worker.intent_store.list(status="active") == []

    kill_switch.disengage(actor="test", source="phase1")
    events = []
    for path in (isolated / "audit").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    assert any(event.get("event_type") == "kill_switch_resume" for event in events)


def test_judge_failure_skips_buy_and_still_exits(isolated, monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "1")
    position = Position(
        id="p1",
        symbol="AAPL",
        quantity=10.0,
        average_entry_price=90.0,
        current_price=100.0,
    )
    worker, broker, account = _arm(
        isolated,
        universe=["AAPL", "MSFT"],
        positions=[position],
    )
    calls = _spy_process(worker)

    def _client(_setup):
        return "not-json"

    worker.judge_client = _client
    worker.strategy.check_exit = lambda **kwargs: (
        ExitSignal(ticker="AAPL", reason="stop_loss", exit_price=100.0)
        if kwargs.get("ticker") == "AAPL"
        else None
    )
    worker._run_strategy_signals(account)

    assert calls == []
    broker.submit_order.assert_called_once()
    assert broker.submit_order.call_args[0][0].side == OrderSide.SELL
    assert worker.last_skip_counts.get("judge_failure", 0) >= 1
    rows = journal_store.load_raw_entries()
    assert any(row.get("status") == "vetoed" for row in rows)
    assert worker.intent_store.list(status="active") == []


def test_unknown_veto_does_not_block_and_tier_does_not_resize(isolated, monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "1")
    seen = {}

    def _client(setup):
        seen["setup"] = dict(setup)
        return {
            "veto_codes": ["NOT_A_REAL_CODE"],
            "conviction_tier": "low",
            "sources": [_SOURCE],
            "notes": "ignore me",
        }

    worker, _broker, account = _arm(isolated)
    worker.judge_client = _client
    calls = _spy_process(worker)
    worker._run_strategy_signals(account)
    assert len(calls) == 1
    assert calls[0]["quantity"] > 0
    assert "quantity" not in seen["setup"]
    assert "notional" not in seen["setup"]
    assert "judge_veto" not in worker.last_skip_counts


def test_judge_call_site_is_immediately_before_buy_submit_and_not_on_h1():
    run = _function_def(WORKER_PY, "_run_strategy_signals")
    sell = _function_def(WORKER_PY, "_submit_sell")
    judge_ln = _first_call_lineno(run, "evaluate_entry")
    submit_ln = _first_call_lineno(run, "process_signal")
    assert judge_ln < submit_ln
    between = "\n".join(WORKER_PY.read_text(encoding="utf-8").splitlines()[judge_ln:submit_ln - 1])
    assert "qty =" not in between
    assert "shares_to_buy" not in between
    body = ast.get_source_segment(WORKER_PY.read_text(encoding="utf-8"), run) or ""
    assert "upsert_active_intent" not in body
    assert "parse_intent" not in body
    assert "evaluate_entry" not in _call_names(sell)
    banned = {
        "openai",
        "anthropic",
        "httpx",
        "requests",
        "backend.lab.advisory_debate",
        "backend.trading.advisory",
        "backend.trading.advisory.judge",
    }
    assert _imported(HARNESS_PY).isdisjoint(banned)
    sell_src = ast.get_source_segment(WORKER_PY.read_text(encoding="utf-8"), sell) or ""
    assert "advisory" not in sell_src
    assert "openai" not in sell_src


def test_live_stays_off_and_paper_uses_paper_endpoint(isolated, monkeypatch):
    from unittest.mock import MagicMock, patch

    worker, _broker, _account_obj = _arm(isolated, signal=lambda **k: None)
    seen = {}

    def _build(_strategy, _tickers, execution_mode="paper"):
        seen["mode"] = execution_mode
        return worker

    monkeypatch.setattr(worker_module, "_build_worker", _build)
    argv = ["--once", "--mode", "paper", "--heartbeat-file", str(isolated / "hb.json")]
    assert "--allow-live" not in argv
    assert worker_module.main(argv) == 0
    assert seen["mode"] == "paper"

    monkeypatch.setattr(worker_module, "_build_worker", lambda *a, **k: worker)
    assert worker_module.main(["--once", "--heartbeat-file", str(isolated / "hb2.json")]) == 0
    # default --mode is shadow; the patched builder records the kw from main
    # only when we wrap it. Re-read argparse default via a dedicated call.
    recorded = {}

    def _build_default(_strategy, _tickers, execution_mode="paper"):
        recorded["mode"] = execution_mode
        return worker

    monkeypatch.setattr(worker_module, "_build_worker", _build_default)
    assert worker_module.main(["--once", "--heartbeat-file", str(isolated / "hb3.json")]) == 0
    assert recorded["mode"] == "shadow"

    with pytest.raises(SystemExit):
        worker_module.main(["--once", "--mode", "live"])

    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APCA_PAPER", "true")
    broker = AlpacaBroker()
    assert broker.is_paper is True
    fake = MagicMock()
    fake._retry_codes = [429, 504]
    fake.get_account.return_value.trading_blocked = False
    with patch("backend.trading.alpaca_broker.TradingClient", return_value=fake) as client:
        broker._ensure_connected()
    assert client.call_args.kwargs["paper"] is True


def test_session_card_full_book_ops_cap_and_not_a_seal(monkeypatch):
    core = [row["ticker"] for row in STOCK_UNIVERSE]
    monkeypatch.delenv("WORKER_UNIVERSE_CAP", raising=False)
    monkeypatch.delenv("SCOUT_ENABLED", raising=False)
    full = build_session_card(
        universe_source="stock_universe",
        universe_requested=core,
        cap=len(core),
        cap_env=None,
        fetched=core,
        skip_counts={"no_setup": 3},
        order_statuses=[],
        execution_mode="paper",
        invested_pct=0.0,
        performance_report={
            "pnl": {"total_return_pct": 1.0},
            "benchmark": {"spy_return_pct": 8.0, "beats_spy_net": True},
            "beats_spy_net": True,
        },
    )
    assert full["core_universe_size"] == len(STOCK_UNIVERSE)
    assert 70 <= full["core_universe_size"] <= 80
    assert full["cap_label"] == "full"
    assert full["fetched_count"] == len(core)
    assert full["candidate_size"] == 0
    assert full["scout_enabled"] is False
    assert scout_env_requested() is False
    assert full["why_no_trade"]["no_setup"] == 3
    assert full["paper_vs_spy"]["label"] == "paper vs SPY"
    assert full["paper_vs_spy"]["seal"] is False
    assert full["seal"] is False
    blob = json.dumps(full).lower()
    assert "beat spy" not in blob
    assert "beats_spy" not in blob

    capped = build_session_card(
        universe_source="stock_universe",
        universe_requested=core,
        cap=12,
        cap_env="12",
        fetched=core[:12],
        skip_counts={"universe_capped": len(core) - 12},
        order_statuses=[{"symbol": "AAPL", "side": "buy", "status": "submitted"}],
        execution_mode="shadow",
    )
    assert capped["cap_label"] == "ops cap"
    assert "ops cap" in capped["note"]
    assert capped["core_universe_size"] == len(STOCK_UNIVERSE)
    assert capped["fetched_count"] == 12

    monkeypatch.setenv("SCOUT_ENABLED", "1")
    ignored = build_session_card(
        universe_source="stock_universe",
        universe_requested=core,
        cap=len(core),
        cap_env="",
        fetched=core,
        skip_counts={},
        order_statuses=[],
        execution_mode="shadow",
    )
    assert ignored["scout_enabled"] is False
    assert ignored["candidate_size"] == 0
    assert ignored["scout_env_requested"] is True


def test_import_fallback_is_a_data_fault(monkeypatch):
    import backend.utils.constants as constants
    from unittest.mock import MagicMock

    monkeypatch.delattr(constants, "STOCK_UNIVERSE")
    worker = TradingWorker(
        broker=MagicMock(),
        store=InMemoryOrderStore(),
        manager=OrderManager(broker=MagicMock(), store=InMemoryOrderStore()),
        reconciler=MagicMock(),
        strategy_id="stable",
        ticker_universe=None,
        mandate=TradingMandate.permissive(),
        execution_mode="shadow",
    )
    assert worker.universe_source == "import_fallback"
    assert worker.ticker_universe == ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    card = build_session_card(
        universe_source=worker.universe_source,
        universe_requested=worker.ticker_universe,
        cap=5,
        cap_env=None,
        fetched=worker.ticker_universe,
        skip_counts={},
        order_statuses=[],
        execution_mode="shadow",
    )
    assert card["data_fault"] == "universe_import_fallback"
    assert "data fault" in card["note"]
    assert card["claims_beat_spy"] is False


def test_market_hours_flag_stays_off_and_scout_package_is_absent(monkeypatch):
    monkeypatch.delenv("IGNORE_MARKET_HOURS", raising=False)
    sunday = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)
    assert TradingWorker._is_market_hours(None, sunday) is False
    assert not list((ROOT / "backend" / "trading").glob("scout*.py"))
    assert not (ROOT / "backend" / "trading" / "scout").exists()
    src = WORKER_PY.read_text(encoding="utf-8")
    assert "scout_candidate" not in src
    assert "benzinga" not in src.lower()
