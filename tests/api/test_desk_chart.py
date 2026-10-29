"""ns-1 v0 Desk chart API: provenance, empty honesty, derived indicators, no OM."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api import desk_chart


ROOT = Path(__file__).resolve().parents[2]
CHART_MODULES = (
    ROOT / "backend/api/desk_chart.py",
    ROOT / "backend/utils/desk_indicators.py",
)
INDEX = ROOT / "web/static/index.html"
APP_TSX = ROOT / "web/src/App.tsx"
DESIGN = ROOT / "docs/CHARTS_INDICATORS_DESIGN.md"

BANNED_IMPORTS = (
    "backend.trading.engine.order_manager",
    "backend.trading.engine.desk_orders",
    "backend.trading.alpaca_broker",
    "backend.lab.advisory_debate",
    "backend.trading.engine.stamp",
)
BANNED_NAMES = frozenset(
    {
        "OrderManager",
        "place_desk_order",
        "place_lab_manual_order",
        "submit_order",
        "submit_new_order",
        "AlpacaBroker",
        "advisory_debate",
    }
)


def _frame(n=60, start="2026-01-05"):
    idx = pd.bdate_range(start, periods=n)
    values = [100.0 + i for i in range(n)]
    return pd.DataFrame(
        {
            "Open": values,
            "High": [v + 1 for v in values],
            "Low": [v - 1 for v in values],
            "Close": values,
            "Volume": [1_000 + i for i in range(n)],
        },
        index=idx,
    )


def _ok(frame, *, provider="yahoo", fallback=False, reason=None, attempted=None):
    return {
        "ok": True,
        "data": frame,
        "provider": provider,
        "fallback": fallback,
        "attempted": attempted or (["polygon", "yahoo"] if fallback else [provider]),
        "error": None,
        "reason": reason,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("backend.trading.telegram_inbox.start_background", lambda: (lambda: None))
    monkeypatch.setattr("backend.api.scan_scheduler.start_background", lambda: (lambda: None))
    from backend.api.app import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_chart_api_returns_provenance_and_indicators(client, monkeypatch):
    frame = _frame(60)
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: _ok(frame, provider="polygon", fallback=False, attempted=["polygon"]),
    )
    resp = client.get("/api/chart/AAPL?period=6mo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["interval"] == "1d"
    assert data["vendor"] == "polygon"
    assert data["fallback"] is False
    assert data["asof"] == frame.index[-1].strftime("%Y-%m-%d")
    assert data["source_kind"] == "daily_snapshot"
    assert "verified" not in data
    assert "live" not in data
    assert data.get("verified") is not True
    assert data.get("live") is not True
    assert len(data["bars"]) == 60
    assert data["bars"][0]["c"] == 100.0
    sma20 = data["indicators"]["sma20"]
    expected = round(sum(100.0 + i for i in range(20)) / 20, 4)
    assert sma20[0]["v"] == expected
    assert data["indicators"]["bb_middle"][0]["v"] == expected
    assert data["indicator_params"]["rsi"]["length"] == 14
    assert data["indicator_params"]["macd"] == {"fast": 12, "slow": 26, "signal": 9}


def test_chart_api_labels_yahoo_fallback(client, monkeypatch):
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: _ok(
            _frame(40),
            provider="yahoo",
            fallback=True,
            reason="yahoo_fallback",
            attempted=["polygon", "yahoo"],
        ),
    )
    data = client.get("/api/chart/msft").json()
    assert data["vendor"] == "yahoo"
    assert data["fallback"] is True
    assert data["fallback_reason"] == "yahoo_fallback"
    assert "verified" not in data


def test_empty_history_does_not_invent_bars(client, monkeypatch):
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: {
            "ok": False,
            "data": None,
            "provider": "none",
            "fallback": False,
            "attempted": ["yahoo"],
            "error": "empty",
            "reason": "yahoo_empty",
        },
    )
    resp = client.get("/api/chart/ZZZZ")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["message"] == "No chart data"
    assert "bars" not in detail
    assert detail.get("asof") is None
    assert detail.get("verified") is not True
    assert detail.get("live") is not True


def test_blank_symbol_and_nan_rows_do_not_invent_closes(client, monkeypatch):
    resp = client.get("/api/chart/%20")
    assert resp.status_code == 404

    idx = pd.bdate_range("2026-01-05", periods=3)
    nan_frame = pd.DataFrame(
        {
            "Open": [float("nan")] * 3,
            "High": [float("nan")] * 3,
            "Low": [float("nan")] * 3,
            "Close": [float("nan")] * 3,
            "Volume": [0, 0, 0],
        },
        index=idx,
    )
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: _ok(nan_frame, provider="yahoo"),
    )
    resp = client.get("/api/chart/FAKE")
    assert resp.status_code == 404
    assert "bars" not in resp.json()["detail"]


def test_invalid_period_is_400_not_silent_default(client):
    resp = client.get("/api/chart/AAPL?period=1m")
    assert resp.status_code == 400


def test_chart_modules_do_not_import_order_manager_or_advisory():
    for path in CHART_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
                    names.add(alias.asname or alias.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                for alias in node.names:
                    names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
        assert not any(mod in imported or imported_has_prefix(imported, mod) for mod in BANNED_IMPORTS)
        assert names.isdisjoint(BANNED_NAMES)


def imported_has_prefix(imported: set[str], needle: str) -> bool:
    return any(item == needle or item.startswith(needle + ".") for item in imported)


def test_missing_volume_stays_null_not_zero(client, monkeypatch):
    frame = _frame(5)
    frame.loc[frame.index[1], "Volume"] = float("nan")
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: _ok(frame, provider="yahoo"),
    )
    data = client.get("/api/chart/AAPL").json()
    assert data["bars"][0]["v"] == 1000
    assert data["bars"][1]["v"] is None
    assert data["bars"][2]["v"] == 1002


def test_desk_chart_omits_missing_volume_histogram():
    html = INDEX.read_text(encoding="utf-8")
    start = html.find("function toVolume(")
    end = html.find("function chartErrorTitle(")
    chunk = html[start:end]
    assert start != -1 and end != -1
    assert "b.v==null?0" not in html
    assert "b.v == null ? 0" not in html
    assert "b.v!=null" in chunk
    assert "isFinite(Number(b.v))" in chunk
    paint = html[html.find("function paintDeskChart(") : html.find("function chartShell(")]
    assert "toVolume(bars)" in paint
    assert "value: b.v==null?0:Number(b.v)" not in paint


def test_desk_chart_non_empty_errors_use_distinct_title():
    html = INDEX.read_text(encoding="utf-8")
    helper = html[html.find("function chartErrorTitle(") : html.find("function chartTheme(")]
    assert 't("chart.load_error")' in helper
    assert 't("chart.empty")' in helper
    assert "status === 404" in helper
    chart_fn = html[html.find("async function chart(") : html.find("async function aimode(")]
    catch = chart_fn[chart_fn.find("catch(") :]
    assert "chartErrorTitle(e)" in catch
    assert 'libFail ? t("chart.lib_error") : t("chart.empty")' not in html
    assert t_key_present(html, "chart.load_error")
    assert t_key_present(html, "chart.empty")
    assert t_key_present(html, "chart.lib_error")
    assert html.count('"chart.load_error"') >= 2
    assert "Chart failed to load." in html
    assert "圖表載入失敗。" in html
    assert "此代碼沒有歷史 K 線" in html
    assert "No history for this symbol" in html


def test_desk_chart_page_has_tv_style_surface_not_order_wire():
    html = INDEX.read_text(encoding="utf-8")
    start = html.find("function loadChartInd(")
    end = html.find("async function aimode(")
    chunk = html[start:end]
    assert start != -1 and end != -1
    assert "lightweight-charts" in chunk
    assert "addCandlestickSeries" in chunk
    assert "subscribeCrosshairMove" in chunk
    assert "chartLegend" in chunk
    assert "place_desk_order" not in chunk
    assert "OrderManager" not in chunk
    assert "advisory_debate" not in chunk
    assert "/api/orders" not in chunk
    assert "tradingview.com/widget" not in html.lower()
    assert "TradingView integrated" not in html
    assert "verified: true" not in html
    assert "live: true" not in html
    assert "Daily closes" not in chunk
    assert t_key_present(html, "chart.not_live")
    assert t_key_present(html, "chart.not_tv")
    assert t_key_present(html, "chart.not_order")


def t_key_present(html: str, key: str) -> bool:
    return f'"{key}"' in html


def test_react_chart_page_keeps_honesty_captions():
    src = APP_TSX.read_text(encoding="utf-8")
    assert "Not live / not verified" in src
    assert "Not an official TradingView widget" in src
    assert "do not place orders" in src
    assert "web/static" in src


def test_design_page_remains_draft():
    text = DESIGN.read_text(encoding="utf-8")
    assert "**Status:** Draft" in text
    assert "未 Accepted" in text
    assert "Issue #10 stays OPEN" in text


_ORDER_CALLS = frozenset(
    {
        "place_desk_order",
        "place_order",
        "submit_order",
        "submit_new_order",
        "place_lab_manual_order",
        "cancel_order",
        "OrderManager",
    }
)
_REGISTER_NAMES = frozenset({"register", "register_tool", "registerTool", "add_tool"})
_JS_ORDER_TOOL = re.compile(
    r"/api/orders|OrderManager|place_desk_order|place_lab_manual_order|"
    r"\bsubmit_order\b|\bplace_order\b|\bcancel_order\b|"
    r"register_tool\s*\(\s*['\"][^'\"]*(?:order|place_desk)|"
    r"registerTool\s*\(\s*['\"][^'\"]*(?:order|place_desk)"
)
STREAMLIT = ROOT / "backend" / "app.py"
CHART_UTILS = ROOT / "backend" / "utils" / "chart_utils.py"
HELP_CHAT = ROOT / "backend" / "api" / "help_chat.py"
STREAMLIT_CHART_FNS = (
    "_build_tech_chart",
    "_render_kline_chart",
    "_add_pattern_layers",
    "_add_trade_layers",
    "_focus_recent_candles",
)


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def source_registers_order_tool(source: str) -> bool:
    """True when Python source registers or calls an order tool."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _ORDER_CALLS:
                return True
            if name in _REGISTER_NAMES:
                segment = ast.get_source_segment(source, node) or ""
                if re.search(r"place_order|place_desk|submit_order|cancel_order|/api/orders|OrderManager", segment):
                    return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value in _ORDER_CALLS or "/api/orders" in value:
                return True
    return False


