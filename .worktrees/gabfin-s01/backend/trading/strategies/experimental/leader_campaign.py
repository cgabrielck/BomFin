"""Leader Campaign (``leader_campaign``) experimental Harness playbook.

The four setup classifiers follow the rule text in draft PR #45
(``docs/BOOMBOOM_NEW_STRATEGY.md``, strategy id ``leader_campaign``) and match
the E-STAIR-0 census helpers on draft PR #46. This branch does not depend on
either unmerged PR. The official census VALID total on that 74-name window
remains 0. This module does not re-run the census and does not start an
E-STAIR-1 return backtest.

Not loaded unless ``BOOMBOOM_EXPERIMENTAL_STRATEGIES`` is on (default off).
Not the product default. Not an AI Mode option. A missing fundamental score
is ``fund_missing`` — never filled with 50 or 55. Missing SPY is
``market_unavailable``. There is no hot-path writer for these constants.

This file must not import ``OrderManager``, ``place_desk_order``, or an
Alpaca submit client. A Signal is not an order.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from backend.utils.us_equity_calendar import filter_us_equity_daily_bars

from backend.trading.strategies.base import ExitSignal, Signal, StrategyBase
from backend.trading.strategies.experimental import experimental_strategies_enabled

EXPERIMENT_ID = "E-STAIR-0"
STRATEGY_ID = "leader_campaign"

# Design band from §5.8. Official VALID must be strictly inside it.
BAND_LOW_EXCLUSIVE = 96
BAND_HIGH_EXCLUSIVE = 1440

SETUPS: Tuple[str, ...] = ("gap_up", "pivot_break", "pocket_pivot", "ma_pullback")
PRIORITY: Tuple[str, ...] = SETUPS

# Named skips that can be the single label for a symbol-session.
# Template failures (not Stage 2, RS, price floor) stay in the per-setup
# table and collapse to ``no_setup`` so they are not merged into a pattern veto.
NAMED_PRECEDENCE: Tuple[str, ...] = (
    "fund_missing",
    "fund_below_min",
    "market_pressure",
    "stop_too_wide",
    "extended",
    "handle_deep",
    "volume_not_dry",
    "volume_weak",
    "above_ma_band",
    "prior_run",
    "regime_block",
)

PIVOT_FAIL_RANK = {
    "stop_too_wide": 60,
    "extended": 50,
    "volume_weak": 40,
    "volume_not_dry": 30,
    "handle_deep": 20,
    "no_setup": 10,
    "history_short": 5,
}

MIN_GAP_BARS = 64
MIN_LEADER_BARS = 252
FUND_MIN = 50.0
PRICE_FLOOR = 10.0
DIST_DECLINE = 0.002
DIST_WINDOW = 25
DIST_MIN_COUNT = 5
ADX_MARK = 30.0


def band_verdict(valid_total: int) -> str:
    """Return the pre-committed §5.8 decision. Does not run a backtest."""
    total = int(valid_total)
    if total <= BAND_LOW_EXCLUSIVE:
        return "stop_sparse"
    if total >= BAND_HIGH_EXCLUSIVE:
        return "stop_noisy"
    return "propose_e_stair_1"


def in_design_band(valid_total: int) -> bool:
    return band_verdict(valid_total) == "propose_e_stair_1"


def product_path_enabled() -> bool:
    """False. This module has no order path.

    The experimental flag may let the worker load the playbook. It does not
    let this file submit, and it does not change RiskLimits or kelly_scale.
    """
    return False


def fund_gate(score: Optional[float]) -> str:
    """``valid`` only when a real score is present and >= 50.

    ``None`` is ``fund_missing``, not a default of 50 and not ``fund_below_min``.
    """
    if score is None:
        return "fund_missing"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "fund_missing"
    if not np.isfinite(value):
        return "fund_missing"
    if value < FUND_MIN:
        return "fund_below_min"
    return "valid"


def stop_too_wide(
    close: float,
    stop: float,
    atr: float,
    *,
    pct_cap: Optional[float],
    atr_mult: float,
) -> bool:
    """True when the stop distance is strictly wider than a written cap.

    Equality passes. Pivot / pullback / pocket use ``pct_cap=0.08`` and
    ``atr_mult=1``. Gap-up uses no percent cap and ``atr_mult=1.5``.
    """
    if close <= 0 or stop >= close:
        return True
    if not np.isfinite(atr) or atr <= 0:
        return True
    dist = (close - stop) / close
    atr_frac = atr / close
    if pct_cap is not None and dist > pct_cap:
        return True
    if dist > atr_mult * atr_frac:
        return True
    return False


def collapse_day(statuses: Mapping[str, str]) -> str:
    """One label per symbol-session. Priority: gap, pivot, pocket, pullback."""
    for name in PRIORITY:
        if statuses.get(name) == "valid":
            return name
    for code in NAMED_PRECEDENCE:
        if any(statuses.get(name) == code for name in PRIORITY):
            return code
    if statuses and all(statuses.get(name) == "history_short" for name in PRIORITY):
        return "history_short"
    return "no_setup"


def market_blocks_setup(state: str, setup: str) -> bool:
    if state == "market_correction":
        return True
    if state == "market_pressure" and setup in {"pivot_break", "gap_up"}:
        return True
    return False


def _day(value: Any) -> date:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/New_York").tz_localize(None)
    return ts.normalize().date()


def _wilder_from(values: np.ndarray, length: int, start_index: int = 1) -> np.ndarray:
    out = np.full(len(values), np.nan)
    end = start_index + length - 1
    if end >= len(values):
        return out
    window = values[start_index : end + 1]
    if np.isnan(window).any():
        return out
    out[end] = float(np.mean(window))
    prev = out[end]
    for i in range(end + 1, len(values)):
        current = values[i]
        if not np.isfinite(current) or not np.isfinite(prev):
            out[i] = np.nan
            prev = np.nan
            continue
        prev = (prev * (length - 1) + float(current)) / length
        out[i] = prev
    return out


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n, dtype=float)
    if n:
        tr[0] = float(high[0] - low[0])
    for i in range(1, n):
        tr[i] = max(
            float(high[i] - low[i]),
            abs(float(high[i] - close[i - 1])),
            abs(float(low[i] - close[i - 1])),
        )
    return _wilder_from(tr, length, start_index=1)


def wilder_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    """Welles Wilder ADX. Recorded for pullbacks. Not an entry gate."""
    n = len(close)
    tr = np.zeros(n, dtype=float)
    plus_dm = np.zeros(n, dtype=float)
    minus_dm = np.zeros(n, dtype=float)
    if n:
        tr[0] = float(high[0] - low[0])
    for i in range(1, n):
        up = float(high[i] - high[i - 1])
        down = float(low[i - 1] - low[i])
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(
            float(high[i] - low[i]),
            abs(float(high[i] - close[i - 1])),
            abs(float(low[i] - close[i - 1])),
        )
    atr = _wilder_from(tr, length, start_index=1)
    plus_s = _wilder_from(plus_dm, length, start_index=1)
    minus_s = _wilder_from(minus_dm, length, start_index=1)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    ok = np.isfinite(atr) & (atr > 0) & np.isfinite(plus_s) & np.isfinite(minus_s)
    plus_di[ok] = 100.0 * plus_s[ok] / atr[ok]
    minus_di[ok] = 100.0 * minus_s[ok] / atr[ok]
    denom = plus_di + minus_di
    dx = np.full(n, np.nan)
    dok = np.isfinite(denom) & (denom > 0)
    dx[dok] = 100.0 * np.abs(plus_di[dok] - minus_di[dok]) / denom[dok]
    adx = np.full(n, np.nan)
    finite = np.flatnonzero(np.isfinite(dx))
    if len(finite) < length:
        return adx
    start = int(finite[0])
    seed_at = start + length - 1
    if seed_at >= n or not np.all(np.isfinite(dx[start : seed_at + 1])):
        return adx
    adx[seed_at] = float(np.mean(dx[start : seed_at + 1]))
    prev = adx[seed_at]
    for i in range(seed_at + 1, n):
        if not np.isfinite(dx[i]) or not np.isfinite(prev):
            adx[i] = np.nan
            prev = np.nan
            continue
        prev = (prev * (length - 1) + float(dx[i])) / length
        adx[i] = prev
    return adx


def distribution_flags(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """SPY distribution day: decline strictly greater than 0.2% and volume up.

    A stalling day (higher volume, flat or up close) is not counted.
    """
    flags = np.zeros(len(close), dtype=bool)
    for i in range(1, len(close)):
        prev = float(close[i - 1])
        if prev <= 0:
            continue
        declined = float(close[i]) < prev * (1.0 - DIST_DECLINE)
        vol_up = float(volume[i]) > float(volume[i - 1])
        flags[i] = bool(declined and vol_up)
    return flags


def build_market_states(spy: pd.DataFrame) -> Dict[date, str]:
    """SPY-only market state. Nasdaq is not consulted. No follow-through buy."""
    frame = _ohlcv(spy)
    if frame is None or len(frame) < 200:
        return {}
    close = frame["Close"].to_numpy(dtype=float)
    volume = frame["Volume"].to_numpy(dtype=float)
    sma200 = pd.Series(close).rolling(200, min_periods=200).mean().to_numpy()
    flags = distribution_flags(close, volume)
    states: Dict[date, str] = {}
    for i, ts in enumerate(frame.index):
        if not np.isfinite(sma200[i]):
            continue
        price = float(close[i])
        anchor = float(sma200[i])
        if price < anchor:
            state = "market_correction"
        elif price > anchor and i >= DIST_WINDOW - 1:
            window = flags[i - (DIST_WINDOW - 1) : i + 1]
            state = "market_pressure" if int(window.sum()) >= DIST_MIN_COUNT else "market_uptrend"
        else:
            state = "market_uptrend"
        states[_day(ts)] = state
    return states


class SymbolFrame:
    def __init__(self, frame: pd.DataFrame):
        self.dates: List[date] = [_day(ts) for ts in frame.index]
        self.date_to_i: Dict[date, int] = {day: i for i, day in enumerate(self.dates)}
        self.open = frame["Open"].to_numpy(dtype=float)
        self.high = frame["High"].to_numpy(dtype=float)
        self.low = frame["Low"].to_numpy(dtype=float)
        self.close = frame["Close"].to_numpy(dtype=float)
        self.volume = frame["Volume"].to_numpy(dtype=float)
        close_s = pd.Series(self.close)
        volume_s = pd.Series(self.volume)
        high_s = pd.Series(self.high)
        low_s = pd.Series(self.low)
        self.sma10 = close_s.rolling(10, min_periods=10).mean().to_numpy()
        self.sma20 = close_s.rolling(20, min_periods=20).mean().to_numpy()
        self.sma50 = close_s.rolling(50, min_periods=50).mean().to_numpy()
        self.sma150 = close_s.rolling(150, min_periods=150).mean().to_numpy()
        self.sma200 = close_s.rolling(200, min_periods=200).mean().to_numpy()
        self.vol20_prev = volume_s.rolling(20, min_periods=20).mean().shift(1).to_numpy()
        self.vol50_prev = volume_s.rolling(50, min_periods=50).mean().shift(1).to_numpy()
        self.high252 = high_s.rolling(252, min_periods=252).max().to_numpy()
        self.low252 = low_s.rolling(252, min_periods=252).min().to_numpy()
        self.atr14 = wilder_atr(self.high, self.low, self.close, 14)
        self.adx14 = wilder_adx(self.high, self.low, self.close, 14)


def _ohlcv(frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    work = frame.copy()
    if isinstance(work.columns, pd.MultiIndex):
        work.columns = work.columns.get_level_values(0)
    needed = [col for col in ("Open", "High", "Low", "Close", "Volume") if col in work.columns]
    if "Close" not in needed or "Volume" not in needed:
        return None
    work = work[needed].apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if work.empty:
        return None
    work = filter_us_equity_daily_bars(work)
    if work.empty:
        return None
    return work


def prepare_symbol(frame: Optional[pd.DataFrame]) -> Optional[SymbolFrame]:
    clean = _ohlcv(frame)
    if clean is None or clean.empty:
        return None
    return SymbolFrame(clean)


def spy_close_map(spy: pd.DataFrame) -> Dict[date, float]:
    clean = _ohlcv(spy)
    if clean is None:
        return {}
    return {_day(ts): float(px) for ts, px in clean["Close"].items()}


def excess_return(prep: SymbolFrame, spy_close: Mapping[date, float], i: int, lookback: int) -> Optional[float]:
    """Stock return minus SPY return over ``lookback`` trading bars.

    Same endpoints as ``relative_strength_vs_spy`` (``close[i] / close[i-lookback] - 1``).
    This is not an IBD RS Rating.
    """
    if i < lookback:
        return None
    start_day = prep.dates[i - lookback]
    end_day = prep.dates[i]
    spy_start = spy_close.get(start_day)
    spy_end = spy_close.get(end_day)
    stock_start = float(prep.close[i - lookback])
    stock_end = float(prep.close[i])
    if spy_start is None or spy_end is None or spy_start <= 0 or stock_start <= 0:
        return None
    if not np.isfinite(spy_end) or not np.isfinite(stock_end):
        return None
    return (stock_end / stock_start - 1.0) - (float(spy_end) / float(spy_start) - 1.0)


def leader_template(prep: SymbolFrame, spy_close: Mapping[date, float], i: int) -> Optional[str]:
    """Price-template result. ``None`` means the template passed.

    Fundamental score is not applied here.
    """
    if i < MIN_LEADER_BARS:
        return "history_short"
    close = float(prep.close[i])
    sma50 = float(prep.sma50[i])
    sma150 = float(prep.sma150[i])
    sma200 = float(prep.sma200[i])
    sma200_prev = float(prep.sma200[i - 21])
    high252 = float(prep.high252[i])
    low252 = float(prep.low252[i])
    values = (close, sma50, sma150, sma200, sma200_prev, high252, low252)
    if not all(np.isfinite(v) for v in values) or min(close, high252, low252) <= 0:
        return "history_short"
    if close < PRICE_FLOOR:
        return "price_floor"
    if not (close > sma50 > sma150 > sma200):
        return "not_stage2"
    if not (sma200 > sma200_prev):
        return "sma200_flat"
    off_high = (high252 - close) / high252
    if not (close >= low252 * 1.30 and off_high <= 0.25):
        return "leader_position"
    rs63 = excess_return(prep, spy_close, i, 63)
    rs126 = excess_return(prep, spy_close, i, 126)
    if rs63 is None or rs126 is None or rs63 <= 0 or rs126 <= 0:
        return "rs_weak"
    return None


def pivot_window_status(
    prep: SymbolFrame,
    i: int,
    base_len: int,
    handle_len: int,
) -> str:
    """One base/handle pair. ``pass`` means price, volume, and stop all clear.

    Handle depth is ``(base high − handle low) / base high``. The handle is the
    last ``handle_len`` sessions of the base. Volume averages exclude the signal day.
    """
    if handle_len >= base_len or i - base_len < 0:
        return "no_setup"
    base_start = i - base_len
    handle_start = i - handle_len
    base_high = float(np.max(prep.high[base_start:i]))
    base_low = float(np.min(prep.low[base_start:i]))
    close = float(prep.close[i])
    if not np.isfinite(base_high) or base_high <= 0 or base_low <= 0 or not np.isfinite(close):
        return "no_setup"
    if close <= base_high:
        return "no_setup"
    handle_high = float(np.max(prep.high[handle_start:i]))
    handle_low = float(np.min(prep.low[handle_start:i]))
    prior_high = float(np.max(prep.high[base_start:handle_start]))
    prior_low = float(np.min(prep.low[base_start:handle_start]))
    if not (handle_high - handle_low < prior_high - prior_low and handle_low > (base_high + base_low) / 2.0):
        return "no_setup"
    if (base_high - handle_low) / base_high > 0.12:
        return "handle_deep"
    half = base_len // 2
    first_vol = float(np.mean(prep.volume[base_start : base_start + half]))
    handle_vol = float(np.mean(prep.volume[handle_start:i]))
    if not (np.isfinite(first_vol) and first_vol > 0 and np.isfinite(handle_vol) and handle_vol < first_vol):
        return "volume_not_dry"
    vol50 = float(prep.vol50_prev[i])
    if not (np.isfinite(vol50) and vol50 > 0 and float(prep.volume[i]) >= 1.4 * vol50):
        return "volume_weak"
    if close > base_high * 1.05:
        return "extended"
    if stop_too_wide(close, handle_low, float(prep.atr14[i]), pct_cap=0.08, atr_mult=1.0):
        return "stop_too_wide"
    return "pass"


def _best_pivot(prep: SymbolFrame, i: int) -> Tuple[str, Dict[str, Any]]:
    if float(prep.close[i]) <= float(np.max(prep.high[i - 25 : i])):
        return "no_setup", {}
    best_code = "no_setup"
    best_rank = 0
    chosen: Optional[Dict[str, Any]] = None
    chosen_key: Optional[Tuple[int, int]] = None
    for base_len in range(25, 66):
        for handle_len in range(5, 16):
            code = pivot_window_status(prep, i, base_len, handle_len)
            if code == "pass":
                handle_low = float(np.min(prep.low[i - handle_len : i]))
                base_high = float(np.max(prep.high[i - base_len : i]))
                key = (base_len, -handle_len)
                if chosen_key is None or key > chosen_key:
                    chosen_key = key
                    chosen = {
                        "base_len": base_len,
                        "handle_len": handle_len,
                        "stop": handle_low,
                        "pivot": base_high,
                    }
                continue
            rank = PIVOT_FAIL_RANK.get(code, 0)
            if rank > best_rank:
                best_rank = rank
                best_code = code
    if chosen is not None:
        return "pass", chosen
    return best_code, {}


def _vcp_also_true(prep: SymbolFrame, i: int) -> bool:
    """Existing VCP detector on bars up to and including the signal. No future bars."""
    start = max(0, i - 119)
    window = pd.DataFrame(
        {
            "High": prep.high[start : i + 1],
            "Low": prep.low[start : i + 1],
            "Close": prep.close[start : i + 1],
            "Volume": prep.volume[start : i + 1],
        }
    )
    try:
        from backend.trading.strategies.aggressive import detect_vcp

        return bool(detect_vcp(window).get("found"))
    except Exception:
        return False


def _finish_structural(
    code: str,
    notes: Dict[str, Any],
    fund_score: Optional[float],
    market: str,
    setup: str,
) -> Tuple[str, Dict[str, Any]]:
    if code != "pass":
        return code, notes
    notes = dict(notes)
    notes["structural"] = True
    notes["fund_status"] = fund_gate(fund_score)
    # Market is read before the score. A finished pivot or gap on a pressure
    # day is market_pressure, not fund_missing, so the two codes stay apart.
    if market_blocks_setup(market, setup):
        return "regime_block" if market == "market_correction" else "market_pressure", notes
    if notes["fund_status"] != "valid":
        return notes["fund_status"], notes
    return "valid", notes


def classify_pivot(
    prep: SymbolFrame,
    spy_close: Mapping[date, float],
    i: int,
    market: str,
    fund_score: Optional[float],
    *,
    template: Optional[str] = None,
    check_vcp: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    if template is None:
        template = leader_template(prep, spy_close, i)
    if template:
        return template, {}
    code, notes = _best_pivot(prep, i)
    if code == "pass" and check_vcp and _vcp_also_true(prep, i):
        notes = dict(notes)
        notes["vcp_also_true"] = True
    return _finish_structural(code, notes, fund_score, market, "pivot_break")


def classify_pullback(
    prep: SymbolFrame,
    spy_close: Mapping[date, float],
    i: int,
    market: str,
    fund_score: Optional[float],
    *,
    template: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    if template is None:
        template = leader_template(prep, spy_close, i)
    if template:
        return template, {}
    above = 0
    for j in range(i - 20, i):
        sma = float(prep.sma20[j])
        if np.isfinite(sma) and float(prep.close[j]) > sma:
            above += 1
    earlier = float(prep.close[i - 21])
    prior = float(prep.close[i - 1])
    if earlier <= 0 or not np.isfinite(earlier) or not np.isfinite(prior):
        return "history_short", {}
    trail_return = prior / earlier - 1.0
    if above < 15 or trail_return <= 0:
        return "no_setup", {}
    sma20 = float(prep.sma20[i])
    close = float(prep.close[i])
    low = float(prep.low[i])
    if not np.isfinite(sma20) or sma20 <= 0:
        return "history_short", {}
    if abs(low - sma20) / sma20 > 0.01 or close <= sma20:
        return "no_setup", {}
    if close > sma20 * 1.08:
        return "above_ma_band", {}
    vol20 = float(prep.vol20_prev[i])
    if not (np.isfinite(vol20) and vol20 > 0):
        return "history_short", {}
    if float(prep.volume[i]) > vol20:
        return "volume_not_dry", {}
    recent_low = float(np.min(prep.low[i - 2 : i + 1]))
    stop = min(recent_low, sma20 * 0.97)
    if stop_too_wide(close, stop, float(prep.atr14[i]), pct_cap=0.08, atr_mult=1.0):
        return "stop_too_wide", {}
    adx = float(prep.adx14[i])
    notes = {
        "stop": stop,
        "adx14": None if not np.isfinite(adx) else adx,
        "adx30": bool(np.isfinite(adx) and adx > ADX_MARK),
    }
    return _finish_structural("pass", notes, fund_score, market, "ma_pullback")


def classify_pocket(
    prep: SymbolFrame,
    spy_close: Mapping[date, float],
    i: int,
    market: str,
    fund_score: Optional[float],
    *,
    template: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    if template is None:
        template = leader_template(prep, spy_close, i)
    if template:
        return template, {}
    close = float(prep.close[i])
    open_ = float(prep.open[i])
    low = float(prep.low[i])
    sma10 = float(prep.sma10[i])
    sma50 = float(prep.sma50[i])
    if not (np.isfinite(close) and np.isfinite(open_) and close > open_ and np.isfinite(sma10) and close > sma10):
        return "no_setup", {}
    near10 = np.isfinite(sma10) and sma10 > 0 and abs(low - sma10) / sma10 <= 0.02
    near50 = np.isfinite(sma50) and sma50 > 0 and abs(low - sma50) / sma50 <= 0.02
    if not (near10 or near50):
        return "no_setup", {}
    if i < 11:
        return "history_short", {}
    down_vols: List[float] = []
    for j in range(i - 10, i):
        if float(prep.close[j]) < float(prep.close[j - 1]):
            down_vols.append(float(prep.volume[j]))
    need = max(down_vols) if down_vols else float(np.max(prep.volume[i - 10 : i]))
    if not (np.isfinite(need) and float(prep.volume[i]) > need):
        return "volume_weak", {}
    if stop_too_wide(close, low, float(prep.atr14[i]), pct_cap=0.08, atr_mult=1.0):
        return "stop_too_wide", {}
    return _finish_structural("pass", {"stop": low}, fund_score, market, "pocket_pivot")


def classify_gap(
    prep: SymbolFrame,
    i: int,
    market: str,
    fund_score: Optional[float],
) -> Tuple[str, Dict[str, Any]]:
    """Gap-up does not require the Stage-2 template. No earnings calendar is loaded."""
    if i < MIN_GAP_BARS:
        return "history_short", {}
    prev = float(prep.close[i - 1])
    anchor = float(prep.close[i - 1 - 63])
    if prev <= 0 or anchor <= 0 or not np.isfinite(prev) or not np.isfinite(anchor):
        return "history_short", {}
    open_ = float(prep.open[i])
    high = float(prep.high[i])
    low = float(prep.low[i])
    close = float(prep.close[i])
    if not all(np.isfinite(v) for v in (open_, high, low, close)):
        return "no_setup", {}
    open_gap = open_ / prev - 1.0
    close_gap = close / prev - 1.0
    upper_half = close >= (high + low) / 2.0
    if not (open_gap >= 0.10 or (close_gap >= 0.08 and upper_half)):
        return "no_setup", {}
    prior_run = prev / anchor - 1.0
    if prior_run >= 0.50:
        return "prior_run", {}
    vol50 = float(prep.vol50_prev[i])
    if not (np.isfinite(vol50) and vol50 > 0 and float(prep.volume[i]) >= 1.5 * vol50):
        return "volume_weak", {}
    if close < PRICE_FLOOR:
        return "price_floor", {}
    if stop_too_wide(close, low, float(prep.atr14[i]), pct_cap=None, atr_mult=1.5):
        return "stop_too_wide", {}
    notes = {"stop": low, "catalyst": "catalyst_unconfirmed"}
    return _finish_structural("pass", notes, fund_score, market, "gap_up")



# --- Harness playbook. Classifiers above are the E-STAIR-0 rules. ---

# Sizing inputs for the existing half-Kelly formula in the worker.
# They are not a measured edge and they do not change kelly_scale (0.5).
SIZING_WIN_RATE = 0.42
SIZING_WIN_PCT = 0.18
SIZING_LOSS_PCT = 0.07

_REAL_FUND_SOURCES = frozenset({"last_scan", "last_scan_stale", "cache"})
_LEADER_META_KEYS = (
    "setup",
    "pivot",
    "entry_date",
    "r_unit",
    "catalyst",
    "bars_held",
    "last_bar_day",
    "max_r",
    "adx30",
)


def coerce_fund_score(info: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Return a real score, or None when the book only filled a placeholder.

    Sources ``default`` and ``missing`` carry score 50 with no raw score.
    That 50 is not a fundamental result. Neutral 55 is not invented either.
    """
    if not info:
        return None
    source = str(info.get("source") or "")
    if source not in _REAL_FUND_SOURCES:
        return None
    raw = info.get("raw_score")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value):
        return None
    return value


