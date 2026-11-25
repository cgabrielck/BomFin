"""P1 zone evidence: stable ids, owner meta, read API, zero-order Option C."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.desk_zones import (
    attach_proposal_zone_ref,
    format_cite,
    get_zone,
    replace_symbol_snapshot,
    update_zone_meta,
)
from backend.trading.engine.session_card import build_session_card

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "web" / "static" / "index.html"
STREAMLIT = ROOT / "backend" / "app.py"
ZONES_PY = ROOT / "backend" / "api" / "desk_zones.py"

ORDER_CTA = (
    "一鍵依區下單",
    "訊號已就緒",
    "AI 建議區",
    "AI建議區",
    "自動畫區",
    "place_desk_order",
    "OrderManager",
)


def _zone_block(html: str) -> str:
    start = html.find("/* CGAB_DRAW_ZONE_BEGIN")
    end = html.find("/* CGAB_DRAW_ZONE_END */")
    assert start != -1 and end > start
    return html[start:end]


def _run_zone_js(block: str, script: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the zone sanitize block")
    proc = subprocess.run(
        [node, "-e", block + "\n" + script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _card(**kwargs):
    base = dict(
        universe_source="stock_universe",
        universe_requested=["AAPL"],
        cap=1,
        cap_env=None,
        fetched=["AAPL"],
        skip_counts={},
        order_statuses=[],
        execution_mode="shadow",
    )
    base.update(kwargs)
    return build_session_card(**base)


@pytest.fixture
def zones_file(tmp_path, monkeypatch):
    path = tmp_path / "desk_zones.json"
    monkeypatch.setenv("DESK_ZONES_PATH", str(path))
    monkeypatch.setattr("backend.trading.telegram_inbox.start_background", lambda: (lambda: None))
    monkeypatch.setattr("backend.api.scan_scheduler.start_background", lambda: (lambda: None))
    monkeypatch.setenv("APCA_PAPER", "true")
    return path


@pytest.fixture
def owner(zones_file):
    from backend.api.app import app

    with TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000)) as client:
        yield client


@pytest.fixture
def guest(zones_file):
    from backend.api.app import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _sample(zone_id="11111111-1111-4111-8111-111111111111", **extra):
    row = {
        "id": zone_id,
        "zone_id": zone_id,
        "priceHigh": 12,
        "priceLow": 10,
        "timeLeft": "2024-01-02",
        "timeRight": "2024-01-05",
        "extendLeft": True,
        "extendRight": False,
        "role": "neutral",
        "notes": "",
        "status": "active",
        "label": "",
    }
    row.update(extra)
    return row


def test_cite_form_omits_empty_notes_and_stamps():
    assert format_cite("abc", "support", "") == "用戶標註價區 abc｜支撐"
    assert format_cite("abc", "support", "前高") == "用戶標註價區 abc｜支撐｜前高"
    assert format_cite("abc", "neutral", "   ") == "用戶標註價區 abc｜中性"
    assert format_cite("abc", "resist", "") == "用戶標註價區 abc｜阻力"
    assert format_cite("abc", "nope", "") == "用戶標註價區 abc｜中性"
    assert "verified" not in format_cite("abc", "resist", "note")
    assert "%" not in format_cite("abc", "neutral", "")


def test_js_stable_uuid_notes_archive_and_cite():
    html = INDEX.read_text(encoding="utf-8")
    assert "Math.random()" not in html
    result = _run_zone_js(
        _zone_block(html),
        r"""
