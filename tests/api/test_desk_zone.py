"""P0.5 zone tool: schema v2, fail-closed sanitize, tint/extend geometry."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "web" / "static" / "index.html"
LICENSE = ROOT / "web" / "static" / "vendor" / "LICENSE.lightweight-charts.txt"

BANNED_ZONE_COPY = (
    "必買",
    "止蝕",
    "止損",
    "必賣",
    "verified",
    "已驗證",
    "AI已確認",
    "AI confirmed",
    "/api/orders",
    "OrderManager",
    "place_desk_order",
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
    program = block + "\n" + script
    proc = subprocess.run(
        [node, "-e", program],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_zone_toolbar_schema_and_reject_list():
    html = INDEX.read_text(encoding="utf-8")
    order = 'const DRAW_TOOL_ORDER = ["select","trend","hline","fib","zone","measure"]'
    assert order in html
    assert order.index("fib") < order.index("zone") < order.index("measure")
    assert "const DRAW_SCHEMA_VERSION = CgabDraw.DRAW_SCHEMA_VERSION" in html
    assert "v: DRAW_SCHEMA_VERSION" in html
    assert "cgab.chart.draw." in html
    assert 'id="drawZoneCanvas"' in html
    assert "fillRect" in html
    assert "setTransform(dpr, 0, 0, dpr, 0, 0)" in html
    assert "rectangle-drawing-tool" in html
    assert "/static/vendor/lightweight-charts.standalone.production.js" in html
    assert "lightweight-charts@5" not in html
    assert "lightweight-charts.v5" not in html.lower()
    assert "rectangle-drawing-tool.js" not in html
    assert LICENSE.read_text(encoding="utf-8").startswith("lightweight-charts v4.2.3")
    assert '"chart.tool.zone":"Zone"' in html
    assert '"chart.tool.zone":"價區"' in html
    assert "zone-ico" in html
    assert 'data-zone-role="neutral"' in html
    assert 'data-zone-role="support"' in html
    assert 'data-zone-role="resist"' in html
    assert 'data-zone-ext="extendLeft"' in html
    assert 'data-zone-ext="extendRight"' in html
    props = html[html.find('id="zoneProps"') : html.find('id="zoneProps"') + 1400]
    assert "zoneProps" in props
    for banned in BANNED_ZONE_COPY:
        assert banned not in props
        for line in html.splitlines():
            if "chart.zone." in line or "chart.tool.zone" in line:
                assert banned.lower() not in line.lower()
    chart = html[html.find("function drawStorageKey(") : html.find("async function aimode(")]
    assert "place_desk_order" not in chart
    assert "/api/orders" not in chart
    assert "Long" not in props
    assert "Short" not in props
    assert "Buy" not in props
    assert "Sell" not in props


def test_zone_sanitize_fail_closed_and_color_only_edits():
    block = _zone_block(INDEX.read_text(encoding="utf-8"))
    result = _run_zone_js(
        block,
        r"""