def js_registers_order_tool(source: str) -> bool:
    return bool(_JS_ORDER_TOOL.search(source))


def _function_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(src, node)
            assert segment, name
            return segment
    raise AssertionError(name)


def _chart_js_region(html: str) -> str:
    start = html.find("function drawStorageKey(")
    end = html.find("async function aimode(")
    assert start != -1 and end != -1 and start < end
    return html[start:end]


def test_registering_an_order_tool_fails_the_gate():
    assert source_registers_order_tool("def wire():\n    register_tool('place_desk_order')\n")
    assert source_registers_order_tool("TOOLS = ['place_order']\n")
    assert source_registers_order_tool("def wire():\n    return '/api/orders'\n")
    assert source_registers_order_tool("def wire():\n    OrderManager()\n")
    assert not source_registers_order_tool("def wire():\n    register_tool('explain_chart')\n")
    assert js_registers_order_tool("registerTool('place_order')")
    assert js_registers_order_tool('fetch("/api/orders")')
    assert not js_registers_order_tool('const DRAW_TOOL_ORDER = ["select","trend","hline","fib","zone","measure"]')


def test_chart_js_streamlit_chart_and_help_chat_do_not_register_order_tools():
    html = INDEX.read_text(encoding="utf-8")
    chart_js = _chart_js_region(html)
    assert not js_registers_order_tool(chart_js)
    assert "place_desk_order" not in chart_js
    assert "OrderManager" not in chart_js
    assert "/api/orders" not in chart_js
    for path in (ROOT / "backend/api/desk_chart.py", CHART_UTILS, HELP_CHAT):
        assert not source_registers_order_tool(path.read_text(encoding="utf-8"))
    for name in STREAMLIT_CHART_FNS:
        segment = _function_source(STREAMLIT, name)
        assert not source_registers_order_tool(segment)
        assert "OrderManager" not in segment
        assert "/api/orders" not in segment
        assert "place_desk_order" not in segment