const D = globalThis.CgabDraw;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const id = D.newDrawId();
const again = D.newDrawId();
const built = D.zoneFromPoints({time:"2024-01-02", price:11},{time:"2024-01-10", price:8});
built.id = id;
const stored = D.sanitizeDrawItem(built);
const reloaded = D.sanitizeDrawItem(stored);
const legacy = D.sanitizeDrawItem({
  type:"zone", id:"dabc1234", priceHigh:3, priceLow:1,
  timeLeft:"2024-01-02", timeRight:"2024-01-04", role:"support"
});
const support = D.withZoneRole(stored, "support");
const noted = D.withZoneNotes(support, "前高");
const cleared = D.withZoneNotes(noted, "");
const archived = D.withZoneStatus(noted, "archive");
const restored = D.withZoneStatus(archived, "active");
const sliced = D.withZoneNotes(stored, "n".repeat(300));
console.log(JSON.stringify({
  version: D.DRAW_SCHEMA_VERSION,
  idOk: uuid.test(id) && uuid.test(again) && id !== again,
  kept: stored.id === id && reloaded.id === id,
  role: stored.role,
  notes: stored.notes,
  status: stored.status,
  legacy: legacy && legacy.id,
  cite: D.citeZone(noted),
  citeClear: D.citeZone(cleared),
  citeMissing: D.citeZone({role:"support", notes:"x"}),
  storedRole: noted.role,
  high: archived.priceHigh,
  low: archived.priceLow,
  extL: archived.extendLeft,
  extR: archived.extendRight,
  arch: archived.status,
  back: restored.status,
  sliced: sliced.notes.length,
  banned: D.sanitizeZoneNotes("必買"),
  prices: archived.priceHigh === stored.priceHigh && archived.priceLow === stored.priceLow
}));
""",
    )
    assert result["version"] == 3
    assert result["idOk"] is True
    assert result["kept"] is True
    assert result["role"] == "neutral"
    assert result["notes"] == ""
    assert result["status"] == "active"
    assert result["legacy"] == "dabc1234"
    cite = result["cite"]
    cite_clear = result["citeClear"]
    assert cite.startswith("用戶標註價區 ")
    assert cite.endswith("｜支撐｜前高")
    assert cite.count("｜") == 2
    assert "support" not in cite
    assert result["storedRole"] == "support"
    assert cite_clear.count("｜") == 1
    assert cite_clear.endswith("｜支撐")
    assert not cite_clear.endswith("｜")
    assert result["citeMissing"] == ""
    assert result["arch"] == "archive"
    assert result["back"] == "active"
    assert result["prices"] is True
    assert result["extL"] is False
    assert result["sliced"] == 280
    assert result["banned"] == ""


def test_desk_panel_is_not_an_order_surface():
    html = INDEX.read_text(encoding="utf-8")
    start = html.find('id="zoneDetail"')
    end = html.find("ZONE_DETAIL_END")
    assert start != -1 and end > start
    detail = html[start:end]
    assert 'data-readonly="geom"' in detail
    assert "data-zone-ext" not in detail
    assert 'type="number"' not in detail
    assert "<input" not in detail
    assert "zoneNotes" in detail
    assert 'maxlength="280"' in detail
    assert "data-zone-meta-role" in detail
    assert "data-zone-meta-status" in detail
    assert "data-zone-list" in detail
    assert "無法引用" in detail or "chart.zone.unable" in detail
    for banned in ORDER_CTA + ("必買", "verified", "Buy", "Sell", "下單"):
        assert banned not in detail
    for phrase in ORDER_CTA:
        assert phrase not in html
    assert 'source: "desk_draw"' in html
    assert "/api/desk/zones/snapshot" in html
    assert "/api/desk/zones?symbol=" in html
    assert 'method:"PATCH"' in html
    assert "zoneGuestHint" in html
    assert "mergeZoneItems" in html
    assert '!paperControls && tool!=="select"' in html
    assert "未能同步價區" in html
    assert "只可查看。選取價區後可複製引用。" in html
    assert "has no proposal HTTP route" in ZONES_PY.read_text(encoding="utf-8")
    mirror = STREAMLIT.read_text(encoding="utf-8")
    body_start = mirror.find("def _render_zone_evidence_mirror")
    body_end = mirror.find("\ndef render_charts_tab")
    body = mirror[body_start:body_end]
    assert "list_zones" in body
    assert "st.dataframe" in body
    for token in (
        "st.text_input",
        "st.text_area",
        "st.button",
        "st.slider",
        "place_desk_order",
        "update_zone_meta",
        "replace_symbol_snapshot",
        "/api/orders",
    ):
        assert token not in body
    assert "_render_zone_evidence_mirror(" in mirror
    zsrc = ZONES_PY.read_text(encoding="utf-8")
    assert "place_desk_order" not in zsrc
    assert "OrderManager" not in zsrc
    assert "AlpacaBroker" not in zsrc


def test_owner_snapshot_meta_archive_and_guest_readonly(owner, guest, zones_file):
    zone_id = "11111111-1111-4111-8111-111111111111"
    denied = guest.put(
        "/api/desk/zones/snapshot",
        json={"symbol": "AAPL", "source": "desk_draw", "zones": [_sample(zone_id)]},
    )
    assert denied.status_code == 403
    created = owner.put(
        "/api/desk/zones/snapshot",
        json={
            "symbol": "aapl",
            "source": "desk_draw",
            "zones": [_sample(zone_id, verified=True, live=True, role="nope")],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["verified"] is False
    assert body["live"] is False
    row = body["zones"][0]
    assert row["zone_id"] == zone_id
    assert row["role"] == "neutral"
    assert row["notes"] == ""
    assert row["status"] == "active"
    assert row["verified"] is False
    assert row["live"] is False
    assert row["role"] == "neutral"
    assert row["cite"] == f"用戶標註價區 {zone_id}｜中性"
    assert row["geometry"]["price_high"] == 12
    assert row["geometry"]["price_low"] == 10
    assert row["geometry"]["extend_left"] is True
    assert row["geometry"]["extend_right"] is False
    raw = zones_file.read_text(encoding="utf-8").lower()
    assert '"verified": true' not in raw
    assert '"live": true' not in raw

    stamped = owner.put(
        "/api/desk/zones/snapshot",
        json={"symbol": "AAPL", "source": "desk_draw", "zones": [_sample()], "verified": True},
    )
    assert stamped.status_code == 422

    agent = owner.put(
        "/api/desk/zones/snapshot",
        json={"symbol": "AAPL", "source": "desk_draw", "zones": [_sample("22222222-2222-4222-8222-222222222222")]},
        headers={"X-Cgab-Actor": "agent"},
    )
    assert agent.status_code == 403
    assert get_zone("22222222-2222-4222-8222-222222222222") is None

    invented = owner.post(
        "/api/desk/zones",
        json={"symbol": "AAPL", "price_high": 9, "price_low": 8, "role": "support"},
    )
    assert invented.status_code == 405

    guest_patch = guest.patch(f"/api/desk/zones/{zone_id}", json={"role": "support"})
    assert guest_patch.status_code == 403

    priced = owner.patch(
        f"/api/desk/zones/{zone_id}",
        json={"role": "support", "price_high": 99},
    )
    assert priced.status_code == 422
    unchanged = owner.get(f"/api/desk/zones/{zone_id}").json()
    assert unchanged["geometry"]["price_high"] == 12
    assert unchanged["role"] == "neutral"

    noted = owner.patch(f"/api/desk/zones/{zone_id}", json={"role": "support", "notes": "前高"})
    assert noted.status_code == 200
    assert noted.json()["role"] == "support"
    assert noted.json()["cite"] == f"用戶標註價區 {zone_id}｜支撐｜前高"
    assert noted.json()["geometry"]["extend_left"] is True
    cleared = owner.patch(f"/api/desk/zones/{zone_id}", json={"notes": ""})
    assert cleared.status_code == 200
    assert cleared.json()["notes"] == ""
    assert cleared.json()["cite"] == f"用戶標註價區 {zone_id}｜支撐"
    assert cleared.json()["cite"].count("｜") == 1

    archived = owner.patch(f"/api/desk/zones/{zone_id}", json={"status": "archive"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archive"
    assert archived.json()["geometry"]["price_low"] == 10
    active = owner.get("/api/desk/zones?symbol=AAPL&status=active").json()["zones"]
    filed = owner.get("/api/desk/zones?symbol=AAPL&status=archive").json()["zones"]
    assert active == []
    assert len(filed) == 1
    assert filed[0]["geometry"]["time_left"] == "2024-01-02"
    restored = owner.patch(f"/api/desk/zones/{zone_id}", json={"status": "active", "notes": "前高"})
    assert restored.json()["status"] == "active"
    assert restored.json()["role"] == "support"
    nudged = owner.put(
        "/api/desk/zones/snapshot",
        json={
            "symbol": "AAPL",
            "source": "desk_draw",
            "zones": [_sample(zone_id, role="resist", notes="ignored", priceHigh=18, priceLow=14)],
        },
    )
    assert nudged.status_code == 200
    kept = nudged.json()["zones"][0]
    assert kept["role"] == "support"
    assert kept["notes"] == "前高"
    assert kept["cite"] == f"用戶標註價區 {zone_id}｜支撐｜前高"
    assert kept["geometry"]["price_high"] == 18
    assert kept["geometry"]["price_low"] == 14

    missing = guest.get("/api/desk/zones/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["detail"]["message"] == "無法引用"

    bad_note = owner.patch(f"/api/desk/zones/{zone_id}", json={"notes": "必買"})
    assert bad_note.status_code == 422


def test_g7_select_cite_archive_and_hydrate_merge():
    """Node stand-in for select → cite → archive, plus G3 merge rules."""
    html = INDEX.read_text(encoding="utf-8")
    result = _run_zone_js(
        _zone_block(html),
        r"""