def _optional_fund(score: Any) -> Optional[float]:
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value):
        return None
    return value


def evaluate_latest(
    frame: Optional[pd.DataFrame],
    spy: Optional[pd.DataFrame],
    fund_score: Optional[float],
) -> Tuple[str, Dict[str, Any]]:
    """One symbol, last bar. Returns a setup id or a skip code. Not an order.

    Same priority and same gates as the E-STAIR-0 census day loop.
    Does not call a backtest and does not read ``band_verdict``.
    """
    prep = prepare_symbol(frame)
    if prep is None or len(prep.close) == 0:
        return "no_price", {}
    i = len(prep.close) - 1
    if not np.isfinite(prep.close[i]):
        return "no_price", {}
    if i < MIN_GAP_BARS:
        return "history_short", {}
    if spy is None:
        return "market_unavailable", {}
    market = build_market_states(spy)
    spy_px = spy_close_map(spy)
    state = market.get(prep.dates[i])
    if state is None:
        return "market_unavailable", {}
    if state == "market_correction":
        return "regime_block", {"market": state}
    if i < MIN_LEADER_BARS:
        template: Optional[str] = "history_short"
    else:
        template = leader_template(prep, spy_px, i)
    notes: Dict[str, Dict[str, Any]] = {}
    statuses: Dict[str, str] = {}
    statuses["gap_up"], notes["gap_up"] = classify_gap(prep, i, state, fund_score)
    statuses["pivot_break"], notes["pivot_break"] = classify_pivot(
        prep, spy_px, i, state, fund_score, template=template
    )
    statuses["pocket_pivot"], notes["pocket_pivot"] = classify_pocket(
        prep, spy_px, i, state, fund_score, template=template
    )
    statuses["ma_pullback"], notes["ma_pullback"] = classify_pullback(
        prep, spy_px, i, state, fund_score, template=template
    )
    label = collapse_day(statuses)
    chosen: Dict[str, Any] = {}
    if label in notes and notes[label]:
        chosen = dict(notes[label])
    else:
        for name in PRIORITY:
            if statuses.get(name) == label and notes.get(name):
                chosen = dict(notes[name])
                break
    chosen["market"] = state
    chosen["statuses"] = statuses
    chosen["label"] = label
    chosen["asof"] = prep.dates[i].isoformat()
    return label, chosen