def test_drawing_toolbar_persistence_and_watchlist_chart_link():
    html = INDEX.read_text(encoding="utf-8")
    assert 'const DRAW_TOOL_ORDER = ["select","trend","hline","fib","zone","measure"]' in html
    shell = html[html.find("function chartShell(") : html.find("function bindChartChrome(")]
    bar = shell[shell.find('id="chartDrawBar"') : shell.find('id="chartDrawExtra"')]
    assert "DRAW_TOOL_ORDER.map(drawToolBtn)" in bar
    assert bar.find('drawAct("magnet")') < bar.find('drawAct("hide")') < bar.find('drawAct("clear")')
    assert 'id="chartDrawExtra"' in shell
    assert "drawToolBtn(\"text\")" in shell
    assert 'drawAct("undo")' in shell
    assert 'drawAct("lock")' in shell
    assert 'return "cgab.chart.draw."+s' in html
    assert 'if(chartTool==="measure") return "chart.mode.measure"' in html
    assert 'if(chartTool==="select") return "chart.mode.observe"' in html
    assert 'return "chart.mode.draw"' in html
    assert "{symbol} · {tf} · {mode} · {vendor} / {asof}" in html
    market = html[html.find("async function market(") : html.find("function loadChartInd(")]
    watch = market[market.find(".watch-open") :]
    assert "watch-open" in market
    assert 'navTo("chart")' in watch
    assert 'navTo("research")' not in watch
    chart_fn = html[html.find("async function chart(") : html.find("async function aimode(")]
    assert "|| symbol" not in chart_fn
    empty_at = chart_fn.find("if(!want){")
    api_at = chart_fn.find("/api/chart/")
    assert empty_at != -1 and api_at != -1 and empty_at < api_at
    assert "chart.empty_symbol" in chart_fn
    assert "loadDrawState(want)" in chart_fn
    assert 'id="drawSvg"' in chart_fn
    render = _function_source(STREAMLIT, "_render_kline_chart")
    assert "modeBarButtonsToAdd" not in render
    assert '"displayModeBar": False' in render
    assert "empty symbol" in render
    assert "drawline" in render
    build = _function_source(STREAMLIT, "_build_tech_chart")
    assert "empty symbol" in build
    react = APP_TSX.read_text(encoding="utf-8")
    assert "onWatch={openChart}" in react
    assert 'setPage("chart")' in react
    react_chart = react[react.find("function ChartPage") : react.find("function AiMode")]
    assert "setBars([])" in react_chart
    assert "if (!want) return" in react_chart
    assert "/api/orders" not in react_chart


def test_vendor_js_is_served(client):
    resp = client.get("/static/vendor/lightweight-charts.standalone.production.js")
    assert resp.status_code == 200
    body = resp.text
    assert "LightweightCharts" in body
    assert "createChart" in body
    denied = client.get("/static/vendor/../index.html")
    assert denied.status_code == 404
