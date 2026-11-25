"""Futu OpenD observe adapter: US map, quota, synthesize, degrade, no order tools."""
from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.observe.errors import ObserveFailure
from backend.observe.futu_adapter import FutuObserveAdapter, build_adapter
from backend.observe.opend_config import OpenDConfig, load_config
from backend.observe.symbols import from_vendor, to_vendor
from backend.observe.timeframes import resolve_timeframe, synthesize

ROOT = Path(__file__).resolve().parents[2]
OBSERVE_PY = list((ROOT / "backend" / "observe").glob("*.py")) + [ROOT / "backend" / "api" / "desk_observe.py"]
INDEX = ROOT / "web" / "static" / "index.html"
BANNED = (
    "OpenSecTradeContext",
    "OpenFutureTradeContext",
    "OpenHKTradeContext",
    "unlock_trade",
    "place_order",
    "modify_order",
    "cancel_order",
    "OrderManager",
    "yfinance",
    "fetch_daily_ohlcv",
    "equity_ohlcv",
    "STOCK_UNIVERSE",
)


class FakeGateway:
    def __init__(self):
        self.subs: dict[str, set[str]] = {}
        self.history_calls: list[tuple[str, str]] = []
        self.cur_calls: list[tuple[str, str]] = []
        self.snap_calls: list[list[str]] = []
        self.fail: dict[str, ObserveFailure] = {}
        self.history: dict[tuple[str, str], list[dict]] = {}
        self.current: dict[tuple[str, str], list[dict]] = {}
        self.quotes: dict[str, dict] = {}
        self.closed = False

    def subscribe(self, codes, subtypes):
        if self.fail.get("subscribe"):
            raise self.fail["subscribe"]
        for code in codes:
            self.subs.setdefault(code, set()).update(subtypes)

    def unsubscribe(self, codes, subtypes):
        if self.fail.get("unsubscribe"):
            raise self.fail["unsubscribe"]
        for code in codes:
            have = self.subs.setdefault(code, set())
            for kind in subtypes:
                have.discard(kind)
            if not have:
                self.subs.pop(code, None)

    def snapshot(self, codes):
        self.snap_calls.append(list(codes))
        if self.fail.get("snapshot"):
            raise self.fail["snapshot"]
        return [dict(self.quotes.get(code, {"code": code, "last_price": None})) for code in codes]

    def history_kline(self, code, kl_type, max_count=1000):
        self.history_calls.append((code, kl_type))
        if self.fail.get("history"):
            raise self.fail["history"]
        return list(self.history.get((code, kl_type), []))

    def cur_kline(self, code, kl_type, num):
        self.cur_calls.append((code, kl_type))
        if self.fail.get("cur"):
            raise self.fail["cur"]
        if (code, kl_type) in self.current:
            rows = list(self.current[(code, kl_type)])
        else:
            rows = list(self.history.get((code, kl_type), []))
        if num is None:
            return rows
        return rows[-int(num) :]

    def close(self):
        self.closed = True


def _hour(index: int, close: float) -> dict:
    return {
        "time_key": f"2026-11-10 {9 + index:02d}:30:00",
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 100 + index,
    }


def _day(index: int, close: float) -> dict:
    return {
        "time_key": f"2026-11-{10 + index:02d}",
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 1000 * (index + 1),
    }


def _adapter(gateway: FakeGateway, **kwargs) -> FutuObserveAdapter:
    clock = kwargs.pop("clock", lambda: 1_000.0)
    config = kwargs.pop("config", None) or OpenDConfig("127.0.0.1", 11111, tuple(kwargs.pop("watchlist", ())))
    return FutuObserveAdapter(
        gateway,
        config,
        position_symbols=kwargs.pop("position_symbols", None),
        clock=clock,
        now=lambda: datetime(2026, 11, 10, 1, 35, tzinfo=timezone.utc),
        **kwargs,
    )


