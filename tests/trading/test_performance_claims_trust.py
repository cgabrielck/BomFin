"""Wave 0/1: seal-gated performance claims and a browse-only Streamlit shell."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backend.api.paper_performance as pp
from backend.trading.performance.display import (
    PERFORMANCE_STALE_AFTER_DAYS,
    build_trust_status,
    gate_performance_claims,
    snapshot_freshness,
)
from backend.trading.performance.tracker import PerformanceReport

ROOT = Path(__file__).resolve().parents[2]


def _old_misleading_snapshot() -> dict:
    generated = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
    return {
        "generated_at": generated,
        "seal_passed": False,
        "seal_reasons": ["num_trades 0 < min 5", "trading_days 1 < min 20"],
        "metrics": {"num_trades": 0, "trading_days": 1},
        "period": {"trading_days": 1},
        "pnl": {"total_return_pct": 84.0, "annualized_return_pct": 99999.0},
        "benchmark": {"spy_return_pct": 1.2, "alpha_net_of_costs_pct": 80.0},
        "beats_spy_net": True,
        "criteria": {"min_trades": 5, "min_trading_days": 20},
    }


def test_seal_fail_hides_beat_spy_and_absurd_annualized():
    view = gate_performance_claims(_old_misleading_snapshot())
    assert view["claims_allowed"] is False
    assert view["seal_passed"] is False
    assert view["claims_beat_spy"] is False
    assert view["beats_spy_net"] is not True
    assert view["beats_spy_net"] is None
    assert view["annualized_return_pct"] is None
    assert view["annualized_label"] == "n/a"
    assert view["total_return_pct"] is None
    assert view["spy_return_pct"] is None
    assert view["alpha_net_of_costs_pct"] is None
    assert "num_trades" in view["reason"]
    assert view["live"] is False


def test_old_json_status_surfaces_session_card_and_outdated_age():
    heartbeat = {
        "session_card": {
            "seal": False,
            "not_a_seal": True,
            "claims_beat_spy": False,
            "why_no_trade": {"no_setup": 4, "kelly_zero": 1},
        }
    }
    status = build_trust_status(_old_misleading_snapshot(), heartbeat)
    assert status["beats_spy_net"] is not True
    assert status["annualized_label"] == "n/a"
    assert status["claims_beat_spy"] is False
    assert status["session_card"]["seal"] is False
    assert status["session_card"]["not_a_seal"] is True
    assert status["session_card"]["claims_beat_spy"] is False
    assert "no_setup × 4" in status["why_no_trade_summary"]
    assert status["freshness"]["stale"] is True
    assert status["freshness"]["label"].startswith("outdated")
    assert status["freshness"]["age_days"] >= 12
    assert status["freshness"]["stale_after_days"] == PERFORMANCE_STALE_AFTER_DAYS
    assert status["book_dir"] == "backend/data/"
    assert status["kelly_dir"] == "data/"
    assert status["kelly_kind"] == "portfolio experiment"
    assert status["same_ledger"] is False
    assert status["live"] is False


def test_fresh_snapshot_is_not_labeled_outdated():
    fresh = snapshot_freshness(datetime.now(timezone.utc).isoformat())
    assert fresh["stale"] is False
    assert fresh["label"] is None
    assert fresh["live"] is False
    week = snapshot_freshness((datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
    assert week["stale"] is True
    assert str(week["label"]).startswith("outdated")


def test_writer_cannot_store_beat_spy_when_seal_fails(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    report = PerformanceReport(
        start_date=now - timedelta(days=1),
        end_date=now,
        trading_days=1,
        num_trades=0,
        total_return_pct=84.0,
        annualized_return_pct=99999.0,
        alpha_pct=40.0,
        spy_return_pct=1.0,
        final_equity=184000.0,
        initial_capital=100000.0,
    )
    monkeypatch.setattr(pp, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pp, "_load_paper_orders", lambda: [{"symbol": "AAPL"}])
    monkeypatch.setattr(pp, "evaluate_performance", lambda *a, **k: report)
    monkeypatch.setattr(
        "backend.trading.alpaca_broker.AlpacaBroker",
        lambda: (_ for _ in ()).throw(RuntimeError("skip")),
    )
    out = pp.build_paper_report(persist=True, initial_capital=100000)
    assert out["benchmark"]["beats_spy_net"] is not True
    assert out["display"]["claims_beat_spy"] is False
    assert out["display"]["annualized_label"] == "n/a"
    assert out["display"]["total_return_pct"] is None
    assert out["pnl"]["annualized_return_pct"] is None
    saved = json.loads((tmp_path / "performance_paper.json").read_text(encoding="utf-8"))
    assert saved["beats_spy_net"] is not True
    assert saved["seal_passed"] is False
    assert saved["pnl"]["annualized_return_pct"] is None


def test_streamlit_shell_cannot_start_worker_or_show_live_cta():
    dashboard = (ROOT / "backend" / "trading" / "ui" / "dashboard.py").read_text(encoding="utf-8")
    app = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    assert "place_lab_manual_order" not in dashboard
    assert "TradingWorker" not in dashboard
    assert ".start(" not in dashboard
    assert "trading.mode.live" not in dashboard
    assert "worker_start_btn" in dashboard
    assert "disabled=True" in dashboard
    assert "render_paper_book_status" in dashboard
    assert "trading.perf.session" in dashboard
    assert "trading.perf.why" in dashboard
    assert "trading.perf.outdated" in dashboard
    assert "render_paper_book_status" in app
    forbidden = (
        "not the product",
        "lab / legacy",
        "lab/legacy",
        "實驗室／舊",
        "实验室／旧",
        "不是產品",
        "不是产品",
    )
    for phrase in forbidden:
        assert phrase not in dashboard
        assert phrase not in app
