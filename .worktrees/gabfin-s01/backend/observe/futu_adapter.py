"""Quota-safe Futu OpenD observe adapter.

On-demand set: the current chart symbol, paper positions, and a small
owner watchlist. Historical bars are cached. 5h / 3d / 5d are folded from
native K_60M / K_DAY and labeled synthesized. No trade context.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

from backend.observe.errors import DEGRADE_CODES, ObserveFailure
from backend.observe.opend_config import MAX_WATCHLIST, OpenDConfig, load_config
from backend.observe.symbols import parse_internal, to_vendor
from backend.observe.timeframes import Timeframe, resolve_timeframe, synthesize
from backend.utils.desk_indicators import compute_closed_set_from_bars

SOURCE = "futu_opend"
# D6: these failures return an empty price and empty bars. Do not replay the last read.
_EMPTY_ON_FAIL = frozenset({"opend_unreachable", "quota_exhausted"})
MAX_DEMAND = 32
HIST_PAGE = 1000
HIST_TTL_SECONDS = 7 * 24 * 3600
TAIL_MIN_SECONDS = 15
HISTORY_MAX_CALLS = 60
HISTORY_WINDOW_SECONDS = 30
POSITION_REFRESH_SECONDS = 60
# Overnight and a long weekend stay mergeable; a multi-month hole does not.
MAX_MERGE_GAP_SECONDS = 4 * 24 * 3600
_ET = ZoneInfo("America/New_York")

PositionProvider = Callable[[], Sequence[str]]
Clock = Callable[[], float]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _price(value: Any) -> float | None:
    number = _finite(value)
    if number is None or number <= 0:
        return None
    return number


def _volume(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    number = _finite(value)
    if number is None or number < 0:
        return None
    return int(number)


def _clean_bar(row: dict) -> dict | None:
    raw_time = row.get("time_key", row.get("time", row.get("t")))
    if raw_time is None:
        return None
    text = str(raw_time).strip()
    if not text or text.lower() in {"nat", "none", "nan"}:
        return None
    open_ = _price(row.get("open", row.get("Open")))
    high = _price(row.get("high", row.get("High")))
    low = _price(row.get("low", row.get("Low")))
    close = _price(row.get("close", row.get("Close")))
    if open_ is None or high is None or low is None or close is None:
        return None
    if "volume" in row or "Volume" in row or "v" in row:
        volume = _volume(row.get("volume", row.get("Volume", row.get("v"))))
    else:
        volume = None
    return {"time": text, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _parse_et(text: str) -> datetime | None:
    raw = text.strip()
    if len(raw) >= 19 and raw[10] in {" ", "T"}:
        try:
            parsed = datetime.strptime(raw[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=_ET)
    if len(raw) >= 10:
        try:
            parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return None
        return parsed.replace(tzinfo=_ET)
    return None


def _time_token(raw: str, intraday: bool) -> str | int:
    text = str(raw).strip()
    if not intraday:
        return text[:10]
    parsed = _parse_et(text)
    if parsed is None:
        return text
    return int(parsed.timestamp())


def _asof(raw: str | None, intraday: bool) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not intraday and len(text) >= 10 and text[4] == "-":
        return text[:10]
    parsed = _parse_et(text)
    if parsed is None:
        return text
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public_bar(bar: dict, intraday: bool) -> dict:
    volume = bar.get("volume")
    return {
        "t": _time_token(str(bar["time"]), intraday),
        "o": round(float(bar["open"]), 4),
        "h": round(float(bar["high"]), 4),
        "l": round(float(bar["low"]), 4),
        "c": round(float(bar["close"]), 4),
        "v": None if volume is None else int(volume),
    }


def _seal(payload: dict) -> dict:
    payload["source"] = SOURCE
    payload["vendor"] = SOURCE
    payload["verified"] = False
    payload["live"] = False
    if payload["verified"] is not False or payload["live"] is not False:
        raise RuntimeError("observe payload must not stamp verified or live")
    if payload["source"] != SOURCE or payload["vendor"] != SOURCE:
        raise RuntimeError("observe source must be futu_opend")
    error = payload.get("error")
    if error is not None and error not in DEGRADE_CODES:
        payload["error"] = "opend_unreachable"
        payload["degraded"] = True
        payload["last"] = None
        payload["bars"] = []
    return payload


class _CallWindow:
    def __init__(self, limit: int, window: float, clock: Clock):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._stamps: list[float] = []

    def allow(self) -> bool:
        now = self.clock()
        self._stamps = [stamp for stamp in self._stamps if now - stamp < self.window]
        if len(self._stamps) >= self.limit:
            return False
        self._stamps.append(now)
        return True


class FutuObserveAdapter:
    """Observe adapter. ``gateway`` is injected so tests never dial OpenD."""

    def __init__(
        self,
        gateway: Any,
        config: OpenDConfig,
        *,
        position_symbols: PositionProvider | None = None,
        clock: Clock | None = None,
        now: Callable[[], datetime] | None = None,
        hist_ttl: float = HIST_TTL_SECONDS,
        tail_min: float = TAIL_MIN_SECONDS,
        history_limit: int = HISTORY_MAX_CALLS,
        history_window: float = HISTORY_WINDOW_SECONDS,
        boot_error: str | None = None,
    ):
        self.gateway = gateway
        self.config = config
        self._position_symbols = position_symbols
        self._clock = clock or _monotonic
        self._now = now or _utc_now
        self._hist_ttl = hist_ttl
        self._tail_min = tail_min
        self._history = _CallWindow(history_limit, history_window, self._clock)
        self._boot_error = boot_error
        self._lock = threading.Lock()
        self._chart: str | None = None
        self._chart_tf: str | None = None
        self._view_gen = 0
        self._positions: list[str] = []
        self._positions_at = -1e12
        self._active: dict[str, set[str]] = {}
        self._cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self._tail_at: dict[tuple[str, str], float] = {}
        self._last_quote: dict[str, dict] = {}

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        gateway: Any = None,
        position_symbols: PositionProvider | None = None,
    ) -> "FutuObserveAdapter":
        try:
            config = load_config(env)
        except ObserveFailure as exc:
            from backend.observe.opend_config import DEFAULT_HOST, DEFAULT_PORT

            config = OpenDConfig(DEFAULT_HOST, DEFAULT_PORT, ())
            return cls(gateway=_ClosedGateway(), config=config, position_symbols=position_symbols, boot_error=exc.code)
        if gateway is None:
            from backend.observe.futu_gateway import FutuQuoteGateway

            gateway = FutuQuoteGateway(config.host, config.port)
        return cls(gateway=gateway, config=config, position_symbols=position_symbols)

    def close(self) -> None:
        with self._lock:
            closer = getattr(self.gateway, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    return

    def subscribed(self) -> dict[str, set[str]]:
        with self._lock:
            return {code: set(kinds) for code, kinds in self._active.items()}

    def leave_chart(self, generation: int | None = None) -> dict:
        """Drop the chart symbol. A stale ``generation`` does not unsubscribe a newer view."""
        with self._lock:
            if generation is not None and generation != self._view_gen:
                body = {
                    "ok": True,
                    "stale": True,
                    "chart_symbol": self._chart,
                    "source": SOURCE,
                    "verified": False,
                    "live": False,
                }
                return _seal(body)
            self._chart = None
            self._chart_tf = None
            self._view_gen += 1
            error = self._sync_locked()
        body = {"ok": error is None, "chart_symbol": None, "source": SOURCE, "verified": False, "live": False}
        if error is not None:
            body["degraded"] = True
            body["error"] = error
        return _seal(body)

    def quote(self, symbol: str) -> dict:
        with self._lock:
            return self._quote_locked(symbol)

    def bars(self, symbol: str, tf: str, *, limit: int = 300) -> dict:
        spec = resolve_timeframe(tf)
        bounded = max(1, min(int(limit or 300), HIST_PAGE))
        with self._lock:
            return self._bars_locked(symbol, spec, bounded)

    def _quote_locked(self, symbol: str) -> dict:
        try:
            internal = parse_internal(symbol)
            vendor = to_vendor(internal)
        except ObserveFailure:
            return self._fail(symbol.strip().upper(), None, "quote", "unmapped_symbol")
        if self._boot_error:
            return self._fail(internal, vendor, "quote", self._boot_error)
        try:
            self._set_chart_locked(internal, self._chart_tf)
            rows = self.gateway.snapshot([vendor])
        except ObserveFailure as exc:
            if exc.code in _EMPTY_ON_FAIL:
                self._drop_series_locked(internal, vendor)
            return self._fail(internal, vendor, "quote", exc.code, viewed=True)
        match = _match_snapshot(rows, vendor)
        last = _price(None if match is None else match.get("last_price", match.get("last")))
        asof_raw = None if match is None else match.get("update_time", match.get("data_time", match.get("time")))
        if last is None:
            return self._fail(internal, vendor, "quote", "empty", viewed=True)
        body = self._base(internal, vendor, "quote")
        body.update(
            {
                "asof": _asof(None if asof_raw is None else str(asof_raw), True),
                "degraded": False,
                "error": None,
                "last": round(last, 4),
            }
        )
        sealed = _seal(body)
        self._last_quote[internal] = dict(sealed)
        return sealed

    def _bars_locked(self, symbol: str, spec: Timeframe, limit: int) -> dict:
        try:
            internal = parse_internal(symbol)
            vendor = to_vendor(internal)
        except ObserveFailure:
            return self._fail(symbol.strip().upper(), None, spec.token, "unmapped_symbol", spec=spec)
        if self._boot_error:
            return self._fail(internal, vendor, spec.token, self._boot_error, spec=spec)
        try:
            self._set_chart_locked(internal, spec.token)
            native, tail_error = self._native_bars_locked(vendor, spec.source_kl, limit)
        except ObserveFailure as exc:
            if exc.code in _EMPTY_ON_FAIL:
                self._drop_series_locked(internal, vendor, spec.source_kl)
            return self._fail(internal, vendor, spec.token, exc.code, spec=spec, viewed=True)
        if not native:
            return self._fail(internal, vendor, spec.token, "empty", spec=spec, viewed=True)
        return self._present(
            internal,
            vendor,
            spec,
            native,
            limit,
            degraded=tail_error is not None,
            error=tail_error,
        )

    def _native_bars_locked(self, vendor: str, kl_type: str, limit: int) -> tuple[list[dict], str | None]:
        """Chart window is ``get_cur_kline(num=limit)``. History extends only when contiguous."""
        key = (vendor, kl_type)
        now = self._clock()
        need = max(1, min(int(limit or 300), HIST_PAGE))
        cached = self._fresh_cache(vendor, kl_type)
        tail_at = self._tail_at.get(key, -1e12)
        if cached is not None and now - tail_at < self._tail_min:
            return list(cached)[-need:], None

        try:
            tail_rows = self.gateway.cur_kline(vendor, kl_type, num=need)
        except ObserveFailure as exc:
            if exc.code in _EMPTY_ON_FAIL:
                self._cache.pop(key, None)
                self._tail_at.pop(key, None)
                raise
            if cached:
                return list(cached)[-need:], exc.code
            raise
        recent = [bar for bar in (_clean_bar(row) for row in tail_rows) if bar is not None]
        self._tail_at[key] = now

        hist: list[dict] = []
        if cached is None:
            if self._history.allow():
                try:
                    rows = self.gateway.history_kline(vendor, kl_type, max_count=HIST_PAGE)
                    hist = [bar for bar in (_clean_bar(row) for row in rows) if bar is not None]
                except ObserveFailure as exc:
                    if not recent:
                        if exc.code in _EMPTY_ON_FAIL:
                            self._cache.pop(key, None)
                            self._tail_at.pop(key, None)
                        raise
                    hist = []
            elif not recent:
                raise ObserveFailure("quota_exhausted")
        else:
            hist = list(cached)

        if recent and hist:
            if _contiguous_enough(hist, recent):
                merged = _merge_bars(hist, recent)
                stored_at = now if cached is None else self._cache.get(key, (now, merged))[0]
            else:
                merged = list(recent)
                stored_at = now
        elif recent:
            merged = list(recent)
            stored_at = now if cached is None else self._cache.get(key, (now, merged))[0]
        else:
            merged = list(hist)
            stored_at = now if cached is None else self._cache.get(key, (now, merged))[0]

        self._cache[key] = (stored_at, list(merged))
        return list(merged)[-need:], None

    def _drop_series_locked(self, internal: str, vendor: str, kl_type: str | None = None) -> None:
        """Forget the last quote and cached bars so a failure cannot be served later."""
        self._last_quote.pop(internal, None)
        keys = [(vendor, kl_type)] if kl_type else [key for key in self._cache if key[0] == vendor]
        for key in keys:
            self._cache.pop(key, None)
            self._tail_at.pop(key, None)

    def _fresh_cache(self, vendor: str, kl_type: str) -> list[dict] | None:
        found = self._cache.get((vendor, kl_type))
        if found is None:
            return None
        stored_at, bars = found
        ttl = self._hist_ttl if bars else self._tail_min
        if self._clock() - stored_at > ttl:
            return None
        return list(bars)

    def _present(
        self,
        internal: str,
        vendor: str,
        spec: Timeframe,
        native: list[dict],
        limit: int,
        *,
        degraded: bool,
        error: str | None,
    ) -> dict:
        folded = synthesize(native, spec.group) if spec.bar_origin == "synthesized" else list(native)
        view = folded[-limit:]
        public = [_public_bar(bar, spec.intraday) for bar in view]
        last_time = None if not view else str(view[-1]["time"])
        body = self._base(internal, vendor, spec.token)
        body.update(
            {
                "kl_type": spec.kl_type,
                "bar_origin": spec.bar_origin,
                "synthesized_from": spec.synthesized_from,
                "asof": _asof(last_time, spec.intraday),
                "degraded": degraded,
                "error": error,
                "bars": public,
                "indicators": compute_closed_set_from_bars(public),
            }
        )
        if spec.span_trading_days is not None:
            body["span_trading_days"] = spec.span_trading_days
        return _seal(body)

    def _set_chart_locked(self, internal: str, tf: str | None) -> None:
        self._refresh_positions_locked()
        self._chart = internal
        if tf:
            self._chart_tf = tf
        self._view_gen += 1
        error = self._sync_locked()
        if self._chart:
            code = to_vendor(self._chart)
            need = self._desired_locked().get(code, set())
            have = self._active.get(code, set())
            if need and not need.issubset(have):
                raise ObserveFailure(error or "opend_unreachable")

    def _refresh_positions_locked(self) -> None:
        if self._position_symbols is None:
            return
        if self._clock() - self._positions_at < POSITION_REFRESH_SECONDS:
            return
        self._positions_at = self._clock()
        try:
            raw = self._position_symbols() or []
        except Exception:
            return
        found: list[str] = []
        for item in raw:
            try:
                symbol = parse_internal(str(item))
            except ObserveFailure:
                continue
            if symbol not in found:
                found.append(symbol)
        self._positions = found

    def _demand_locked(self) -> list[str]:
        ordered: list[str] = []
        if self._chart:
            ordered.append(self._chart)
        pool: list[str] = []
        for symbol in list(self.config.watchlist) + list(self._positions):
            try:
                pool.append(parse_internal(symbol))
            except ObserveFailure:
                continue
        for symbol in pool:
            if symbol not in ordered:
                ordered.append(symbol)
            if len(ordered) >= MAX_DEMAND:
                break
        return ordered[:MAX_DEMAND]

    def _desired_locked(self) -> dict[str, set[str]]:
        desired: dict[str, set[str]] = {}
        for symbol in self._demand_locked():
            desired.setdefault(to_vendor(symbol), set()).add("QUOTE")
        if self._chart and self._chart_tf:
            try:
                spec = resolve_timeframe(self._chart_tf)
            except ValueError:
                spec = None
            if spec is not None:
                desired.setdefault(to_vendor(self._chart), set()).add(spec.source_kl)
        return desired

    def _sync_locked(self) -> str | None:
        desired = self._desired_locked()
        error: str | None = None
        for code, kinds in list(self._active.items()):
            keep = desired.get(code, set())
            drop = set(kinds) - keep
            if not drop:
                continue
            try:
                self.gateway.unsubscribe([code], sorted(drop))
            except ObserveFailure as exc:
                error = exc.code
                continue
            kinds -= drop
            if kinds:
                self._active[code] = kinds
            else:
                self._active.pop(code, None)
        for code, kinds in desired.items():
            have = self._active.get(code, set())
            add = set(kinds) - have
            if not add:
                continue
            try:
                self.gateway.subscribe([code], sorted(add))
            except ObserveFailure as exc:
                error = exc.code
                continue
            self._active.setdefault(code, set()).update(add)
        return error

    def _base(self, symbol: str, vendor: str | None, interval: str) -> dict:
        return {
            "symbol": symbol,
            "vendor_symbol": vendor,
            "source": SOURCE,
            "vendor": SOURCE,
            "interval": interval,
            "asof": None,
            "fetched_at": self._stamp(),
            "degraded": False,
            "error": None,
            "last": None,
            "bars": [],
            "verified": False,
            "live": False,
            "view_gen": self._view_gen,
        }

    def _fail(
        self,
        symbol: str,
        vendor: str | None,
        interval: str,
        code: str,
        *,
        spec: Timeframe | None = None,
        viewed: bool = False,
    ) -> dict:
        body = self._base(symbol, vendor, interval)
        body["degraded"] = True
        body["error"] = code if code in DEGRADE_CODES else "opend_unreachable"
        body["last"] = None
        body["bars"] = []
        body["view_gen"] = self._view_gen if viewed else None
        body["kl_type"] = None if spec is None or spec.bar_origin != "native" else spec.kl_type
        body["bar_origin"] = None if spec is None else spec.bar_origin
        body["synthesized_from"] = None if spec is None else spec.synthesized_from
        if spec is not None and spec.span_trading_days is not None:
            body["span_trading_days"] = spec.span_trading_days
        if body["bar_origin"] == "synthesized":
            body["kl_type"] = None
        return _seal(body)

    def _stamp(self) -> str:
        return self._now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _monotonic() -> float:
    import time

    return time.monotonic()


def _match_snapshot(rows: Iterable[dict], vendor: str) -> dict | None:
    found = None
    for row in rows:
        code = str(row.get("code") or row.get("stock_code") or "").upper()
        if code == vendor or not code:
            found = row
            if code == vendor:
                return row
    return found


def _merge_bars(cached: list[dict], tail: list[dict]) -> list[dict]:
    by_time = {bar["time"]: bar for bar in cached}
    for bar in tail:
        by_time[bar["time"]] = bar
    return [by_time[key] for key in sorted(by_time)]


def _bar_epoch(bar: dict) -> float | None:
    parsed = _parse_et(str(bar.get("time") or ""))
    if parsed is None:
        return None
    return parsed.timestamp()


def _contiguous_enough(older: list[dict], newer: list[dict]) -> bool:
    """True when the newer window abuts or overlaps the older page.

    A weekend gap is fine. A multi-month hole between a history first page
    and ``get_cur_kline`` is not — keep only the recent window.
    """
    if not older or not newer:
        return True
    left = _bar_epoch(older[-1])
    right = _bar_epoch(newer[0])
    if left is None or right is None:
        return False
    if right <= left:
        return True
    return (right - left) <= MAX_MERGE_GAP_SECONDS


class _ClosedGateway:
    """Used when the configured host is not local. Never dials out."""

    def subscribe(self, codes: Sequence[str], subtypes: Sequence[str]) -> None:
        raise ObserveFailure("opend_unreachable", "OpenD host is not local")

    def unsubscribe(self, codes: Sequence[str], subtypes: Sequence[str]) -> None:
        return None

    def snapshot(self, codes: Sequence[str]) -> list[dict]:
        raise ObserveFailure("opend_unreachable", "OpenD host is not local")

    def history_kline(self, code: str, kl_type: str, max_count: int = 1000) -> list[dict]:
        raise ObserveFailure("opend_unreachable", "OpenD host is not local")

    def cur_kline(self, code: str, kl_type: str, num: int) -> list[dict]:
        raise ObserveFailure("opend_unreachable", "OpenD host is not local")

    def close(self) -> None:
        return None


def build_adapter(
    *,
    gateway: Any = None,
    env: dict[str, str] | None = None,
    position_symbols: PositionProvider | None = None,
) -> FutuObserveAdapter:
    return FutuObserveAdapter.from_env(env, gateway=gateway, position_symbols=position_symbols)
