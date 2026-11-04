"""Mobile Desk RO P0 — zero-order shell, paper continue/pause, Tailscale copy.

ADR-005 stays Draft. These checks do not Accept it and do not open live trading.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.mobile_desk import activity_rows, morning_book

ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "web" / "static" / "mobile.html"
INDEX = ROOT / "web" / "static" / "index.html"
SERVE_DOC = ROOT / "docs" / "TAILSCALE_SERVE.md"
ADR = ROOT / "docs" / "ADR-005-mobile-desk-readonly.md"

FORBIDDEN_MOBILE = (
    "Approve live",
    "allow-live",
    "place order",
    "/api/orders",
    "/api/ops/",
    "/api/scan",
    "/api/deep",
    "/api/worker/",
    "Scan all",
    "help-fab",
    "Ask Cgab",
    "confetti",
    "ngrok",
    "funnel",
    "capacitor",
    "Deposit",
    "Withdraw",
    ">LIVE<",
    "Halt",
    "Resume",
)


@pytest.fixture
def quiet_lifespan(monkeypatch):
    monkeypatch.setenv("APCA_PAPER", "true")
    monkeypatch.setenv("DESK_OPERATOR_TOKEN", "unit-test-operator")
    monkeypatch.setenv("DESK_RO_TOKEN", "unit-test-reader")
    monkeypatch.setattr("backend.trading.telegram_inbox.start_background", lambda: (lambda: None))
    monkeypatch.setattr("backend.api.scan_scheduler.start_background", lambda: (lambda: None))


@pytest.fixture
def client(quiet_lifespan):
    from backend.api.app import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _operator(client: TestClient) -> TestClient:
    client.headers.update({"X-Desk-Operator-Token": "unit-test-operator"})
    return client


def _digest(*, claims: bool, alpha: float = 12.5) -> dict:
    return {
        "benchmark": {
            "claims_allowed": claims,
            "alpha_net_of_costs_pct": alpha,
            "spy_return_pct": 4.0,
            "equity": 10100,
            "seal_reason": "" if claims else "trades/days below min",
        },
        "pnl": {"equity": 10100, "claims_allowed": claims},
        "scan": {"as_of": "2026-11-04T01:00:00+00:00", "stale": False, "available": True, "fresh_label_zh": "新鮮", "top5": ["AAPL"]},
        "filled": {"count": 1},
        "pending": {"count": 2},
        "skips": {"summary_zh": "流動性不足"},
    }


def _card(*, seal: bool, claims_beat: bool = False) -> dict:
    return {
        "schema": "session_card.v0",
        "seal": seal,
        "not_a_seal": not seal,
        "claims_beat_spy": claims_beat,
        "execution_mode": "paper",
        "note": "label only",
        "why_no_trade": {},
    }


def test_unsealed_card_withholds_beat_spy_number():
    book = morning_book(_digest(claims=False, alpha=12.5), _card(seal=False, claims_beat=True))
    assert book["alpha_net_of_costs_pct"] is None
    assert book["spy_return_pct"] is None
    assert book["claims_beat_spy"] is False
    assert book["seal"] is False
    assert "12.5" not in str(book["alpha_net_of_costs_pct"])
    assert book["equity_label"] == "paper · not live"
    assert book["digest"]["working_note"].startswith("Working")


def test_claims_without_seal_still_withholds_hero_number():
    book = morning_book(_digest(claims=True, alpha=12.5), _card(seal=False, claims_beat=True))
    assert book["claims_allowed"] is True
    assert book["alpha_net_of_costs_pct"] is None
    assert book["claims_beat_spy"] is False
    assert book["seal_reason"]


def test_sealed_claims_may_show_alpha_without_a_live_stamp():
    book = morning_book(_digest(claims=True, alpha=1.25), _card(seal=True, claims_beat=True))
    assert book["alpha_net_of_costs_pct"] == 1.25
    assert book["claims_beat_spy"] is True
    assert "live" not in book
    assert "verified" not in book


def test_activity_keeps_losses_and_skips():
    rows = activity_rows(
        [
            {
                "ts": "2026-11-04T01:41:00+00:00",
                "symbol": "MSFT",
                "status": "filled",
                "user_visible_summary": "filled",
                "r_multiple": -0.4,
                "log_id": "log-loss",
                "provenance": {"actor": "worker", "source": "paper"},
            },
            {
                "ts": "2026-11-04T02:02:00+00:00",
                "symbol": "AAPL",
                "status": "rejected",
                "user_visible_summary": "liquidity gate",
                "reason_codes": ["skip"],
                "log_id": "log-skip",
                "provenance": {"source": "paper"},
            },
        ],
        {"NVDA": "size cap"},
        heartbeat_ts="2026-11-04T00:12:00+00:00",
    )
    symbols = [row["symbol"] for row in rows]
    assert symbols.index("AAPL") < symbols.index("MSFT")
    assert "NVDA" in symbols
    loss = next(row for row in rows if row["symbol"] == "MSFT")
    assert loss["tone"] == "rose"
    assert loss["action"] == "FILL"
    assert "paper fill" in loss["result"]
    assert loss["mode"] == "paper"
    skip = next(row for row in rows if row["symbol"] == "AAPL")
    assert skip["action"] == "SKIP"
    assert skip["tone"] == "rose"
    assert all(row["mode"] in {"paper", "shadow"} for row in rows)


def test_mobile_template_has_no_order_controls():
    html = MOBILE.read_text(encoding="utf-8")
    style = html[html.find("<style>"):html.find("</style>")]
    lowered = html.lower()
    for phrase in FORBIDDEN_MOBILE:
        assert phrase.lower() not in lowered, phrase
    # The resident honesty line names the prohibition. It is not an order control.
    without_honesty = html.replace("手機不會下單或改 live 規則", "")
    assert "下單" not in without_honesty
    assert "continue paper" in lowered
    assert "pause paper" in lowered
    assert "review seals" in lowered
    assert "請開啟 Tailscale 後重新整理" in html
    assert "paper · not live" in html
    assert "教學／觀察面" in html
    assert "晨報" in html and "狀態" in html and "活動" in html
    assert "曲線事件釘延後" in html
    apis = set(re.findall(r"/api/[A-Za-z0-9_./-]+", html))
    assert apis == {
        "/api/mobile/snapshot",
        "/api/mobile/paper/continue",
        "/api/mobile/paper/pause",
    }
    assert style.count("#7c6cff") == 1
    assert "var(--purple)" not in style
    assert "radial-gradient" not in style
    assert "linear-gradient" not in style
    assert "box-shadow" not in style
    assert "Ask Cgab" not in html
    nav = html[html.find("<nav"):html.find("</nav>")]
    nav_labels = [re.sub(r"\s+", " ", body).strip() for _attrs, body in re.findall(r"<button\b([^>]*)>(.*?)</button>", nav, flags=re.S)]
    assert nav_labels == ["晨報", "狀態", "活動"]
    script = html[html.find("<script>"):]
    script_labels = sorted(re.sub(r"\s+", " ", body).strip() for _attrs, body in re.findall(r"<button\b([^>]*)>(.*?)</button>", script, flags=re.S))
    assert script_labels == ["Continue paper", "Pause paper", "Review seals"]


def test_render_error_keeps_stale_banner_without_illegal_insert():
    """Cached snapshot + fetch failure must show the honest banner and a stale label.

    insertAdjacentHTML(0) throws, so the banner is part of render(), not a follow-up insert.
    """
    html = MOBILE.read_text(encoding="utf-8")
    script = html[html.find("<script>"):html.find("</script>")]
    assert "insertAdjacentHTML" not in script
    assert re.search(r"insertAdjacentHTML\(\s*0\b", script) is None
    assert "上次快照" in script
    assert "· stale" in script
    assert 'id="errorBanner"' in script
    assert 'id="staleNote"' in script
    assert 'root.innerHTML = (errorBanner || "") + body' in script
    load_fn = script[script.find("async function load"):script.find("function renderError")]
    assert 'errorBanner = "";' in load_fn
    err_fn = script[script.find("function renderError"):script.find("function morning")]
    assert "render();" in err_fn
    assert "insertAdjacentHTML" not in err_fn


def test_narrow_desktop_redirects_to_mobile_shell():
    html = INDEX.read_text(encoding="utf-8")
    assert 'location.replace("/m")' in html
    assert "max-width: 520px" in html or "max-width:520px" in html
    assert 'class="phone-gate"' in html
    assert "請開啟 Tailscale 後重新整理" in html
    media = html[html.rfind("@media (max-width:520px)"):]
    assert ".help-fab" in media
    assert "display:none" in media


def test_serve_doc_is_private_mesh_and_adr_stays_draft():
    doc = SERVE_DOC.read_text(encoding="utf-8")
    assert "tailscale serve" in doc
    assert "請開啟 Tailscale 後重新整理" in doc
    assert "/m" in doc
    assert "Draft" in doc
    assert "加入主畫面" in doc
    assert not re.search(r"tailscale\s+funnel", doc, flags=re.I)
    assert "ngrok http" not in doc.lower()
    adr = ADR.read_text(encoding="utf-8").splitlines()
    assert any("**Status:** **Draft**" in line for line in adr[:8])
    assert not (ROOT / "capacitor.config.ts").exists()
    assert not (ROOT / "capacitor.config.json").exists()


def test_guest_snapshot_hides_controls_and_skips_the_book(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("guest must not read the paper book")

    monkeypatch.setattr("backend.api.paper_performance.build_daily_digest", boom)
    res = client.get("/api/mobile/snapshot")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access"] == "guest"
    assert body["operator"] is False
    assert body["controls"]["continue_paper"] is False
    assert body["controls"]["pause_paper"] is False
    assert body["controls"]["orders"] is False
    assert body["equity"] is None
    assert body["activity"] == []
    assert body["live"] is False
    assert body["verified"] is False
    assert body["places_order"] is False
    assert body["adr_005"]["status"] == "Draft"
    assert body["adr_005"]["accepted"] is False


def _patch_reads(monkeypatch):
    monkeypatch.setattr(
        "backend.api.worker_ctl.status",
        lambda *a, **k: {
            "running": True,
            "paper": True,
            "halted": False,
            "heartbeat_ts": "2026-11-04T01:00:00+00:00",
            "session_card": _card(seal=False),
            "skip_by_ticker": {"AAPL": "liquidity gate"},
            "skip_counts": {"liquidity": 1},
            "explain": {"message_zh": "paper worker", "message_en": "paper worker"},
        },
    )
    monkeypatch.setattr(
        "backend.api.paper_performance.build_daily_digest",
        lambda *a, **k: _digest(claims=False, alpha=99),
    )
    monkeypatch.setattr(
        "backend.api.research_jobs.latest_scan",
        lambda: {"available": True, "stale": False, "ts": "2026-11-04T01:00:00+00:00", "ranking_count": 12, "top5_tickers": ["AAPL"]},
    )
    monkeypatch.setattr("backend.api.research_jobs.latest_job", lambda kind: None)
    monkeypatch.setattr(
        "backend.api.trade_journal.build_journal_response",
        lambda **k: {"entries": []},
    )

    class _Store:
        def list(self, **_kwargs):
            return [object(), object()]

    monkeypatch.setattr("backend.api.intents.get_intent_store", lambda: _Store())
    monkeypatch.setattr("backend.trading.safety.kill_switch.is_halted", lambda: False)
    monkeypatch.setattr("backend.trading.safety.kill_switch.get_reason", lambda: None)


def test_reader_sees_book_but_cannot_post_paper(client, monkeypatch, tmp_path):
    _patch_reads(monkeypatch)
    monkeypatch.setattr("backend.api.mobile_desk.AI_MODE_PATH", tmp_path / "ai_mode.json")
    started = {"n": 0}
    monkeypatch.setattr(
        "backend.api.worker_ctl.start",
        lambda **k: started.__setitem__("n", started["n"] + 1),
    )
    res = client.get("/api/mobile/snapshot", headers={"X-Desk-Ro-Token": "unit-test-reader"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["access"] == "reader"
    assert body["operator"] is False
    assert body["controls"]["continue_paper"] is False
    assert body["alpha_net_of_costs_pct"] is None
    assert body["equity"] == 10100
    assert body["agents"]["intent"]["pending"] == 2
    assert any(row["symbol"] == "AAPL" and row["action"] == "SKIP" for row in body["activity"])
    denied = client.post(
        "/api/mobile/paper/continue",
        headers={"X-Desk-Ro-Token": "unit-test-reader", "X-Cgab-Surface": "mobile-ro"},
        json={"mode": "paper"},
    )
    assert denied.status_code == 403, denied.text
    assert started["n"] == 0


def test_continue_and_pause_are_paper_worker_only(client, monkeypatch, tmp_path):
    _operator(client)
    monkeypatch.setattr("backend.api.mobile_desk.AI_MODE_PATH", tmp_path / "ai_mode.json")
    (tmp_path / "ai_mode.json").write_text('{"strategy": "adaptive"}', encoding="utf-8")
    calls = {"start": [], "stop": 0, "kill": 0, "broker": 0}

    def fake_start(strategy="breakout", interval=60):
        calls["start"].append((strategy, interval))
        return {"running": True, "paper": True, "already_running": False}

    def fake_stop():
        calls["stop"] += 1
        return {"running": False, "paper": True}

    monkeypatch.setattr("backend.api.worker_ctl.start", fake_start)
    monkeypatch.setattr("backend.api.worker_ctl.stop", fake_stop)
    monkeypatch.setattr(
        "backend.trading.safety.kill_switch.engage",
        lambda *a, **k: calls.__setitem__("kill", calls["kill"] + 1),
    )
    monkeypatch.setattr(
        "backend.trading.alpaca_broker.AlpacaBroker",
        lambda *a, **k: calls.__setitem__("broker", calls["broker"] + 1),
    )

    headers = {"X-Cgab-Surface": "mobile-ro"}
    started = client.post("/api/mobile/paper/continue", headers=headers, json={"mode": "paper"})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["mode"] == "paper"
    assert body["touches_broker"] is False
    assert body["touches_live"] is False
    assert body["touches_kill"] is False
    assert body["places_order"] is False
    assert body["live"] is False
    assert calls["start"] == [("adaptive", 60)]
    assert calls["kill"] == 0
    assert calls["broker"] == 0

    paused = client.post("/api/mobile/paper/pause", headers=headers, json={"mode": "paper"})
    assert paused.status_code == 200, paused.text
    assert paused.json()["running"] is False
    assert calls["stop"] == 1
    assert calls["kill"] == 0
    assert '"worker_enabled": false' in (tmp_path / "ai_mode.json").read_text(encoding="utf-8")


def test_live_mode_and_extra_fields_never_start_the_worker(client, monkeypatch, tmp_path):
    _operator(client)
    monkeypatch.setattr("backend.api.mobile_desk.AI_MODE_PATH", tmp_path / "ai_mode.json")
    calls = {"n": 0}
    monkeypatch.setattr(
        "backend.api.worker_ctl.start",
        lambda **k: calls.__setitem__("n", calls["n"] + 1),
    )
    live = client.post("/api/mobile/paper/continue", json={"mode": "live"})
    assert live.status_code == 403, live.text
    extra = client.post("/api/mobile/paper/continue", json={"mode": "paper", "allow_live": True})
    assert extra.status_code == 422, extra.text
    monkeypatch.setenv("APCA_PAPER", "false")
    blocked = client.post("/api/mobile/paper/continue", json={"mode": "paper"})
    assert blocked.status_code == 403, blocked.text
    assert calls["n"] == 0


def test_mobile_surface_blocks_orders_kill_and_scan(client, monkeypatch):
    _operator(client)
    flags = {"order": 0, "kill": 0, "scan": 0}

    monkeypatch.setattr(
        "backend.api.app.place_desk_order",
        lambda *a, **k: flags.__setitem__("order", flags["order"] + 1),
    )
    monkeypatch.setattr(
        "backend.trading.safety.kill_switch.engage",
        lambda *a, **k: flags.__setitem__("kill", flags["kill"] + 1),
    )
    monkeypatch.setattr(
        "backend.api.research_jobs.start_scan",
        lambda *a, **k: flags.__setitem__("scan", flags["scan"] + 1),
    )
    headers = {"X-Cgab-Surface": "mobile-ro"}
    order = client.post("/api/orders", headers=headers, json={"symbol": "AAPL", "quantity": 1})
    kill = client.post("/api/ops/kill", headers=headers)
    scan = client.post("/api/scan", headers=headers, json={})
    assert order.status_code == 403, order.text
    assert kill.status_code == 403, kill.text
    assert scan.status_code == 403, scan.text
    assert "read-only" in order.json()["detail"]
    assert flags == {"order": 0, "kill": 0, "scan": 0}


def test_mobile_routes_serve_shell(client):
    page = client.get("/m")
    assert page.status_code == 200
    assert "Continue paper" in page.text
    assert "Pause paper" in page.text
    assert "/api/orders" not in page.text
    manifest = client.get("/m/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["start_url"] == "/m"
    assert manifest.json()["display"] == "standalone"
