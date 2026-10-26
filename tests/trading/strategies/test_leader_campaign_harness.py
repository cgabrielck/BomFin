"""leader_campaign experimental harness. No network, no live orders.

Synthetic bars prove each setup can emit VALID. The 74-name E-STAIR-0
census (VALID = 0) is not re-run and is not treated as alpha.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.api.app import DEFAULT_AI_MODE
from backend.trading.engine.order_manager import InMemoryOrderStore, OrderManager
from backend.trading.engine.worker import TradingWorker
from backend.trading.models import AccountSummary, OrderStatus
from backend.trading.risk.gates import RiskLimits
from backend.trading.safety import audit
from backend.trading.safety.mandate import TradingMandate
from backend.trading.strategies.base import Signal
from backend.trading.strategies.experimental import experimental_strategies_enabled
from backend.trading.strategies.experimental.leader_campaign import (
    FUND_MIN,
    DisabledLeaderCampaign,
    LeaderCampaignStrategy,
    band_verdict,
    coerce_fund_score,
    evaluate_latest,
    fund_gate,
    prepare_symbol,
    product_path_enabled,
    stop_too_wide,
)
from backend.trading.strategies.registry import (
    KNOWN_STRATEGIES,
    STRATEGY_REGISTRY,
    get_strategy,
    strategy_choices,
)
from backend.trading.strategies.skip_codes import label
from backend.utils.provenance import journal_store
from backend.utils.us_equity_calendar import is_us_equity_trading_day

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "backend/trading/strategies/experimental/leader_campaign.py"


def _sessions(n: int, start: str = "2021-06-01") -> pd.DatetimeIndex:
    days = []
    cursor = pd.Timestamp(start)
    while len(days) < n:
        if is_us_equity_trading_day(cursor):
            days.append(cursor.normalize())
        cursor += pd.Timedelta(days=1)
    return pd.DatetimeIndex(days)


def _frame(close, high, low, open_, volume, index) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": np.asarray(open_, dtype=float),
            "High": np.asarray(high, dtype=float),
            "Low": np.asarray(low, dtype=float),
            "Close": np.asarray(close, dtype=float),
            "Volume": np.asarray(volume, dtype=float),
        },
        index=index,
    )


def _smooth_book(n: int = 420, *, span: float = 0.01):
    index = _sessions(n)
    i = np.arange(n, dtype=float)
    stock_close = 40.0 + i * 0.25
    stock_high = stock_close * (1.0 + span)
    stock_low = stock_close * (1.0 - span)
    stock_open = stock_close * 0.999
    stock_vol = np.full(n, 1_000_000.0)
    spy_close = 100.0 + i * 0.02
    spy_high = spy_close * 1.005
    spy_low = spy_close * 0.995
    spy_open = spy_close * 0.999
    spy_vol = np.full(n, 1_000_000.0)
    return (
        index,
        stock_close,
        stock_high,
        stock_low,
        stock_open,
        stock_vol,
        spy_close,
        spy_high,
        spy_low,
        spy_open,
        spy_vol,
    )


def _paint_pivot(stock_high, stock_low, stock_open, stock_close, stock_vol, *, extended: bool = False):
    signal = len(stock_close) - 1
    peak = float(stock_close[signal - 41])
    prior = slice(signal - 40, signal - 5)
    handle = slice(signal - 5, signal)
    stock_high[prior] = peak
    stock_low[prior] = peak * 0.92
    stock_open[prior] = peak * 0.98
    stock_close[prior] = peak * 0.97
    stock_vol[prior] = 2_000_000.0
    stock_high[handle] = peak * 0.995
    stock_low[handle] = peak * 0.99
    stock_open[handle] = peak * 0.993
    stock_close[handle] = peak * 0.993
    stock_vol[handle] = 500_000.0
    multiple = 1.08 if extended else 1.01
    close = peak * multiple
    stock_close[signal] = close
    stock_high[signal] = close * 1.002
    stock_low[signal] = close * 0.998
    stock_open[signal] = close * 1.002
    stock_vol[signal] = 5_000_000.0
    return peak


def _pivot_books(*, extended: bool = False):
    parts = _smooth_book()
    index = parts[0]
    stock = [np.array(part, dtype=float, copy=True) for part in parts[1:6]]
    spy = [np.array(part, dtype=float, copy=True) for part in parts[6:]]
    _paint_pivot(*stock, extended=extended)
    return _frame(*stock, index), _frame(*spy, index)


def _play(monkeypatch) -> LeaderCampaignStrategy:
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    strat = LeaderCampaignStrategy()
    return strat


def _signal(monkeypatch, stock, spy, fund):
    strat = _play(monkeypatch)
    strat.set_spy_frame(spy)
    sig = strat.generate_signal("AAA", stock, fund, None, [])
    code = strat.diagnose_entry("AAA", stock, fund, None, [])
    return sig, code


def test_product_defaults_and_flag_off(monkeypatch):
    monkeypatch.delenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", raising=False)
    assert experimental_strategies_enabled() is False
    assert product_path_enabled() is False
    assert "leader_campaign" not in KNOWN_STRATEGIES
    assert "leader_campaign" not in STRATEGY_REGISTRY
    assert "leader_campaign" not in strategy_choices()
    assert DEFAULT_AI_MODE["strategy"] == "breakout"
    blocked = get_strategy("leader_campaign")
    assert isinstance(blocked, DisabledLeaderCampaign)
    assert blocked.strategy_id == "leader_campaign"
    assert blocked.strategy_id != "adaptive"
    assert get_strategy("does_not_exist").strategy_id == "adaptive"
    assert blocked.generate_signal("AAA", None, None, None, []) is None
    assert blocked.diagnose_entry("AAA", None, 50.0, None, []) == "experimental_disabled"
    limits = RiskLimits()
    assert limits.kelly_scale == 0.5
    assert limits.max_order_notional == 10_000.0
    assert limits.daily_loss_limit_percent == 0.03
    assert limits.max_total_exposure == 0.90
    assert limits.max_position_concentration == 0.25
    assert limits.max_open_positions == 10


def test_flag_on_registers_for_cli_only_and_still_does_not_submit(monkeypatch):
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    assert experimental_strategies_enabled() is True
    assert product_path_enabled() is False
    assert "leader_campaign" not in KNOWN_STRATEGIES
    assert "leader_campaign" not in STRATEGY_REGISTRY
    assert strategy_choices()[-1] == "leader_campaign"
    loaded = get_strategy("leader_campaign", min_fund=1)
    assert isinstance(loaded, LeaderCampaignStrategy)
    assert FUND_MIN == 50.0
    assert loaded.strategy_id == "leader_campaign"
    assert get_strategy("").strategy_id == "adaptive"


def test_ai_mode_and_desk_start_reject_the_id(monkeypatch):
    monkeypatch.setenv("APCA_PAPER", "true")
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    html = (ROOT / "web/static/index.html").read_text(encoding="utf-8")
    assert 'const modes = ["adaptive","trend","breakout","research_list","defensive_gld"]' in html
    assert "leader_campaign" not in html
    from backend.api.worker_ctl import start

    with pytest.raises(ValueError, match="Unknown strategy"):
        start("leader_campaign")


def test_module_does_not_import_order_router_or_backtest():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    banned = {"OrderManager", "place_desk_order", "AlpacaBroker", "submit_order"}
    modules = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                names.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
                names.add(node.module.split(".")[-1])
            for alias in node.names:
                names.add(alias.name)
    assert not (banned & names)
    assert not any("backtesting" in item or "alpaca" in item.lower() for item in modules)
    assert not any(item.endswith("order_manager") for item in modules)


def test_fund_gate_does_not_invent_a_score():
    assert fund_gate(None) == "fund_missing"
    assert fund_gate(float("nan")) == "fund_missing"
    assert fund_gate(49.9) == "fund_below_min"
    assert fund_gate(50.0) == "valid"
    assert coerce_fund_score({"source": "missing", "score": 50.0, "raw_score": None}) is None
    assert coerce_fund_score({"source": "default", "score": 55.0, "raw_score": None}) is None
    assert coerce_fund_score({"source": "last_scan", "score": 50.0, "raw_score": 50.0}) == 50.0
    assert coerce_fund_score({"source": "last_scan", "score": 60.0, "raw_score": None}) is None
    assert label("fund_missing", "zh") == "沒有基本面分數（不填 50／55）"
    assert band_verdict(0) == "stop_sparse"


def test_stop_width_is_strict():
    assert stop_too_wide(100, 96, 4, pct_cap=0.08, atr_mult=1.0) is False
    assert stop_too_wide(100, 95.9, 4, pct_cap=0.08, atr_mult=1.0) is True
    assert stop_too_wide(100, 90, 10, pct_cap=None, atr_mult=1.5) is False
    assert stop_too_wide(100, 84.9, 10, pct_cap=None, atr_mult=1.5) is True


def test_each_setup_can_valid_on_synthetic_bars(monkeypatch):
    stock, spy = _pivot_books()
    sig, code = _signal(monkeypatch, stock, spy, 60.0)
    assert code is None
    assert sig is not None
    assert sig.strategy_id == "leader_campaign"
    assert sig.meta["setup"] == "pivot_break"
    assert sig.meta["alpha_claimed"] is False
    assert sig.stop_loss_price < sig.entry_price
    assert sig.take_profit_price is None

    parts = _smooth_book()
    index = parts[0]
    stock_px = [np.array(part, dtype=float, copy=True) for part in parts[1:6]]
    spy_px = [np.array(part, dtype=float, copy=True) for part in parts[6:]]
    stock_px[4][-1] = 2_000_000.0
    pocket_stock = _frame(*stock_px, index)
    pocket_spy = _frame(*spy_px, index)
    pocket, pocket_code = _signal(monkeypatch, pocket_stock, pocket_spy, 60.0)
    label, notes = evaluate_latest(pocket_stock, pocket_spy, 60.0)
    assert label == "pocket_pivot", (label, notes.get("statuses"))
    assert pocket_code is None
    assert pocket is not None and pocket.meta["setup"] == "pocket_pivot"

    wide = _smooth_book(span=0.04)
    windex = wide[0]
    wstock = [np.array(part, dtype=float, copy=True) for part in wide[1:6]]
    wspy = [np.array(part, dtype=float, copy=True) for part in wide[6:]]
    draft = _frame(*wstock, windex)
    prep = prepare_symbol(draft)
    assert prep is not None
    wstock[2][-1] = float(prep.sma20[-1])
    pull_stock = _frame(*wstock, windex)
    pull_spy = _frame(*wspy, windex)
    pull_label, pull_notes = evaluate_latest(pull_stock, pull_spy, 70.0)
    assert pull_label == "ma_pullback", (pull_label, pull_notes.get("statuses"))
    pull, pull_code = _signal(monkeypatch, pull_stock, pull_spy, 70.0)
    assert pull_code is None
    assert pull is not None and pull.meta["setup"] == "ma_pullback"

    n = 260
    index = _sessions(n)
    close = np.full(n, 50.0)
    high = close * 1.03
    low = close * 0.97
    open_ = close.copy()
    volume = np.full(n, 1_000_000.0)
    close[-1] = 56.5
    open_[-1] = 56.0
    high[-1] = 57.0
    low[-1] = 55.8
    volume[-1] = 3_000_000.0
    gap_stock = _frame(close, high, low, open_, volume, index)
    spy_close = 100.0 + np.arange(n) * 0.05
    gap_spy = _frame(spy_close, spy_close * 1.01, spy_close * 0.99, spy_close, np.full(n, 1e6), index)
    gap, gap_code = _signal(monkeypatch, gap_stock, gap_spy, 60.0)
    assert gap_code is None
    assert gap is not None
    assert gap.meta["setup"] == "gap_up"
    assert gap.meta["catalyst"] == "catalyst_unconfirmed"


def test_skip_codes_fire_and_missing_score_is_not_valid(monkeypatch):
    stock, spy = _pivot_books()
    missing, missing_code = _signal(monkeypatch, stock, spy, None)
    assert missing is None
    assert missing_code == "fund_missing"

    ext_stock, ext_spy = _pivot_books(extended=True)
    extended, extended_code = _signal(monkeypatch, ext_stock, ext_spy, 60.0)
    ext_label, ext_notes = evaluate_latest(ext_stock, ext_spy, 60.0)
    assert extended is None
    # The pivot itself is extended. The same bar also completes a wide gap,
    # and stop_too_wide outranks extended for the one daily label.
    assert ext_notes["statuses"]["pivot_break"] == "extended"
    assert ext_label == "stop_too_wide"
    assert extended_code == "stop_too_wide"

    crashed = spy.copy()
    crashed.iloc[-1, crashed.columns.get_loc("Close")] = 10.0
    crashed.iloc[-1, crashed.columns.get_loc("High")] = 11.0
    crashed.iloc[-1, crashed.columns.get_loc("Low")] = 9.0
    blocked, blocked_code = _signal(monkeypatch, stock, crashed, 60.0)
    assert blocked is None
    assert blocked_code == "regime_block"

    pressured = spy.copy()
    signal = len(pressured) - 1
    for offset in (6, 8, 10, 12, 14):
        idx = signal - offset
        prev = float(pressured["Close"].iloc[idx - 1])
        pressured.iloc[idx, pressured.columns.get_loc("Close")] = prev * 0.995
        pressured.iloc[idx, pressured.columns.get_loc("High")] = prev * 0.998
        pressured.iloc[idx, pressured.columns.get_loc("Low")] = prev * 0.993
        pressured.iloc[idx, pressured.columns.get_loc("Volume")] = float(pressured["Volume"].iloc[idx - 1]) * 2 + 1
    pressed, pressed_code = _signal(monkeypatch, stock, pressured, 60.0)
    assert pressed is None
    assert pressed_code == "market_pressure"
    # A filled score must not hide the market block, and a missing score must not either.
    hidden, hidden_code = _signal(monkeypatch, stock, pressured, None)
    assert hidden is None
    assert hidden_code == "market_pressure"

    no_spy, no_spy_code = _signal(monkeypatch, stock, None, 60.0)
    assert no_spy is None
    assert no_spy_code == "market_unavailable"

    n = 260
    index = _sessions(n)
    close = np.linspace(40.0, 48.0, n)
    high = close * 1.01
    low = close * 0.99
    open_ = close.copy()
    volume = np.full(n, 1_000_000.0)
    prev = float(close[-2])
    close[-1] = prev * 1.04
    open_[-1] = prev * 1.01
    high[-1] = float(close[-1])
    low[-1] = prev
    volume[-1] = 4_000_000.0
    small = _frame(close, high, low, open_, volume, index)
    spy_close = 100.0 + np.arange(n) * 0.02
    small_spy = _frame(spy_close, spy_close * 1.01, spy_close * 0.99, spy_close, np.full(n, 1e6), index)
    small_sig, small_code = _signal(monkeypatch, small, small_spy, 60.0)
    assert small_sig is None
    assert small_code == "no_setup"

    short_index = _sessions(20)
    short = _frame(
        np.full(20, 50.0),
        np.full(20, 51.0),
        np.full(20, 49.0),
        np.full(20, 50.0),
        np.full(20, 1e6),
        short_index,
    )
    short_spy = _frame(
        np.full(20, 100.0),
        np.full(20, 101.0),
        np.full(20, 99.0),
        np.full(20, 100.0),
        np.full(20, 1e6),
        short_index,
    )
    early, early_code = _signal(monkeypatch, short, short_spy, 60.0)
    assert early is None
    assert early_code == "history_short"

    held, held_code = _signal(monkeypatch, stock, spy, 60.0)
    strat = _play(monkeypatch)
    strat.set_spy_frame(spy)
    assert strat.generate_signal("AAA", stock, 60.0, None, [{"symbol": "AAA"}]) is None
    assert strat.diagnose_entry("AAA", stock, 60.0, None, [{"symbol": "AAA"}]) == "already_held"
    del held, held_code


def test_flag_off_same_bars_do_not_emit_a_signal(monkeypatch):
    monkeypatch.delenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", raising=False)
    stock, spy = _pivot_books()
    strat = LeaderCampaignStrategy()
    strat.set_spy_frame(spy)
    assert strat.generate_signal("AAA", stock, 60.0, None, []) is None
    assert strat.diagnose_entry("AAA", stock, 60.0, None, []) == "experimental_disabled"
    # The rule function still describes the bar. It is not a submit path.
    assert evaluate_latest(stock, spy, 60.0)[0] == "pivot_break"


def test_exits_follow_the_written_rules():
    strat = LeaderCampaignStrategy()
    index = _sessions(60)
    close = np.linspace(100, 130, 60)
    df = _frame(close, close * 1.01, close * 0.99, close * 0.999, np.full(60, 1e6), index)
    strat.bind_position_meta({"setup": "pivot_break", "pivot": 120.0, "r_unit": 4.0, "max_r": 0.0})
    stopped = strat.check_exit("AAA", 110.0, 100.0, df, 105.0, None)
    assert stopped is not None and stopped.reason == "stop_loss"

    strat.bind_position_meta({
        "setup": "pivot_break",
        "pivot": 140.0,
        "r_unit": 4.0,
        "max_r": 0.0,
        "last_bar_day": index[-1].date().isoformat(),
    })
    lost = strat.check_exit("AAA", 130.0, 125.0, df, 100.0, None)
    assert lost is not None and lost.reason == "pivot_lost"

    gap_index = _sessions(10)
    flat = np.full(10, 50.0)
    gap_df = _frame(flat, flat * 1.01, flat * 0.99, flat, np.full(10, 1e6), gap_index)
    strat.bind_position_meta({
        "setup": "gap_up",
        "r_unit": 2.0,
        "max_r": 0.0,
        "bars_held": 4,
        "last_bar_day": "2020-01-02",
    })
    timed = strat.check_exit("AAA", 50.0, 50.5, gap_df, 40.0, None)
    assert timed is not None and timed.reason == "time_stop"
    assert strat._bound_meta["bars_held"] == 5


def _account() -> AccountSummary:
    return AccountSummary(
        cash=100_000.0,
        buying_power=100_000.0,
        portfolio_value=100_000.0,
        positions=[],
    )


def _short_bars(n: int = 40) -> pd.DataFrame:
    index = _sessions(n)
    close = np.linspace(20.0, 30.0, n)
    return _frame(close, close * 1.01, close * 0.99, close, np.full(n, 1e6), index)


def _run_cycle(worker, account, df, fund):
    with patch.object(worker, "_detect_regime", return_value={"regime": "bull", "target_allocation": 0.90}), \
         patch.object(worker, "_fetch_vix", return_value=None), \
         patch.object(worker, "_fetch_ohlcv", return_value=df), \
         patch.object(worker, "_get_fundamental_score_info", return_value=fund), \
         patch.object(worker, "_get_top5_tickers", return_value=[]), \
         patch.object(worker, "_resolve_cadence", return_value="intraday"), \
         patch.object(worker, "_safe_get_account", return_value=account):
        worker._run_strategy_signals(account)


def test_flag_off_worker_does_not_trade(monkeypatch):
    monkeypatch.delenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", raising=False)
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    worker = TradingWorker(
        broker=MagicMock(),
        store=MagicMock(),
        manager=MagicMock(),
        reconciler=MagicMock(),
        strategy_id="leader_campaign",
        ticker_universe=["AAA"],
        mandate=TradingMandate(),
    )
    worker.store.get_recent_orders.return_value = []
    worker.signal_processor.process_signal = MagicMock()
    _run_cycle(
        worker,
        _account(),
        _short_bars(),
        {"score": 80.0, "raw_score": 80.0, "source": "last_scan", "stale": False},
    )
    worker.signal_processor.process_signal.assert_not_called()
    assert worker.last_skip_counts.get("experimental_disabled", 0) >= 1
    assert worker.strategy.strategy_id == "leader_campaign"


def test_flag_on_empty_cycle_skips_without_double_submit(monkeypatch):
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    monkeypatch.setattr("backend.trading.safety.kill_switch.worker_kill_blocks_side", lambda side: False)
    periods = []

    def _fetch(ticker, period="1y"):
        periods.append((ticker, period))
        return _short_bars(40 if ticker != "SPY" else 40)

    worker = TradingWorker(
        broker=MagicMock(),
        store=MagicMock(),
        manager=MagicMock(),
        reconciler=MagicMock(),
        strategy_id="leader_campaign",
        ticker_universe=["AAA"],
        mandate=TradingMandate(),
    )
    worker.store.get_recent_orders.return_value = []
    calls = []
    worker.signal_processor.process_signal = lambda *args, **kwargs: calls.append(1)
    with patch.object(worker, "_detect_regime", return_value={"regime": "bull", "target_allocation": 0.90}), \
         patch.object(worker, "_fetch_vix", return_value=None), \
         patch.object(worker, "_fetch_ohlcv", side_effect=_fetch), \
         patch.object(
             worker,
             "_get_fundamental_score_info",
             return_value={"score": 80.0, "raw_score": 80.0, "source": "last_scan", "stale": False},
         ), \
         patch.object(worker, "_get_top5_tickers", return_value=[]), \
         patch.object(worker, "_resolve_cadence", return_value="intraday"), \
         patch.object(worker, "_safe_get_account", return_value=_account()):
        worker._run_strategy_signals(_account())
    worker.intent_store = MagicMock()
    worker.intent_store.list.return_value = []
    worker._consume_intents(_account())
    assert calls == []
    assert worker.last_skip_counts.get("history_short", 0) >= 1
    assert ("AAA", "2y") in periods
    assert ("AAA", "1y") not in periods


def test_breakout_fetch_period_stays_one_year(monkeypatch):
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    periods = []

    def _fetch(ticker, period="1y"):
        periods.append((ticker, period))
        return _short_bars()

    worker = TradingWorker(
        broker=MagicMock(),
        store=MagicMock(),
        manager=MagicMock(),
        reconciler=MagicMock(),
        strategy_id="breakout",
        ticker_universe=["AAA"],
        mandate=TradingMandate(),
    )
    worker.store.get_recent_orders.return_value = []
    with patch.object(worker, "_detect_regime", return_value={"regime": "bull", "target_allocation": 0.90}), \
         patch.object(worker, "_fetch_vix", return_value=None), \
         patch.object(worker, "_fetch_ohlcv", side_effect=_fetch), \
         patch.object(
             worker,
             "_get_fundamental_score_info",
             return_value={"score": 80.0, "raw_score": 80.0, "source": "last_scan", "stale": False},
         ), \
         patch.object(worker, "_get_top5_tickers", return_value=[]), \
         patch.object(worker, "_resolve_cadence", return_value="intraday"):
        worker._run_strategy_signals(_account())
    assert ("AAA", "1y") in periods
    assert ("AAA", "2y") not in periods


def test_worker_does_not_pass_a_filled_fifty(monkeypatch):
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    worker = TradingWorker(
        broker=MagicMock(),
        store=MagicMock(),
        manager=MagicMock(),
        reconciler=MagicMock(),
        strategy_id="leader_campaign",
        ticker_universe=["AAA"],
        mandate=TradingMandate(),
    )
    worker.store.get_recent_orders.return_value = []
    seen = {}

    def _gen(ticker, df, fundamental_score, llm_signal, current_positions):
        seen["score"] = fundamental_score
        return None

    worker.strategy.generate_signal = _gen
    worker.strategy.diagnose_entry = lambda *args, **kwargs: "no_setup"
    _run_cycle(
        worker,
        _account(),
        _short_bars(),
        {"score": 50.0, "raw_score": None, "source": "missing", "stale": False},
    )
    assert seen["score"] is None
    assert RiskLimits().kelly_scale == 0.5


def test_forced_signal_reaches_process_signal_once_and_keeps_structural_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    monkeypatch.setattr("backend.trading.safety.kill_switch.worker_kill_blocks_side", lambda side: False)
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path / "audit")
    (tmp_path / "audit").mkdir()
    monkeypatch.setattr(journal_store, "JOURNAL_PATH", tmp_path / "trade_journal.json")
    broker = MagicMock()
    store = InMemoryOrderStore()
    manager = OrderManager(broker=broker, store=store)
    worker = TradingWorker(
        broker=broker,
        store=store,
        manager=manager,
        reconciler=MagicMock(),
        strategy_id="leader_campaign",
        ticker_universe=["AAA"],
        mandate=TradingMandate(),
        execution_mode="paper",
    )
    account = _account()
    broker.get_account_summary.return_value = account

    def _submit(order):
        order.status = OrderStatus.SUBMITTED
        store.save_order(order)
        return order

    broker.submit_order.side_effect = _submit

    def _buy(ticker, df, fundamental_score, llm_signal, current_positions):
        del fundamental_score, llm_signal, current_positions
        close = float(df["Close"].iloc[-1])
        return Signal(
            ticker=ticker,
            side="buy",
            strategy_id="leader_campaign",
            confidence=0.5,
            reason="wiring fixture",
            entry_price=close,
            stop_loss_price=round(close * 0.96, 4),
            take_profit_price=None,
            avg_win_pct=0.18,
            avg_loss_pct=0.07,
            meta={"setup": "pivot_break", "pivot": round(close * 0.99, 4), "r_unit": close * 0.04},
        )

    worker.strategy.generate_signal = _buy
    worker.strategy.diagnose_entry = lambda *args, **kwargs: None
    df = _short_bars()
    with patch.object(worker, "_detect_regime", return_value={"regime": "bull", "target_allocation": 0.90}), \
         patch.object(worker, "_fetch_vix", return_value=None), \
         patch.object(worker, "_fetch_ohlcv", return_value=df), \
         patch.object(
             worker,
             "_get_fundamental_score_info",
             return_value={"score": 80.0, "raw_score": 80.0, "source": "last_scan", "stale": False},
         ), \
         patch.object(worker, "_get_top5_tickers", return_value=[]), \
         patch.object(worker, "_get_deep_trade_plan", return_value={"stop_loss": 1.0, "targets": [999.0]}), \
         patch.object(worker, "_resolve_cadence", return_value="intraday"), \
         patch.object(worker, "_safe_get_account", return_value=account):
        worker._run_strategy_signals(account)
    assert broker.submit_order.call_count == 1
    order = broker.submit_order.call_args[0][0]
    assert order.symbol == "AAA"
    assert worker._position_meta["AAA"]["strategy_id"] == "leader_campaign"
    assert worker._position_meta["AAA"]["setup"] == "pivot_break"
    close = float(df["Close"].iloc[-1])
    assert order.stop_loss_price == pytest.approx(round(close * 0.96, 4))
    assert order.stop_loss_price != 1.0
    worker.intent_store = MagicMock()
    worker.intent_store.list.return_value = []
    worker._consume_intents(account)
    assert broker.submit_order.call_count == 1
    assert RiskLimits().max_order_notional == 10_000.0
    assert RiskLimits().kelly_scale == 0.5


def test_cli_rejects_leader_campaign_until_the_flag_is_on(monkeypatch):
    from backend.trading.engine import worker as worker_module

    monkeypatch.delenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", raising=False)
    monkeypatch.setenv("APCA_PAPER", "true")
    with pytest.raises(SystemExit):
        worker_module.main(["--once", "--strategy", "leader_campaign"])
    fake = MagicMock()
    fake.ticker_universe = ["AAA"]
    fake.running = False
    fake.is_market_hours = False
    fake.last_run_utc = None
    fake.last_signal_summary = []
    fake._sync_orders.return_value = None
    fake._safe_get_account.return_value = _account()
    monkeypatch.setenv("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "1")
    with patch.object(worker_module, "_build_worker", return_value=fake) as build:
        code = worker_module.main(["--once", "--mode", "shadow", "--strategy", "leader_campaign"])
    assert code == 0
    assert build.call_args[0][0] == "leader_campaign"
    assert build.call_args.kwargs.get("execution_mode") == "shadow"