def test_us_symbol_map_and_unmapped():
    assert to_vendor("aapl") == "US.AAPL"
    assert to_vendor("BRK.B") == "US.BRK.B"
    assert from_vendor("US.AAPL") == "AAPL"
    assert from_vendor("US.BRK.B") == "BRK.B"
    for raw in ("", "US.AAPL", "HK.00700", "0700", "SH.600000", "SZ.000001", ".DJI", "AAPL US", "123"):
        with pytest.raises(ObserveFailure) as raised:
            to_vendor(raw)
        assert raised.value.code == "unmapped_symbol"


def test_native_and_synthesized_timeframe_labels():
    native = resolve_timeframe("1m")
    assert native.bar_origin == "native"
    assert native.kl_type == "K_1M"
    assert native.synthesized_from is None
    assert resolve_timeframe("60m").kl_type == "K_60M"
    assert resolve_timeframe("1h").kl_type == "K_60M"
    assert resolve_timeframe("1h").source_kl == resolve_timeframe("60m").source_kl
    for token, kl in (("2h", "K_120M"), ("3h", "K_180M"), ("4h", "K_240M"), ("1q", "K_QUARTER"), ("1y", "K_YEAR")):
        spec = resolve_timeframe(token)
        assert spec.kl_type == kl
        assert spec.bar_origin == "native"
    for token, source, span in (("5h", "K_60M", None), ("3d", "K_DAY", 3), ("5d", "K_DAY", 5)):
        spec = resolve_timeframe(token)
        assert spec.bar_origin == "synthesized"
        assert spec.kl_type is None
        assert spec.synthesized_from == source
        assert spec.span_trading_days == span
    with pytest.raises(ValueError):
        resolve_timeframe("K_5H")


