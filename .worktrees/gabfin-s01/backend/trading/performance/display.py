"""Seal-gated paper performance claims.

Any total return, vs-SPY, beats-SPY, or annualized figure shown in the UI
must come from :func:`gate_performance_claims`. A Stage-2 seal failure, or
the equivalent (trades or trading days below the seal minima), withholds
those claims:

* ``beats_spy_net`` is never true
* annualized return is ``n/a``
* a short reason is returned (for example trades or days below the minimum)

Snapshots with ``generated_at`` older than :data:`PERFORMANCE_STALE_AFTER_DAYS`
(7 days) are outdated. Callers label them with age. They are not live.

Reads of the paper ledger belong under ``backend/data/``
(``performance_paper.json``, ``worker_heartbeat.json`` / session card).
The Kelly book under repo-root ``data/`` is a portfolio experiment and is
not that paper ledger.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

# Older than this many days → outdated age label, never a live stamp.
PERFORMANCE_STALE_AFTER_DAYS = 7

_DEFAULT_MIN_TRADES = 5
_DEFAULT_MIN_DAYS = 20


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def parse_generated_at(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def snapshot_freshness(
    generated_at: Any,
    *,
    now: Optional[datetime] = None,
    stale_after_days: int = PERFORMANCE_STALE_AFTER_DAYS,
) -> Dict[str, Any]:
    """Age label for a snapshot. Missing or unparseable timestamps are outdated.

    Threshold: ``generated_at`` older than ``stale_after_days`` (default 7).
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    parsed = parse_generated_at(generated_at)
    if parsed is None:
        return {
            "generated_at": None,
            "age_days": None,
            "stale": True,
            "stale_after_days": int(stale_after_days),
            "label": "outdated",
            "live": False,
        }
    age_days = (moment - parsed).days
    stale = (moment - parsed) > timedelta(days=int(stale_after_days))
    label = f"outdated · {age_days}d" if stale else None
    return {
        "generated_at": parsed.isoformat(),
        "age_days": age_days,
        "stale": stale,
        "stale_after_days": int(stale_after_days),
        "label": label,
        "live": False,
    }


def _explicit_seal(snapshot: Mapping[str, Any]) -> Optional[bool]:
    flag = _as_bool(snapshot.get("seal_passed"))
    if flag is not None:
        return flag
    preview = _mapping(snapshot.get("seal_preview"))
    flag = _as_bool(preview.get("passed"))
    if flag is not None:
        return flag
    nested = _mapping(snapshot.get("seal"))
    return _as_bool(nested.get("passed"))


def _counts(snapshot: Mapping[str, Any]) -> tuple[Optional[int], Optional[int], int, int]:
    metrics = _mapping(snapshot.get("metrics"))
    trading = _mapping(snapshot.get("trading"))
    period = _mapping(snapshot.get("period"))
    criteria = _mapping(snapshot.get("criteria"))
    num_trades = _as_int(trading.get("num_trades"))
    if num_trades is None:
        num_trades = _as_int(metrics.get("num_trades"))
    if num_trades is None:
        num_trades = _as_int(snapshot.get("num_trades"))
    trading_days = _as_int(period.get("trading_days"))
    if trading_days is None:
        trading_days = _as_int(metrics.get("trading_days"))
    if trading_days is None:
        trading_days = _as_int(snapshot.get("trading_days"))
    min_trades = _as_int(criteria.get("min_trades"))
    if min_trades is None:
        min_trades = _DEFAULT_MIN_TRADES
    min_days = _as_int(criteria.get("min_trading_days"))
    if min_days is None:
        min_days = _DEFAULT_MIN_DAYS
    return num_trades, trading_days, min_trades, min_days


def _raw_beats(snapshot: Mapping[str, Any]) -> Optional[bool]:
    bench = _mapping(snapshot.get("benchmark"))
    flag = _as_bool(bench.get("beats_spy_net"))
    if flag is None:
        flag = _as_bool(snapshot.get("beats_spy_net"))
    return flag


def _short_reason(reasons: List[str]) -> str:
    cleaned = [str(item).strip() for item in reasons if str(item).strip()]
    if not cleaned:
        return "trades/days below min"
    return "; ".join(cleaned[:2])