const D = globalThis.CgabDraw;
const id = "55555555-5555-4555-8555-555555555555";
const other = "66666666-6666-4666-8666-666666666666";
let zone = D.sanitizeDrawItem({
  type:"zone", id:id, priceHigh:11, priceLow:8,
  timeLeft:"2024-01-02", timeRight:"2024-01-10",
  extendLeft:true, extendRight:false, role:"neutral", notes:"", status:"active"
});
zone = D.withZoneRole(zone, "support");
zone = D.withZoneNotes(zone, "前高");
const archived = D.withZoneStatus(zone, "archive");
const local = [
  zone,
  {id:"t1", type:"trend", a:{time:"2024-01-02", price:1}, b:{time:"2024-01-03", price:2}}
];
const server = [
  {zone_id:id, role:"resist", notes:"供給", status:"archive", label:"",
   geometry:{price_high:20, price_low:19, time_left:"2024-02-01", time_right:"2024-02-05",
             extend_left:false, extend_right:true}},
  {zone_id:other, role:"neutral", notes:"", status:"active", label:"",
   geometry:{price_high:4, price_low:3, time_left:"2024-03-01", time_right:"2024-03-04",
             extend_left:false, extend_right:false}}
];
const merged = D.mergeZoneItems(local, server);
const kept = merged.find(it => it.id===id);
const added = merged.find(it => it.id===other);
console.log(JSON.stringify({
  cite: D.citeZone(zone),
  archCite: D.citeZone(archived),
  archHigh: archived.priceHigh,
  archLow: archived.priceLow,
  archExt: archived.extendLeft,
  kinds: merged.map(it => it.type),
  keptHigh: kept.priceHigh,
  keptLow: kept.priceLow,
  keptLeft: kept.timeLeft,
  keptExt: kept.extendLeft,
  keptRole: kept.role,
  keptNotes: kept.notes,
  keptStatus: kept.status,
  keptCite: D.citeZone(kept),
  addedHigh: added.priceHigh,
  addedRole: added.role,
  addedCite: D.citeZone(added)
}));
""",
    )
    assert result["cite"] == "用戶標註價區 55555555-5555-4555-8555-555555555555｜支撐｜前高"
    assert result["archCite"].endswith("｜archive") is False
    assert result["archCite"] == "用戶標註價區 55555555-5555-4555-8555-555555555555｜支撐｜前高"
    assert result["archHigh"] == 11
    assert result["archLow"] == 8
    assert result["archExt"] is True
    assert result["kinds"] == ["zone", "trend", "zone"]
    assert result["keptHigh"] == 11
    assert result["keptLow"] == 8
    assert result["keptLeft"] == "2024-01-02"
    assert result["keptExt"] is True
    assert result["keptRole"] == "resist"
    assert result["keptNotes"] == "供給"
    assert result["keptStatus"] == "archive"
    assert result["keptCite"] == "用戶標註價區 55555555-5555-4555-8555-555555555555｜阻力｜供給"
    assert result["addedHigh"] == 4
    assert result["addedRole"] == "neutral"
    assert result["addedCite"] == "用戶標註價區 66666666-6666-4666-8666-666666666666｜中性"


def test_session_card_and_proposal_cite_existing_zone_only(zones_file):
    zone_id = "33333333-3333-4333-8333-333333333333"
    rows = replace_symbol_snapshot("MSFT", [_sample(zone_id, role="resist", notes="供給")])
    assert rows[0]["role"] == "neutral"
    assert rows[0]["notes"] == ""
    updated = update_zone_meta(zone_id, role="resist", notes="供給")
    assert updated["role"] == "resist"
    assert updated["cite"] == f"用戶標註價區 {zone_id}｜阻力｜供給"
    card = _card()
    assert card["seal"] is False
    assert card["evidence"]["seal"] is False
    assert card["evidence"]["verified"] is False
    assert card["evidence"]["live"] is False
    assert card["evidence"]["zones"][0]["zone_id"] == zone_id
    assert card["evidence"]["zones"][0]["verified"] is False
    assert "必買" not in json.dumps(card, ensure_ascii=False)

    forced = _card(zone_evidence={"zones": [{"zone_id": "z", "verified": True, "live": True, "seal": True}]})
    assert forced["seal"] is False
    assert forced["evidence"]["zones"][0]["verified"] is False
    assert forced["evidence"]["zones"][0]["live"] is False
    assert "seal" not in forced["evidence"]["zones"][0]

    missing = attach_proposal_zone_ref({"status": "draft", "evidenceRefs": []}, "missing-zone")
    assert missing["zone_cite_error"] == "無法引用"
    assert missing["evidenceRefs"] == []
    assert missing["verified"] is False
    assert missing["live"] is False
    assert missing["seal"] is False
    assert "price_high" not in missing
    assert "priceHigh" not in missing

    attached = attach_proposal_zone_ref({"status": "draft"}, zone_id)
    assert attached["status"] == "draft"
    assert attached["seal"] is False
    assert attached["verified"] is False
    ref = attached["evidenceRefs"][0]
    assert ref["zone_id"] == zone_id
    assert ref["ref"] == f"用戶標註價區 {zone_id}｜阻力｜供給"
    assert ref["verified"] is False
    assert ref["live"] is False
    assert "price_high" not in ref


def test_journal_attaches_cite_without_a_seal(owner, zones_file, tmp_path, monkeypatch):
    from backend.utils.provenance import journal_store

    journal = tmp_path / "trade_journal.json"
    monkeypatch.setattr(journal_store, "JOURNAL_PATH", journal)
    zone_id = "44444444-4444-4444-8444-444444444444"
    saved = owner.put(
        "/api/desk/zones/snapshot",
        json={"symbol": "NVDA", "source": "desk_draw", "zones": [_sample(zone_id, role="support", notes="前高")]},
    )
    assert saved.status_code == 200
    assert saved.json()["zones"][0]["role"] == "neutral"
    meta = owner.patch(f"/api/desk/zones/{zone_id}", json={"role": "support", "notes": "前高"})
    assert meta.status_code == 200
    assert meta.json()["cite"] == f"用戶標註價區 {zone_id}｜支撐｜前高"
    missing = owner.post("/api/journal", json={"symbol": "NVDA", "note": "no such zone", "zone_id": "missing"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["message"] == "無法引用"
    assert journal_store.load_raw_entries(journal) == []

    res = owner.post(
        "/api/journal",
        json={"symbol": "nvda", "note": "operator note", "zone_id": zone_id},
    )
    assert res.status_code == 200
    entry = res.json()["entries"][0]
    cite = f"用戶標註價區 {zone_id}｜支撐｜前高"
    assert entry["links"]["zone_ref"] == cite
    assert entry["evidence_refs"][0]["ref"] == cite
    assert entry["evidence_refs"][0]["zone_id"] == zone_id
    assert entry["evidence_refs"][0]["verified"] is False
    assert entry["evidence_refs"][0]["live"] is False
    assert entry["provenance"]["verified"] is False
    assert entry["provenance"]["live"] is False
    assert entry.get("seal") is not True
    assert "verified" not in json.dumps(entry["evidence_refs"]).replace('"verified": false', "")