def test_synthesize_folds_real_bars_without_filling_gaps():
    hours = [_hour(i, 10 + i) for i in range(6)]
    folded = synthesize(
        [
            {"time": row["time_key"], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"], "volume": row["volume"]}
            for row in hours
        ],
        5,
    )
    assert len(folded) == 2
    assert folded[0]["open"] == hours[0]["open"]
    assert folded[0]["close"] == hours[4]["close"]
    assert folded[0]["high"] == max(row["high"] for row in hours[:5])
    assert folded[0]["low"] == min(row["low"] for row in hours[:5])
    assert folded[0]["volume"] == sum(row["volume"] for row in hours[:5])
    assert folded[1]["close"] == hours[5]["close"]
    missing = dict(folded[0])
    missing["close"] = None
    assert synthesize([missing], 1) == [missing]


def test_quote_and_bars_label_source_and_refuse_verified_live():
    gateway = FakeGateway()
    gateway.quotes["US.AAPL"] = {
        "code": "US.AAPL",
        "last_price": 190.5,
        "update_time": "2026-11-10 09:31:00",
        "verified": True,
        "live": True,
        "prev_close_price": 1,
    }
    gateway.history[("US.AAPL", "K_1M")] = [_hour(0, 190.5)]
    adapter = _adapter(gateway)
    quote = adapter.quote("AAPL")
    assert quote["source"] == "futu_opend"
    assert quote["vendor"] == "futu_opend"
    assert quote["last"] == 190.5
    assert quote["verified"] is False
    assert quote["live"] is False
    assert quote["error"] is None
    bars = adapter.bars("AAPL", "1m")
    assert bars["bar_origin"] == "native"
    assert bars["kl_type"] == "K_1M"
    assert bars["synthesized_from"] is None
    assert bars["verified"] is False
    assert bars["live"] is False
    assert bars["bars"][0]["c"] == 190.5
    assert "K_1M" in gateway.subs["US.AAPL"]
    assert "QUOTE" in gateway.subs["US.AAPL"]


def test_subscribe_unsubscribe_on_leave_and_watchlist_positions():
    gateway = FakeGateway()
    gateway.history[("US.AAPL", "K_DAY")] = [_day(0, 10), _day(1, 11), _day(2, 12)]
    gateway.history[("US.MSFT", "K_DAY")] = [_day(0, 20)]
    gateway.quotes["US.AAPL"] = {"code": "US.AAPL", "last_price": 10, "update_time": "2026-11-10 10:00:00"}
    adapter = _adapter(
        gateway,
        watchlist=("MSFT", "HK.00700"),
        position_symbols=lambda: ["TSLA", "HK.00700", "MSFT"],
    )
    adapter.bars("AAPL", "1d")
    assert "US.AAPL" in gateway.subs
    assert "US.MSFT" in gateway.subs
    assert "US.TSLA" in gateway.subs
    assert "HK.00700" not in gateway.subs
    assert "K_DAY" in gateway.subs["US.AAPL"]
    assert "K_DAY" not in gateway.subs["US.MSFT"]
    adapter.bars("NVDA", "1d")
    assert "US.AAPL" not in gateway.subs
    assert "US.NVDA" in gateway.subs
    assert "US.MSFT" in gateway.subs
    left = adapter.leave_chart()
    assert left["chart_symbol"] is None
    assert "US.NVDA" not in gateway.subs
    assert gateway.subs["US.MSFT"] == {"QUOTE"}
    assert gateway.subs["US.TSLA"] == {"QUOTE"}


def test_history_cache_skips_repeat_fetch_until_tail_interval():
    gateway = FakeGateway()
    gateway.history[("US.AAPL", "K_1M")] = [_hour(0, 10)]
    clock = {"now": 50.0}
    adapter = _adapter(gateway, clock=lambda: clock["now"], tail_min=15)
    first = adapter.bars("AAPL", "1m")
    second = adapter.bars("AAPL", "1m")
    assert first["bars"][0]["c"] == 10
    assert second["bars"][0]["c"] == 10
    assert gateway.history_calls == [("US.AAPL", "K_1M")]
    assert len(gateway.cur_calls) == 1
    clock["now"] = 80.0
    gateway.current[("US.AAPL", "K_1M")] = [_hour(0, 10), _hour(1, 12)]
    third = adapter.bars("AAPL", "1m")
    assert gateway.history_calls == [("US.AAPL", "K_1M")]
    assert len(gateway.cur_calls) == 2
    assert third["bars"][-1]["c"] == 12
    assert third["degraded"] is False


def test_synthesized_5h_3d_5d_are_labeled_and_do_not_invent_kl_types():
    gateway = FakeGateway()
    gateway.history[("US.AAPL", "K_60M")] = [_hour(i, 10 + i) for i in range(5)]
    gateway.history[("US.AAPL", "K_DAY")] = [_day(i, 100 + i) for i in range(5)]
    adapter = _adapter(gateway)
    five_h = adapter.bars("AAPL", "5h")
    assert five_h["bar_origin"] == "synthesized"
    assert five_h["kl_type"] is None
    assert five_h["synthesized_from"] == "K_60M"
    assert five_h["interval"] == "5h"
    assert len(five_h["bars"]) == 1
    assert five_h["bars"][0]["o"] == 9
    assert five_h["bars"][0]["c"] == 14
    assert gateway.history_calls == [("US.AAPL", "K_60M")]
    assert "K_5H" not in str(gateway.history_calls)
    three_d = adapter.bars("AAPL", "3d")
    assert three_d["bar_origin"] == "synthesized"
    assert three_d["kl_type"] is None
    assert three_d["synthesized_from"] == "K_DAY"
    assert three_d["span_trading_days"] == 3
    assert len(three_d["bars"]) == 2
    five_d = adapter.bars("AAPL", "5d")
    assert five_d["span_trading_days"] == 5
    assert five_d["kl_type"] is None
    assert len(five_d["bars"]) == 1
    assert five_d["bars"][0]["c"] == 104
    assert all(call[1] in {"K_60M", "K_DAY"} for call in gateway.history_calls)


def test_each_degrade_path_is_empty_and_still_futu():
    cases = (
        ("snapshot", "opend_unreachable", "quote"),
        ("snapshot", "permission_denied", "quote"),
        ("snapshot", "quota_exhausted", "quote"),
        ("cur", "opend_unreachable", "bars"),
        ("cur", "quota_exhausted", "bars"),
    )
    for method, code, kind in cases:
        gateway = FakeGateway()
        gateway.fail[method] = ObserveFailure(code)
        gateway.quotes["US.AAPL"] = {"code": "US.AAPL", "last_price": 50, "prev_close_price": 40}
        gateway.history[("US.AAPL", "K_1M")] = [_hour(0, 50)]
        adapter = _adapter(gateway)
        if kind == "quote":
            body = adapter.quote("AAPL")
            assert body["last"] is None
        else:
            body = adapter.bars("AAPL", "1m")
            assert body["bars"] == []
        assert body["degraded"] is True
        assert body["error"] == code
        assert body["source"] == "futu_opend"
        assert body["vendor"] == "futu_opend"
        assert body["verified"] is False
        assert body["live"] is False

    # History page failure must not blank the chart when cur_kline still works.
    for code in ("permission_denied", "quota_exhausted", "opend_unreachable"):
        gateway = FakeGateway()
        gateway.fail["history"] = ObserveFailure(code)
        gateway.current[("US.AAPL", "K_1M")] = [_hour(0, 50)]
        body = _adapter(gateway).bars("AAPL", "1m")
        assert body["bars"]
        assert body["bars"][0]["c"] == 50
        assert body["error"] is None
        assert body["source"] == "futu_opend"
        assert body["verified"] is False
        assert body["live"] is False

    gateway = FakeGateway()
    gateway.quotes["US.AAPL"] = {"code": "US.AAPL", "last_price": None, "prev_close_price": 40}
    empty_quote = _adapter(gateway).quote("AAPL")
    assert empty_quote["error"] == "empty"
    assert empty_quote["last"] is None
    assert empty_quote["last"] != 0

    gateway = FakeGateway()
    gateway.history[("US.AAPL", "K_1M")] = [{"time_key": "2026-11-10 09:30:00", "open": 1, "high": 1, "low": 1, "close": None}]
    empty_bars = _adapter(gateway).bars("AAPL", "1m")
    assert empty_bars["error"] == "empty"
    assert empty_bars["bars"] == []

    gateway = FakeGateway()
    unmapped = _adapter(gateway).bars("HK.00700", "1d")
    assert unmapped["error"] == "unmapped_symbol"
    assert unmapped["vendor_symbol"] is None
    assert unmapped["bars"] == []
    assert gateway.history_calls == []
    assert gateway.subs == {}


def test_unreachable_and_quota_do_not_replay_last_price_or_bars():
    """D6: opend_unreachable empties price and bars. Quota sketch also nulls last."""
    gateway = FakeGateway()
    gateway.quotes["US.AAPL"] = {"code": "US.AAPL", "last_price": 33, "update_time": "2026-11-10 09:31:00"}
    gateway.history[("US.AAPL", "K_1M")] = [_hour(0, 33)]
    clock = {"now": 10.0}
    adapter = _adapter(gateway, clock=lambda: clock["now"], tail_min=15)
    assert adapter.quote("AAPL")["last"] == 33
    assert adapter.bars("AAPL", "1m")["bars"][0]["c"] == 33

    clock["now"] = 40.0
    gateway.fail["cur"] = ObserveFailure("opend_unreachable")
    gateway.fail["history"] = ObserveFailure("opend_unreachable")
    failed = adapter.bars("AAPL", "1m")
    assert failed["degraded"] is True
    assert failed["error"] == "opend_unreachable"
    assert failed["bars"] == []
    assert failed["last"] is None
    assert failed["asof"] is None
    revived = adapter.bars("AAPL", "1m")
    assert revived["bars"] == []
    assert revived["error"] == "opend_unreachable"
    assert revived["last"] is None
    gateway.fail["snapshot"] = ObserveFailure("opend_unreachable")
    quote = adapter.quote("AAPL")
    assert quote["degraded"] is True
    assert quote["error"] == "opend_unreachable"
    assert quote["last"] is None
    assert quote["bars"] == []
    assert quote["asof"] is None

    gateway.fail.clear()
    gateway.quotes["US.MSFT"] = {"code": "US.MSFT", "last_price": 20, "update_time": "2026-11-10 09:31:00"}
    gateway.history[("US.MSFT", "K_1M")] = [_hour(0, 20)]
    clock["now"] = 100.0
    assert adapter.quote("MSFT")["last"] == 20
    assert adapter.bars("MSFT", "1m")["bars"][0]["c"] == 20
    clock["now"] = 130.0
    gateway.fail["cur"] = ObserveFailure("quota_exhausted")
    gateway.fail["history"] = ObserveFailure("quota_exhausted")
    empty_bars = adapter.bars("MSFT", "1m")
    assert empty_bars["error"] == "quota_exhausted"
    assert empty_bars["bars"] == []
    assert empty_bars["last"] is None
    gateway.fail["snapshot"] = ObserveFailure("quota_exhausted")
    blocked = adapter.quote("MSFT")
    assert blocked["error"] == "quota_exhausted"
    assert blocked["last"] is None
    assert blocked["bars"] == []


def test_history_rate_limit_keeps_cur_window_and_blocks_empty_cur():
    gateway = FakeGateway()
    gateway.current[("US.AAPL", "K_1M")] = [_hour(0, 8)]
    adapter = _adapter(gateway, history_limit=0)
    body = adapter.bars("AAPL", "1m")
    assert body["error"] is None
    assert body["bars"][0]["c"] == 8
    assert gateway.history_calls == []

    empty = FakeGateway()
    blocked = _adapter(empty, history_limit=0).bars("AAPL", "1m")
    assert blocked["error"] == "quota_exhausted"
    assert blocked["bars"] == []
    assert blocked["last"] is None
    assert empty.history_calls == []


def test_public_host_is_refused_and_defaults_stay_local():
    cfg = load_config({})
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 11111
    assert cfg.watchlist == ()
    assert load_config({"FUTU_OPEND_HOST": "localhost", "FUTU_OPEND_PORT": "11111"}).host == "localhost"
    assert load_config({"FUTU_OPEND_HOST": "192.168.1.9"}).host == "192.168.1.9"
    assert load_config({"FUTU_OPEND_WATCHLIST": "aapl, HK.00700, MSFT, nvda"}).watchlist == ("AAPL", "MSFT", "NVDA")
    for host in ("8.8.8.8", "opend.example.com", ""):
        with pytest.raises(ObserveFailure) as raised:
            load_config({"FUTU_OPEND_HOST": host})
        assert raised.value.code == "opend_unreachable"
    refused = build_adapter(env={"FUTU_OPEND_HOST": "1.1.1.1"})
    body = refused.quote("AAPL")
    assert body["error"] == "opend_unreachable"
    assert body["last"] is None
    assert body["source"] == "futu_opend"


def test_year_gap_history_page_is_dropped_for_recent_window():
    gateway = FakeGateway()
    gateway.history[("US.NVDA", "K_10M")] = [
        {
            "time_key": "2025-12-23 10:00:00",
            "open": 180,
            "high": 181,
            "low": 179,
            "close": 180.5,
            "volume": 1000,
        },
        {
            "time_key": "2025-12-23 10:10:00",
            "open": 180.5,
            "high": 182,
            "low": 180,
            "close": 181,
            "volume": 1000,
        },
    ]
    gateway.current[("US.NVDA", "K_10M")] = [
        {
            "time_key": f"2026-11-13 {10 + i // 6:02d}:{(i % 6) * 10:02d}:00",
            "open": 160 + i * 0.1,
            "high": 161 + i * 0.1,
            "low": 159 + i * 0.1,
            "close": 160.5 + i * 0.1,
            "volume": 2000 + i,
        }
        for i in range(30)
    ]
    body = _adapter(gateway).bars("NVDA", "10m", limit=30)
    times = [int(bar["t"]) for bar in body["bars"]]
    assert len(body["bars"]) == 30
    assert times == sorted(times)
    assert body["degraded"] is False
    assert body["error"] is None
    first = datetime.fromtimestamp(times[0], timezone.utc)
    assert first.year == 2026
    assert first.month == 11
    for left, right in zip(times, times[1:]):
        assert right - left < 4 * 24 * 3600


def test_weekend_gap_still_merges_history_and_recent():
    gateway = FakeGateway()
    gateway.history[("US.AAPL", "K_1M")] = [
        {
            "time_key": "2026-11-06 15:59:00",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 100,
        }
    ]
    gateway.current[("US.AAPL", "K_1M")] = [
        {
            "time_key": "2026-11-09 09:30:00",
            "open": 10.6,
            "high": 11,
            "low": 10,
            "close": 10.8,
            "volume": 100,
        },
        {
            "time_key": "2026-11-09 09:31:00",
            "open": 10.8,
            "high": 11,
            "low": 10,
            "close": 10.9,
            "volume": 100,
        },
    ]
    body = _adapter(gateway).bars("AAPL", "1m", limit=10)
    assert len(body["bars"]) == 3
    assert body["bars"][0]["c"] == 10.5
    assert body["bars"][-1]["c"] == 10.9


def test_intraday_indicators_keep_unix_bar_times():
    gateway = FakeGateway()
    gateway.current[("US.AAPL", "K_10M")] = [
        {
            "time_key": f"2026-11-13 {9 + i // 6:02d}:{(i % 6) * 10:02d}:00",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100.5 + i,
            "volume": 1000,
        }
        for i in range(60)
    ]
    body = _adapter(gateway).bars("AAPL", "10m", limit=60)
    assert body["indicators"]["sma20"]
    bar_times = {bar["t"] for bar in body["bars"]}
    for point in body["indicators"]["sma20"]:
        assert isinstance(point["t"], int)
        assert point["t"] in bar_times


def test_observe_package_has_no_order_or_other_feed_api():
    pattern = re.compile(r"\b(" + "|".join(BANNED) + r")\b")
    for path in OBSERVE_PY:
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text) is None, path.name
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "yfinance" not in node.module
                assert "equity_ohlcv" not in node.module
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                assert name not in BANNED
    engine = (ROOT / "backend" / "backtesting" / "engine.py").read_text(encoding="utf-8")
    assert "backend.observe" not in engine
    assert "futu_opend" not in engine
    routes = (ROOT / "backend" / "api" / "desk_observe.py").read_text(encoding="utf-8")
    assert "/api/observe/quote/" in routes
    assert "/api/observe/bars/" in routes
    assert "/api/observe/stream" in routes
    assert "OpenQuoteContext" not in routes