def _last_sma(df: pd.DataFrame, length: int) -> Optional[float]:
    if df is None or len(df) < length or "Close" not in getattr(df, "columns", []):
        return None
    value = float(pd.to_numeric(df["Close"], errors="coerce").iloc[-length:].mean())
    if not np.isfinite(value):
        return None
    return value


def _bar_day(df: pd.DataFrame) -> Optional[str]:
    if df is None or len(df) == 0:
        return None
    try:
        ts = pd.Timestamp(df.index[-1])
    except Exception:
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/New_York").tz_localize(None)
    return ts.normalize().date().isoformat()


def _signal_from(
    ticker: str,
    frame: pd.DataFrame,
    label: str,
    notes: Mapping[str, Any],
    fund_score: Optional[float],
) -> Optional[Signal]:
    if label not in SETUPS:
        return None
    stop = notes.get("stop")
    prep = prepare_symbol(frame)
    if prep is None or stop is None:
        return None
    close = float(prep.close[-1])
    try:
        stop_f = float(stop)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(close) or not np.isfinite(stop_f) or stop_f >= close:
        return None
    risk = close - stop_f
    asof = prep.dates[-1].isoformat()
    meta: Dict[str, Any] = {
        "setup": label,
        "experiment": EXPERIMENT_ID,
        "playbook": STRATEGY_ID,
        "valid": True,
        "alpha_claimed": False,
        "stop": round(stop_f, 4),
        "market": notes.get("market"),
        "fund_score": fund_score,
        "fund_filled": False,
        "vcp_also_true": bool(notes.get("vcp_also_true")),
        "adx30": notes.get("adx30"),
        "catalyst": notes.get("catalyst"),
        "pivot": notes.get("pivot"),
        "entry_date": asof,
        "r_unit": risk,
        "bars_held": 0,
        "last_bar_day": asof,
        "max_r": 0.0,
        "sizing_inputs": "unmeasured_placeholder_for_existing_half_kelly",
    }
    return Signal(
        ticker=ticker,
        side="buy",
        strategy_id=STRATEGY_ID,
        confidence=0.5,
        reason=(
            f"leader_campaign {label} VALID "
            f"(E-STAIR-0 rules, not a measured edge; market={notes.get('market')})"
        ),
        entry_price=round(close, 4),
        stop_loss_price=round(stop_f, 4),
        # Structural exits live in check_exit. A bracket target would sell
        # for a reason the written rules do not have.
        take_profit_price=None,  # type: ignore[arg-type]
        avg_win_pct=SIZING_WIN_PCT,
        avg_loss_pct=SIZING_LOSS_PCT,
        meta=meta,
    )