const D = globalThis.CgabDraw;
const bars = [
  {t:"2024-01-02", o:10, h:12, l:9, c:11},
  {t:"2024-01-03", o:11, h:14, l:10, c:13}
];
const zone = D.zoneFromPoints(
  {time:"2024-01-02", price:11},
  {time:"2024-01-10", price:8}
);
const evil = {};
Object.defineProperty(evil, "type", {get(){ throw new Error("boom"); }});
const list = D.sanitizeDrawList([
  {type:"zone", id:"z-ok", priceHigh:10, priceLow:12, timeLeft:"2024-01-05", timeRight:"2024-01-02", extendLeft:true, extendRight:"yes", role:"support", label:"前高"},
  {type:"order", side:"buy", price:1},
  {type:"auto_sr", level:9},
  {type:"hline", id:"h1", price:12},
  {type:"trend", id:"t1", a:{time:"2024-01-02", price:10}, b:{time:"2024-01-04", price:11}},
  null,
  {type:"zone", id:"flat", priceHigh:5, priceLow:5, timeLeft:"2024-01-02", timeRight:"2024-01-03"},
  {type:"zone", id:"bad-role", role:"verified", label:"必買", priceHigh:5, priceLow:4, timeLeft:"2024-02-01", timeRight:"2024-02-03", extendLeft:1},
  evil,
  {type:"nope"}
]);
const support = D.withZoneRole(zone, "support");
const resist = D.withZoneRole(support, "resist");
const back = D.withZoneRole(resist, "neutral");
const extended = D.withZoneExtend(zone, "extendLeft");
const resizedHigh = D.resizeZone(zone, "n", {time:"2024-06-01", price:15});
const resizedTime = D.resizeZone(zone, "e", {time:"2024-01-15", price:1});
const lockedLeft = D.resizeZone(extended, "w", {time:"2023-01-01", price:1});
const magnetHigh = D.magnetZonePoint({time:"2024-01-03", price:11.2}, bars, "n", true);
const magnetTime = D.magnetZonePoint({time:"2024-01-02", price:11.2}, bars, "w", true);
const magnetOff = D.magnetZonePoint({time:"2024-01-03", price:11.2}, bars, "n", false);
const labeled = D.withZoneLabel(zone, "前高");
console.log(JSON.stringify({
  version: D.DRAW_SCHEMA_VERSION,
  zone,
  list,
  support,
  resist,
  back,
  extended,
  resizedHigh,
  resizedTime,
  lockedLeft,
  magnetHigh,
  magnetTime,
  magnetOff,
  labeled,
  bannedLabel: D.sanitizeZoneLabel("必買"),
  liveLabel: D.sanitizeZoneLabel("live"),
  verifiedLabel: D.sanitizeZoneLabel("verified support"),
  unknownRole: D.withZoneRole(zone, "verified"),
  badExtend: D.withZoneExtend(zone, "extendUp")
}));
""",
    )
    assert result["version"] == 2
    zone = result["zone"]
    assert zone["role"] == "neutral"
    assert zone["label"] == ""
    assert zone["extendLeft"] is False
    assert zone["extendRight"] is False
    assert zone["priceHigh"] == 11
    assert zone["priceLow"] == 8
    assert zone["timeLeft"] == "2024-01-02"
    assert zone["timeRight"] == "2024-01-10"
    kinds = [item["type"] for item in result["list"]]
    assert kinds == ["zone", "hline", "trend", "zone"]
    stored = result["list"][0]
    assert stored["priceHigh"] == 12
    assert stored["priceLow"] == 10
    assert stored["timeLeft"] == "2024-01-02"
    assert stored["timeRight"] == "2024-01-05"
    assert stored["extendLeft"] is True
    assert stored["extendRight"] is False
    assert stored["role"] == "support"
    assert stored["label"] == "前高"
    coerced = result["list"][3]
    assert coerced["role"] == "neutral"
    assert coerced["label"] == ""
    assert coerced["extendLeft"] is False
    for item in result["list"]:
        assert item["type"] in {"zone", "hline", "text", "trend", "fib", "measure"}
        blob = json.dumps(item).lower()
        assert "verified" not in blob
        assert "必買" not in blob
        assert "order" not in blob
    for edited in (result["support"], result["resist"], result["back"]):
        assert edited["priceHigh"] == zone["priceHigh"]
        assert edited["priceLow"] == zone["priceLow"]
        assert edited["timeLeft"] == zone["timeLeft"]
        assert edited["timeRight"] == zone["timeRight"]
        assert edited["extendLeft"] is False
        assert edited["extendRight"] is False
    assert result["support"]["role"] == "support"
    assert result["resist"]["role"] == "resist"
    assert result["back"]["role"] == "neutral"
    assert result["extended"]["extendLeft"] is True
    assert result["extended"]["timeLeft"] == zone["timeLeft"]
    assert result["extended"]["timeRight"] == zone["timeRight"]
    assert result["extended"]["priceHigh"] == zone["priceHigh"]
    assert result["resizedHigh"]["priceHigh"] == 15
    assert result["resizedHigh"]["priceLow"] == zone["priceLow"]
    assert result["resizedHigh"]["timeLeft"] == zone["timeLeft"]
    assert result["resizedHigh"]["timeRight"] == zone["timeRight"]
    assert result["resizedTime"]["timeRight"] == "2024-01-15"
    assert result["resizedTime"]["priceHigh"] == zone["priceHigh"]
    assert result["resizedTime"]["priceLow"] == zone["priceLow"]
    assert result["resizedTime"]["timeLeft"] == zone["timeLeft"]
    assert result["lockedLeft"]["timeLeft"] == zone["timeLeft"]
    assert result["magnetHigh"] == {"time": "2024-01-03", "price": 14}
    assert result["magnetTime"]["time"] == "2024-01-02"
    assert result["magnetTime"]["price"] == 11.2
    assert result["magnetOff"] == {"time": "2024-01-03", "price": 11.2}
    assert result["labeled"]["label"] == "前高"
    assert result["labeled"]["priceHigh"] == zone["priceHigh"]
    assert result["bannedLabel"] == ""
    assert result["liveLabel"] == ""
    assert result["verifiedLabel"] == ""
    assert result["unknownRole"] is None
    assert result["badExtend"] is None
