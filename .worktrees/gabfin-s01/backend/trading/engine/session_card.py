"""Phase 1 session card.

Prints what this cycle watched and did. It is a label, not a seal, and it
does not say the book beat SPY.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence

# Same five names TradingWorker uses when STOCK_UNIVERSE cannot be imported.
IMPORT_FALLBACK_NAMES = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA")

_FULL_CAP_TOKENS = frozenset({"", "0", "all", "full", "none"})


def scout_env_requested() -> bool:
    """Read ``SCOUT_ENABLED``. Phase 1 does not honor it (no scout client)."""
    token = str(os.getenv("SCOUT_ENABLED", "0") or "").strip().lower()
    return token in {"1", "true", "yes", "on"}


def core_universe_size() -> Optional[int]:
    try:
        from backend.utils.constants import STOCK_UNIVERSE

        return len(STOCK_UNIVERSE)
    except Exception:
        return None


def _cap_is_full(cap_env: Optional[str]) -> bool:
    return str(cap_env or "").strip().lower() in _FULL_CAP_TOKENS


def label_paper_vs_spy(report: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """Side-by-side returns when a performance book exists. Not a verdict."""
    if not isinstance(report, Mapping):
        return None
    pnl = report.get("pnl") if isinstance(report.get("pnl"), Mapping) else {}
    bench = report.get("benchmark") if isinstance(report.get("benchmark"), Mapping) else {}
    paper = pnl.get("total_return_pct")
    spy = bench.get("spy_return_pct")
    if paper is None and spy is None:
        return None
    metrics = report.get("metrics") if isinstance(report.get("metrics"), Mapping) else {}
    invested = metrics.get("avg_invested_pct")
    if invested is None:
        invested = report.get("invested_pct")
    return {
        "label": "paper vs SPY",
        "paper_return_pct": paper,
        "spy_return_pct": spy,
        "invested_pct": invested,
        "seal": False,
        "not_a_seal": True,
        "claims_beat_spy": False,
    }


def build_session_card(
    *,
    universe_source: str,
    universe_requested: Sequence[str],
    cap: int,
    cap_env: Optional[str],
    fetched: Sequence[str],
    skip_counts: Optional[Mapping[str, int]],
    order_statuses: Optional[Sequence[Mapping[str, Any]]],
    execution_mode: str,
    invested_pct: Optional[float] = None,
    performance_report: Optional[Mapping[str, Any]] = None,
    ai_judge: bool = False,
    zone_evidence: Optional[Mapping[str, Any]] = None,
) -> dict:
    """One cycle's honest book. ``seal`` is always false."""
    requested = [str(s).upper() for s in universe_requested if str(s).strip()]
    fetched_names = [str(s).upper() for s in fetched if str(s).strip()]
    core = core_universe_size()
    source = str(universe_source or "")
    full_cap = _cap_is_full(cap_env)
    truncated = (not full_cap) and int(cap) < len(requested)
    cap_label = "ops cap" if truncated else "full"
    data_fault = None
    if source == "import_fallback":
        data_fault = "universe_import_fallback"

    orders = []
    for row in order_statuses or []:
        if not isinstance(row, Mapping):
            continue
        orders.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "side": str(row.get("side") or "").lower() or None,
                "status": str(row.get("status") or "").lower(),
            }
        )

    skips = {str(k): int(v) for k, v in (skip_counts or {}).items() if int(v) > 0}
    paper_label = label_paper_vs_spy(performance_report)

    note_parts = []
    if data_fault:
        note_parts.append(
            "data fault: universe import fallback "
            + " ".join(IMPORT_FALLBACK_NAMES)
            + "; not a performance result"
        )
    if truncated:
        note_parts.append("ops cap")
    elif source == "override":
        note_parts.append("ops override (--tickers); not the strategy universe")
    if paper_label is not None:
        note_parts.append("paper vs SPY (label only, not a seal)")

    return {
        "schema": "session_card.v0",
        "seal": False,
        "not_a_seal": True,
        "claims_beat_spy": False,
        "execution_mode": execution_mode,
        "ai_judge": bool(ai_judge),
        "scout_enabled": False,
        "scout_env_requested": scout_env_requested(),
        "candidate_size": 0,
        "core_universe_size": core,
        "universe_requested": len(requested),
        "universe_source": source,
        "cap": int(cap),
        "cap_label": cap_label,
        "cap_env": None if full_cap else str(cap_env).strip(),
        "fetched_count": len(fetched_names),
        "names_fetched": fetched_names,
        "invested_pct": invested_pct,
        "why_no_trade": skips,
        "order_statuses": orders,
        "paper_vs_spy": paper_label,
        "data_fault": data_fault,
        "note": "; ".join(note_parts),
        "evidence": _zone_evidence_block(zone_evidence),
    }


def _zone_evidence_block(zone_evidence: Optional[Mapping[str, Any]]) -> dict:
    """Cite stored zones. Never a seal and never verified/live."""
    if zone_evidence is None:
        try:
            from backend.api.desk_zones import session_zone_evidence

            block = session_zone_evidence()
        except Exception:
            block = {"zones": [], "verified": False, "live": False, "seal": False}
    else:
        raw_zones = zone_evidence.get("zones") if isinstance(zone_evidence, Mapping) else None
        zones = []
        for row in raw_zones or []:
            if not isinstance(row, Mapping):
                continue
            item = dict(row)
            item["verified"] = False
            item["live"] = False
            item.pop("seal", None)
            zones.append(item)
        block = {"zones": zones, "verified": False, "live": False, "seal": False}
    zones_out = []
    for row in block.get("zones") or []:
        if not isinstance(row, Mapping):
            continue
        item = dict(row)
        item["verified"] = False
        item["live"] = False
        item.pop("seal", None)
        zones_out.append(item)
    return {"zones": zones_out, "verified": False, "live": False, "seal": False}