def gate_performance_claims(
    snapshot: Optional[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Display contract for paper performance. Fail closed when the seal does not hold."""
    snap = _mapping(snapshot)
    pnl = _mapping(snap.get("pnl"))
    bench = _mapping(snap.get("benchmark"))
    costs = _mapping(snap.get("costs"))
    num_trades, trading_days, min_trades, min_days = _counts(snap)
    explicit = _explicit_seal(snap)

    reasons: List[str] = []
    raw_reasons = snap.get("seal_reasons")
    if not isinstance(raw_reasons, list):
        raw_reasons = _mapping(snap.get("seal_preview")).get("reasons")
    if isinstance(raw_reasons, list):
        reasons.extend(str(item) for item in raw_reasons if str(item).strip())

    insufficient: List[str] = []
    if num_trades is None or num_trades < min_trades:
        shown = "missing" if num_trades is None else str(num_trades)
        insufficient.append(f"num_trades {shown} < min {min_trades}")
    if trading_days is None or trading_days < min_days:
        shown = "missing" if trading_days is None else str(trading_days)
        insufficient.append(f"trading_days {shown} < min {min_days}")

    claims_allowed = explicit is True and not insufficient
    if explicit is False and not reasons:
        reasons.append("seal_passed is false")
    if explicit is None and not reasons:
        reasons.append("seal unavailable")
    if insufficient:
        for item in insufficient:
            if item not in reasons:
                reasons.append(item)
    if not claims_allowed:
        reason = _short_reason(reasons or insufficient)
    else:
        reason = ""

    raw_beats = _raw_beats(snap)
    if claims_allowed:
        beats: Optional[bool] = raw_beats
    else:
        beats = None

    total = _as_float(pnl.get("total_return_pct"))
    if total is None:
        total = _as_float(snap.get("total_return_pct"))
    spy = _as_float(bench.get("spy_return_pct"))
    if spy is None:
        spy = _as_float(snap.get("spy_return_pct"))
    alpha = _as_float(bench.get("alpha_net_of_costs_pct"))
    if alpha is None:
        alpha = _as_float(costs.get("alpha_net_of_costs_pct"))
    if alpha is None:
        alpha = _as_float(snap.get("alpha_net_of_costs_pct"))
    annualized = _as_float(pnl.get("annualized_return_pct"))
    if annualized is None:
        annualized = _as_float(snap.get("annualized_return_pct"))

    generated = snap.get("generated_at")
    freshness = snapshot_freshness(generated, now=now)
    if claims_allowed:
        annualized_label = None if annualized is None else f"{annualized:.2f}%"
    else:
        total = None
        spy = None
        alpha = None
        annualized = None
        annualized_label = "n/a"

    return {
        "claims_allowed": claims_allowed,
        "seal_passed": claims_allowed,
        "not_a_seal": not claims_allowed,
        "claims_beat_spy": bool(claims_allowed and beats is True),
        "beats_spy_net": beats if claims_allowed else None,
        "total_return_pct": total,
        "spy_return_pct": spy,
        "alpha_net_of_costs_pct": alpha,
        "annualized_return_pct": annualized,
        "annualized_label": annualized_label,
        "num_trades": num_trades,
        "trading_days": trading_days,
        "reason": reason,
        "reasons": reasons if not claims_allowed else [],
        "freshness": freshness,
        "live": False,
    }


def coerce_beats_spy_net(
    beats: Optional[bool],
    *,
    seal_passed: bool,
) -> Optional[bool]:
    """Writers must not persist a beat-SPY claim when the seal failed.

    ``False`` is kept (it is not a beat claim). ``True`` becomes ``None``.
    """
    if beats is True and not seal_passed:
        return None
    return beats


def annualized_for_snapshot(annualized: Optional[float], *, seal_passed: bool) -> Optional[float]:
    """Drop annualized when the seal failed so a short window cannot read as a rate."""
    if not seal_passed:
        return None
    return annualized


def attach_display(
    paper: Optional[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Copy a paper payload and attach a gated ``display`` block.

    Stored ``beats_spy_net`` cannot remain true when the seal fails.
    Annualized on ``pnl`` is cleared in that case. Raw total return stays
    on ``pnl`` for audit; UIs must read ``display``.
    """
    out = _mapping(paper)
    view = gate_performance_claims(out, now=now)
    bench = _mapping(out.get("benchmark"))
    pnl = _mapping(out.get("pnl"))
    if bench.get("beats_spy_net") is True and not view["claims_allowed"]:
        bench["beats_spy_net"] = None
    if out.get("beats_spy_net") is True and not view["claims_allowed"]:
        out["beats_spy_net"] = None
    if not view["claims_allowed"]:
        pnl["annualized_return_pct"] = None
    out["benchmark"] = bench
    out["pnl"] = pnl
    out["display"] = view
    return out


def format_skip_summary(skips: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(skips, Mapping) or not skips:
        return ""
    parts = []
    for key, value in skips.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count > 0:
            parts.append(f"{key} × {count}")
    return "; ".join(parts)


def build_trust_status(
    paper: Optional[Mapping[str, Any]],
    heartbeat: Optional[Mapping[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Paper-ledger status for Streamlit and other readers of ``backend/data/``.

    Kelly ``data/`` is labeled as a portfolio experiment, separate from this ledger.
    """
    hb = _mapping(heartbeat)
    card = hb.get("session_card") if isinstance(hb.get("session_card"), Mapping) else None
    view = gate_performance_claims(paper, now=now)
    skips: Mapping[str, Any] = {}
    if card and isinstance(card.get("why_no_trade"), Mapping):
        skips = card["why_no_trade"]
    elif isinstance(hb.get("skip_counts"), Mapping):
        skips = hb["skip_counts"]
    summary = format_skip_summary(skips)
    if card is None:
        session = {
            "available": False,
            "seal": None,
            "not_a_seal": None,
            "claims_beat_spy": None,
        }
    else:
        session = {
            "available": True,
            "seal": bool(card.get("seal")),
            "not_a_seal": bool(card.get("not_a_seal", True)),
            "claims_beat_spy": bool(card.get("claims_beat_spy")),
        }
    freshness = view["freshness"]
    return {
        "book_dir": "backend/data/",
        "book_kind": "paper ledger",
        "kelly_dir": "data/",
        "kelly_kind": "portfolio experiment",
        "same_ledger": False,
        "seal_passed": view["seal_passed"],
        "reason": view["reason"],
        "claims_allowed": view["claims_allowed"],
        "total_return_pct": view["total_return_pct"],
        "spy_return_pct": view["spy_return_pct"],
        "beats_spy_net": view["beats_spy_net"],
        "claims_beat_spy": view["claims_beat_spy"],
        "annualized_return_pct": view["annualized_return_pct"],
        "annualized_label": view["annualized_label"],
        "num_trades": view["num_trades"],
        "trading_days": view["trading_days"],
        "session_card": session,
        "why_no_trade": dict(skips),
        "why_no_trade_summary": summary,
        "freshness": freshness,
        "generated_at": freshness.get("generated_at"),
        "live": False,
    }