def test_chart_interval_picker_labels_synthesized_and_stays_read_only():
    html = INDEX.read_text(encoding="utf-8")
    shell = html[html.find("function chartShell(") : html.find("function bindChartChrome(")]
    assert 'id="chartIntervals"' in shell
    assert 'data-tf="5h"' in shell or "intervalBtn" in shell
    assert "chart.synthesized.short" in html
    assert "synthesized" in html
    assert "合成" in html
    assert "futu_opend" in html
    assert "OpenSecTradeContext" not in html
    assert "unlock_trade" not in html
    assert "/api/observe/bars/" in html
    assert "/api/observe/leave" in html
    assert 'proto+"://"+location.host+"/api/observe/stream"' in html
    assert 'proto+"//"+location.host+"/api/observe/stream"' not in html
    assert "verified: true" not in html
    assert "live: true" not in html
    chart_fn = html[html.find("async function chart(") : html.find("async function aimode(")]
    assert "|| symbol" not in chart_fn
    assert chart_fn.find("if(!want){") < chart_fn.find("/api/chart/")
    assert "/api/observe/bars/" in chart_fn
    assert 't("chart.lead")' not in chart_fn
    assert 'id="chartLead"' in shell
    assert 'intervalOn ? t("chart.observe.separate") : t("chart.lead")' in shell
    status = html[html.find("function chartStatusLine(") : html.find("function drawControlDisabled(")]
    assert "chartTfLabel()" in status
    assert 't("chart.tf.1d")' not in status
    label = html[html.find("function chartTfLabel(") : html.find("function chartStatusLine(")]
    assert "activeObserveTf()" in label
    assert 'if(!tf) return t("chart.tf.1d")' in label
    assert "chart.series.note" in html
    refresh = html[html.find("async function refreshObserveBars(") : html.find("function renderObserveChart(")]
    assert "showObserveFailure(" in refresh
    quote_js = html[html.find("function applyObserveQuote(") : html.find("function startObserveStream(")]
    assert "showObserveFailure(" in quote_js
    failure = html[html.find("function showObserveFailure(") : html.find("function applyObserveQuote(")]
    assert "setData([])" in failure
    assert "wipeDeskCharts()" in failure
    assert 'getElementById("chartProv")' in failure
    assert 'getElementById("chartLegend")' in failure
    assert "prov.textContent = \"\"" in failure
    assert "legend.textContent = \"\"" in failure
    assert 'id = "chartObserveWarn"' in failure or 'id="chartObserveWarn"' in failure


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("backend.trading.telegram_inbox.start_background", lambda: (lambda: None))
    monkeypatch.setattr("backend.api.scan_scheduler.start_background", lambda: (lambda: None))
    from backend.api import desk_observe
    from backend.api.app import app

    gateway = FakeGateway()
    gateway.quotes["US.AAPL"] = {"code": "US.AAPL", "last_price": 188.25, "update_time": "2026-11-10 09:31:00"}
    gateway.history[("US.AAPL", "K_1M")] = [_hour(0, 188.25)]
    gateway.history[("US.AAPL", "K_60M")] = [_hour(i, 20 + i) for i in range(5)]
    adapter = _adapter(gateway, position_symbols=lambda: [])
    desk_observe.reset_adapter(adapter)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client, adapter, gateway
    desk_observe.reset_adapter(None)