class LeaderCampaignStrategy(StrategyBase):
    """Experimental playbook. Not the product default.

    ``generate_signal`` returns a Signal only when the operator flag is on
    and the last bar is an official VALID. Otherwise the worker records a
    skip code. This class does not size orders and does not submit them.
    """

    strategy_id = STRATEGY_ID
    display_name = "領漲戰役 Leader Campaign（實驗）"
    risk_profile = "experimental"
    expected_win_rate = SIZING_WIN_RATE
    expected_win_pct = SIZING_WIN_PCT
    expected_loss_pct = SIZING_LOSS_PCT
    history_period = "2y"
    entries_enabled = True
    rejects_synthetic_fund_score = True
    coerce_fund_score = staticmethod(coerce_fund_score)

    def __init__(self) -> None:
        self._spy_frame: Optional[pd.DataFrame] = None
        self.spy_close: Optional[pd.Series] = None
        self._bound_meta: Dict[str, Any] = {}

    def set_spy_frame(self, spy_df: Optional[pd.DataFrame]) -> None:
        """Full SPY OHLCV. Close-only is not enough for distribution days."""
        self._spy_frame = spy_df
        if isinstance(spy_df, pd.DataFrame) and "Close" in spy_df.columns:
            self.spy_close = spy_df["Close"]
        else:
            self.spy_close = None

    def set_spy_close(self, spy_close: Optional[pd.Series]) -> None:
        """Compatibility hook. A close series cannot score distribution days."""
        self.spy_close = spy_close
        self._spy_frame = None

    def bind_position_meta(self, meta: Optional[Dict[str, Any]]) -> None:
        self._bound_meta = meta if isinstance(meta, dict) else {}

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def _held(self, ticker: str, current_positions: List[Dict[str, Any]]) -> bool:
        want = str(ticker or "").upper()
        for pos in current_positions or []:
            symbol = str(pos.get("symbol") or pos.get("ticker") or "").upper()
            if symbol and symbol == want:
                return True
        return False

    def _decide(
        self,
        ticker: str,
        df: pd.DataFrame,
        fundamental_score: Any,
        current_positions: List[Dict[str, Any]],
    ) -> Tuple[str, Dict[str, Any]]:
        if self._held(ticker, current_positions):
            return "already_held", {}
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return "no_price", {}
        return evaluate_latest(df, self._spy_frame, _optional_fund(fundamental_score))

    def diagnose_entry(
        self,
        ticker: str,
        df: pd.DataFrame,
        fundamental_score: float,
        llm_signal: Optional[str],
        current_positions: List[Dict[str, Any]],
    ) -> Optional[str]:
        del llm_signal  # The written rules do not use an LLM as an entry.
        if not experimental_strategies_enabled():
            return "experimental_disabled"
        label, _notes = self._decide(ticker, df, fundamental_score, current_positions)
        if label in SETUPS:
            return None
        return label or "no_setup"

    def generate_signal(
        self,
        ticker: str,
        df: pd.DataFrame,
        fundamental_score: float,
        llm_signal: Optional[str],
        current_positions: List[Dict[str, Any]],
    ) -> Optional[Signal]:
        del llm_signal
        if not experimental_strategies_enabled():
            return None
        label, notes = self._decide(ticker, df, fundamental_score, current_positions)
        if label not in SETUPS:
            return None
        return _signal_from(ticker, df, label, notes, _optional_fund(fundamental_score))

    def check_exit(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        df: pd.DataFrame,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> Optional[ExitSignal]:
        """Written exits. No bracket target. No constant mutation.

        In-memory position meta (setup, R, bar count) is process state.
        A restart that loses it falls back to the stop and a close under SMA50.
        """
        del take_profit_price
        meta = self._bound_meta if isinstance(self._bound_meta, dict) else {}
        try:
            close = float(current_price)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(close):
            return None
        try:
            stop = float(stop_loss_price)
        except (TypeError, ValueError):
            stop = float("nan")
        if np.isfinite(stop) and close <= stop:
            return ExitSignal(ticker=ticker, reason="stop_loss", exit_price=close)

        risk = 0.0
        try:
            risk = float(meta.get("r_unit") or 0.0)
        except (TypeError, ValueError):
            risk = 0.0
        if risk <= 0:
            try:
                risk = float(entry_price) - stop
            except (TypeError, ValueError):
                risk = 0.0
        if risk > 0 and df is not None and len(df):
            try:
                high = float(df["High"].iloc[-1])
            except Exception:
                high = close
            if np.isfinite(high):
                this_r = (high - float(entry_price)) / risk
                prev = 0.0
                try:
                    prev = float(meta.get("max_r") or 0.0)
                except (TypeError, ValueError):
                    prev = 0.0
                if this_r > prev:
                    meta["max_r"] = this_r

        day = _bar_day(df) if df is not None else None
        if day:
            previous = meta.get("last_bar_day")
            if previous and previous != day:
                try:
                    held = int(meta.get("bars_held") or 0)
                except (TypeError, ValueError):
                    held = 0
                meta["bars_held"] = held + 1
            if not previous or previous != day:
                meta["last_bar_day"] = day

        setup = str(meta.get("setup") or "")
        try:
            max_r = float(meta.get("max_r") or 0.0)
        except (TypeError, ValueError):
            max_r = 0.0
        try:
            bars_held = int(meta.get("bars_held") or 0)
        except (TypeError, ValueError):
            bars_held = 0
        sma10 = _last_sma(df, 10)
        sma20 = _last_sma(df, 20)
        sma50 = _last_sma(df, 50)

        def _exit(reason: str) -> ExitSignal:
            return ExitSignal(ticker=ticker, reason=reason, exit_price=close)

        if setup == "pivot_break":
            pivot = meta.get("pivot")
            try:
                if pivot is not None and close < float(pivot):
                    return _exit("pivot_lost")
            except (TypeError, ValueError):
                pass
            if sma50 is not None and close < sma50:
                return _exit("trend_break_sma50")
            return None
        if setup == "ma_pullback":
            if max_r >= 2.0 and sma20 is not None and close < sma20:
                return _exit("trend_break_sma20")
            if max_r < 2.0 and sma50 is not None and close < sma50:
                return _exit("trend_break_sma50")
            return None
        if setup == "pocket_pivot":
            if (sma20 is not None and close < sma20) or (sma50 is not None and close < sma50):
                return _exit("trend_break_sma20" if sma20 is not None and close < sma20 else "trend_break_sma50")
            return None
        if setup == "gap_up":
            if max_r < 1.0 and bars_held >= 5:
                return _exit("time_stop")
            if max_r >= 1.0 and sma10 is not None and close < sma10:
                return _exit("trend_break_sma10")
            return None
        if sma50 is not None and close < sma50:
            return _exit("trend_break_sma50")
        return None


class DisabledLeaderCampaign(StrategyBase):
    """Flag-off stand-in. Same id, no entries, so the worker cannot fall back to adaptive."""

    strategy_id = STRATEGY_ID
    display_name = "領漲戰役 Leader Campaign（實驗旗標關閉）"
    risk_profile = "experimental"
    expected_win_rate = SIZING_WIN_RATE
    expected_win_pct = SIZING_WIN_PCT
    expected_loss_pct = SIZING_LOSS_PCT
    entries_enabled = False
    rejects_synthetic_fund_score = True
    coerce_fund_score = staticmethod(coerce_fund_score)

    def __init__(self) -> None:
        self._bound_meta: Dict[str, Any] = {}

    def bind_position_meta(self, meta: Optional[Dict[str, Any]]) -> None:
        self._bound_meta = meta if isinstance(meta, dict) else {}

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def generate_signal(
        self,
        ticker: str,
        df: pd.DataFrame,
        fundamental_score: float,
        llm_signal: Optional[str],
        current_positions: List[Dict[str, Any]],
    ) -> Optional[Signal]:
        del ticker, df, fundamental_score, llm_signal, current_positions
        return None

    def diagnose_entry(
        self,
        ticker: str,
        df: pd.DataFrame,
        fundamental_score: float,
        llm_signal: Optional[str],
        current_positions: List[Dict[str, Any]],
    ) -> Optional[str]:
        del ticker, df, fundamental_score, llm_signal, current_positions
        return "experimental_disabled"

    def check_exit(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        df: pd.DataFrame,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> Optional[ExitSignal]:
        # Exits still follow the written rules if a paper position is open
        # and the flag was turned off afterwards. Entries stay closed.
        inner = LeaderCampaignStrategy()
        inner.bind_position_meta(self._bound_meta)
        return inner.check_exit(
            ticker,
            entry_price,
            current_price,
            df,
            stop_loss_price,
            take_profit_price,
        )
