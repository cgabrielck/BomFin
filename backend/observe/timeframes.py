"""Desk timeframe tokens → official Futu KLType, plus labeled 5h / 3d / 5d.

Native names are the OpenAPI v10.12 KLType set. 5h, 3d, and 5d are not
members of that set; they are folded from K_60M and K_DAY.
"""
from __future__ import annotations

from dataclasses import dataclass

# Official native KLType. Do not add names that page does not list.
NATIVE_KL = {
    "1m": "K_1M",
    "3m": "K_3M",
    "5m": "K_5M",
    "10m": "K_10M",
    "15m": "K_15M",
    "30m": "K_30M",
    "1h": "K_60M",
    "60m": "K_60M",
    "2h": "K_120M",
    "3h": "K_180M",
    "4h": "K_240M",
    "1d": "K_DAY",
    "1w": "K_WEEK",
    "1mo": "K_MON",
    "1q": "K_QUARTER",
    "1y": "K_YEAR",
}

# source_kl is the native series we actually request. group is consecutive bars.
SYNTHESIZED = {
    "5h": {"source_kl": "K_60M", "group": 5, "span_trading_days": None},
    "3d": {"source_kl": "K_DAY", "group": 3, "span_trading_days": 3},
    "5d": {"source_kl": "K_DAY", "group": 5, "span_trading_days": 5},
}

_DAILY_KL = frozenset({"K_DAY", "K_WEEK", "K_MON", "K_QUARTER", "K_YEAR"})


@dataclass(frozen=True)
class Timeframe:
    token: str
    bar_origin: str
    kl_type: str | None
    synthesized_from: str | None
    source_kl: str
    group: int
    span_trading_days: int | None
    intraday: bool


def allowed_timeframes() -> tuple[str, ...]:
    return tuple(list(NATIVE_KL) + list(SYNTHESIZED))


def resolve_timeframe(token: str) -> Timeframe:
    key = (token or "").strip().lower()
    if key in NATIVE_KL:
        kl = NATIVE_KL[key]
        return Timeframe(
            token=key,
            bar_origin="native",
            kl_type=kl,
            synthesized_from=None,
            source_kl=kl,
            group=1,
            span_trading_days=None,
            intraday=kl not in _DAILY_KL,
        )
    spec = SYNTHESIZED.get(key)
    if spec is None:
        raise ValueError(f"Unsupported timeframe: {token}")
    return Timeframe(
        token=key,
        bar_origin="synthesized",
        kl_type=None,
        synthesized_from=spec["source_kl"],
        source_kl=spec["source_kl"],
        group=int(spec["group"]),
        span_trading_days=spec["span_trading_days"],
        intraday=key == "5h",
    )


def synthesize(bars: list[dict], group: int) -> list[dict]:
    """Fold consecutive real bars. Missing OHLC is not filled from a neighbour."""
    if group <= 1:
        return list(bars)
    ordered = sorted(bars, key=lambda bar: str(bar.get("time") or ""))
    folded: list[dict] = []
    for start in range(0, len(ordered), group):
        chunk = ordered[start : start + group]
        if not chunk:
            continue
        volumes = [bar.get("volume") for bar in chunk]
        volume = None if any(item is None for item in volumes) else int(sum(volumes))
        folded.append(
            {
                "time": chunk[-1]["time"],
                "open": chunk[0]["open"],
                "high": max(bar["high"] for bar in chunk),
                "low": min(bar["low"] for bar in chunk),
                "close": chunk[-1]["close"],
                "volume": volume,
            }
        )
    return folded