def test_http_quote_bars_leave_and_daily_chart_still_separate(client, monkeypatch):
    test_client, adapter, gateway = client
    quote = test_client.get("/api/observe/quote/AAPL")
    assert quote.status_code == 200
    body = quote.json()
    assert body["source"] == "futu_opend"
    assert body["last"] == 188.25
    assert body["verified"] is False
    assert body["live"] is False
    bars = test_client.get("/api/observe/bars/AAPL?tf=5h")
    assert bars.status_code == 200
    series = bars.json()
    assert series["bar_origin"] == "synthesized"
    assert series["kl_type"] is None
    assert series["synthesized_from"] == "K_60M"
    assert series["source"] == "futu_opend"
    assert series["bars"]
    missing = test_client.get("/api/observe/bars/AAPL")
    assert missing.status_code == 422
    bad = test_client.get("/api/observe/bars/AAPL?tf=K_5H")
    assert bad.status_code == 400
    unmapped = test_client.get("/api/observe/quote/HK.00700").json()
    assert unmapped["error"] == "unmapped_symbol"
    assert unmapped["last"] is None
    left = test_client.post("/api/observe/leave")
    assert left.status_code == 200
    assert left.json()["verified"] is False
    assert "US.AAPL" not in gateway.subs
    import pandas as pd

    from backend.api import desk_chart

    frame = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10]},
        index=pd.bdate_range("2026-01-05", periods=1),
    )
    monkeypatch.setattr(
        desk_chart,
        "fetch_daily_ohlcv",
        lambda *a, **k: {"ok": True, "data": frame, "provider": "polygon", "fallback": False, "attempted": ["polygon"], "error": None, "reason": None},
    )
    daily = test_client.get("/api/chart/AAPL?period=6mo")
    assert daily.status_code == 200
    payload = daily.json()
    assert payload["source_kind"] == "daily_snapshot"
    assert payload["interval"] == "1d"
    assert payload["vendor"] == "polygon"
    assert payload["vendor"] != "futu_opend"
    assert "futu_opend" not in str(payload.get("source", ""))
    still = test_client.get("/api/chart/AAPL?period=1m")
    assert still.status_code == 400
    paths = test_client.app.openapi()["paths"]
    assert "/api/observe/quote/{symbol}" in paths
    assert "/api/observe/bars/{symbol}" in paths
    assert not any("unlock" in path or "futu/order" in path for path in paths)


def test_stream_polls_one_symbol_and_unsubscribes_on_close(client):
    test_client, adapter, gateway = client
    with test_client.websocket_connect("/api/observe/stream") as ws:
        ws.send_json({"symbol": "AAPL"})
        frame = ws.receive_json()
    assert frame["source"] == "futu_opend"
    assert frame["delivery"] == "poll"
    assert frame["last"] == 188.25
    assert frame["verified"] is False
    assert frame["live"] is False
    assert "US.AAPL" not in gateway.subs
    assert adapter.subscribed() == {}
