"""Mobile Desk read-only shell (/m).

Path A P0: morning / agents / activity. Continue and Pause post only to the
paper worker. This module does not place orders, approve live, edit live
rules, run Scan or Deep, or touch the broker kill switch.

Legacy implementation only; its old architecture decisions are retired.
The adr_005 response metadata is retained for compatibility, not design authority.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.api.desk_auth import is_operator, is_reader, require_operator
from backend.trading.strategies.registry import KNOWN_STRATEGIES
from backend.utils.constants import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mobile-ro"])

AI_MODE_PATH = Path(DATA_DIR) / "ai_mode.json"
MOBILE_SURFACE = "mobile-ro"
PAPER_POSTS = frozenset({
    "/api/mobile/paper/continue",
    "/api/mobile/paper/pause",
})
_HKT = ZoneInfo("Asia/Hong_Kong")
_ORDER_STORE: Any = None

HONESTY_ZH = "教學／觀察面 · 不是 verified／live · 手機不會下單或改 live 規則"
UNREACHABLE_ZH = "請開啟 Tailscale 後重新整理"
EMPTY_SESSION_ZH = "尚無紙上 session"
GUEST_ZH = "此連線只讀。Continue／Pause 已隱藏。"
WORKING_NOTE = "Working ≠ seal · fills only"
ACTIVITY_NOTE = "曲線事件釘延後 · 本輪無"
EQUITY_LABEL = "paper · not live"


class PaperOnlyIn(BaseModel):
    """Client may only confirm paper. Extra fields (live, broker, allow_live) are rejected."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="paper")


def set_order_store(store: Any) -> None:
    global _ORDER_STORE
    _ORDER_STORE = store


def install_mobile_guard(app: Any) -> None:
    """Block every mobile-surface mutation except paper continue/pause.

    Desktop requests do not send ``X-Cgab-Surface: mobile-ro`` and are unchanged.
    """

    @app.middleware("http")
    async def mobile_ro_guard(request: Request, call_next):
        surface = (request.headers.get("x-cgab-surface") or "").strip().lower()
        if surface == MOBILE_SURFACE and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.url.path not in PAPER_POSTS:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Mobile desk is read-only. Paper continue/pause only. "
                            "Live and broker actions are blocked."
                        ),
                        "places_order": False,
                        "live": False,
                        "verified": False,
                    },
                )
        return await call_next(request)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, default=str), encoding="utf-8")


def _paper_env() -> bool:
    from backend.api import worker_ctl

    return bool(worker_ctl._is_paper())


def _require_paper_worker() -> None:
    if not _paper_env():
        raise HTTPException(
            status_code=403,
            detail="Live trading is blocked. Paper worker only.",
        )


def _guard_paper_body(body: Optional[PaperOnlyIn]) -> PaperOnlyIn:
    body = body or PaperOnlyIn()
    mode = str(body.mode or "paper").strip().lower()
    if mode != "paper":
        raise HTTPException(
            status_code=403,
            detail="Live trading is blocked. Paper worker only.",
        )
    _require_paper_worker()
    return body


def _saved_strategy() -> str:
    raw = _read_json(AI_MODE_PATH, {})
    data = raw if isinstance(raw, dict) else {}
    strategy = str(data.get("strategy") or "breakout").strip()
    if strategy not in KNOWN_STRATEGIES:
        strategy = "breakout"
    return strategy


def _mark_worker_enabled(enabled: bool, strategy: Optional[str] = None) -> None:
    raw = _read_json(AI_MODE_PATH, {})
    data = dict(raw) if isinstance(raw, dict) else {}
    data["worker_enabled"] = bool(enabled)
    if strategy:
        data["strategy"] = strategy
    _write_json(AI_MODE_PATH, data)


def _paper_payload(action: str, raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    raw = raw or {}
    return {
        "ok": True,
        "action": action,
        "mode": "paper",
        "worker": "paper",
        "running": bool(raw.get("running")),
        "already_running": bool(raw.get("already_running")),
        "touches_broker": False,
        "touches_live": False,
        "touches_kill": False,
        "places_order": False,
        "live": False,
        "verified": False,
    }


def continue_paper(body: Optional[PaperOnlyIn] = None) -> Dict[str, Any]:
    """Start or confirm the paper worker. Does not call the broker or kill switch."""
    _guard_paper_body(body)
    from backend.api import worker_ctl

    strategy = _saved_strategy()
    try:
        result = worker_ctl.start(strategy=strategy, interval=60)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _mark_worker_enabled(True, strategy)
    return _paper_payload("continue", result)


def pause_paper(body: Optional[PaperOnlyIn] = None) -> Dict[str, Any]:
    """Stop the paper worker process. This is not a broker halt."""
    _guard_paper_body(body)
    from backend.api import worker_ctl

    try:
        result = worker_ctl.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _mark_worker_enabled(False)
    return _paper_payload("pause", result)


def _hkt_hm(ts: Optional[str]) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_HKT).strftime("%H:%M")


def _mode(entry: Mapping[str, Any]) -> str:
    prov = entry.get("provenance") if isinstance(entry.get("provenance"), Mapping) else {}
    blob = " ".join(
        [
            str(entry.get("mode") or ""),
            str(entry.get("execution_mode") or ""),
            str(prov.get("source") or ""),
        ]
    ).lower()
    if "shadow" in blob:
        return "shadow"
    return "paper"


def _actor(entry: Mapping[str, Any]) -> str:
    prov = entry.get("provenance") if isinstance(entry.get("provenance"), Mapping) else {}
    named = str(prov.get("actor") or entry.get("actor") or "").strip()
    if named:
        return named
    kind = str(entry.get("kind") or "")
    status = str(entry.get("status") or "")
    codes = " ".join(str(c) for c in (entry.get("reason_codes") or []))
    summary = str(entry.get("user_visible_summary") or "")
    blob = f"{kind} {status} {codes} {summary}".lower()
    if any(token in blob for token in ("skip", "reject", "risk", "mandate")):
        return "Risk"
    if "fill" in blob or status.lower() in {"filled", "partially_filled"}:
        return "Exec"
    if "scan" in blob:
        return "Scan"
    return "Desk"


def _action(entry: Mapping[str, Any]) -> str:
    status = str(entry.get("status") or "").lower()
    summary = str(entry.get("user_visible_summary") or "").lower()
    codes = [str(c).lower() for c in (entry.get("reason_codes") or [])]
    blob = " ".join([summary, *codes, status])
    if "skip" in blob:
        return "SKIP"
    if any(token in blob for token in ("stopped", "stop out", "stop-loss", "stop_loss")):
        return "STOP"
    if status in {"filled", "partially_filled"} or "fill" in blob:
        return "FILL"
    if status in {"rejected", "cancelled", "canceled"} or "reject" in blob:
        return "SKIP"
    token = str(entry.get("kind") or status or "NOTE").upper()
    return token[:16] or "NOTE"


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_text(entry: Mapping[str, Any], action: str) -> str:
    summary = str(entry.get("user_visible_summary") or "").strip()
    status = str(entry.get("display_status") or entry.get("status") or "").strip()
    base = summary or status or "—"
    r_mult = _float_or_none(entry.get("r_multiple"))
    if r_mult is not None:
        base = f"{base} · R {r_mult:+.2f}"
    if action == "FILL" and "paper" not in base.lower() and "simulated" not in base.lower():
        base = f"paper fill · {base}"
    return base


def _tone(action: str, result: str, entry: Mapping[str, Any]) -> str:
    r_mult = _float_or_none(entry.get("r_multiple"))
    if r_mult is not None:
        if r_mult < 0:
            return "rose"
        if r_mult > 0:
            return "mint"
    text = f"{action} {result}".lower()
    if action in {"SKIP", "STOP"} or any(
        token in text for token in ("skip", "stopped", "stop", "loss", "reject", "虧", "跳過")
    ):
        return "rose"
    if action == "FILL" and any(token in text for token in ("profit", "盈", "gain")):
        return "mint"
    return "muted"


def _evidence(entry: Mapping[str, Any]) -> str:
    links = entry.get("links") if isinstance(entry.get("links"), Mapping) else {}
    parts = [
        str(entry.get("log_id") or "").strip(),
        str(entry.get("risk_decision_id") or "").strip(),
        str(links.get("audit_ref") or "").strip(),
        str(links.get("zone_ref") or "").strip(),
    ]
    seen: List[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return " · ".join(seen)


def _activity_item(
    *,
    ts: str,
    actor: str,
    action: str,
    symbol: str,
    result: str,
    mode: str,
    tone: str,
    evidence: str,
) -> Dict[str, Any]:
    safe_mode = "shadow" if mode == "shadow" else "paper"
    return {
        "time": _hkt_hm(ts) if ts else "—",
        "ts": ts or "",
        "actor": actor or "Desk",
        "action": action or "NOTE",
        "symbol": (symbol or "").upper(),
        "result": result or "—",
        "mode": safe_mode,
        "tone": tone if tone in {"mint", "rose", "muted"} else "muted",
        "evidence": evidence or "",
    }


def activity_rows(
    entries: Optional[List[Mapping[str, Any]]] = None,
    skip_by_ticker: Optional[Mapping[str, Any]] = None,
    *,
    heartbeat_ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Newest first. Losses, stops, and skips stay beside gains."""
    rows: List[Dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, Mapping):
            continue
        action = _action(entry)
        result = _result_text(entry, action)
        rows.append(
            _activity_item(
                ts=str(entry.get("ts") or ""),
                actor=_actor(entry),
                action=action,
                symbol=str(entry.get("symbol") or ""),
                result=result,
                mode=_mode(entry),
                tone=_tone(action, result, entry),
                evidence=_evidence(entry),
            )
        )
    for symbol, reason in (skip_by_ticker or {}).items():
        token = str(symbol or "").upper().strip()
        if not token:
            continue
        why = str(reason or "skipped")
        rows.append(
            _activity_item(
                ts=str(heartbeat_ts or ""),
                actor="Risk",
                action="SKIP",
                symbol=token,
                result=why,
                mode="paper",
                tone="rose",
                evidence="",
            )
        )
    rows.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    return rows[:50]


def _claims_allowed(digest: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(digest, Mapping):
        return False
    bench = digest.get("benchmark") if isinstance(digest.get("benchmark"), Mapping) else {}
    pnl = digest.get("pnl") if isinstance(digest.get("pnl"), Mapping) else {}
    flag = bench.get("claims_allowed")
    if flag is None:
        flag = pnl.get("claims_allowed")
    return bool(flag)


def public_session_card(
    card: Optional[Mapping[str, Any]],
    *,
    claims_allowed: bool,
) -> Optional[Dict[str, Any]]:
    if not isinstance(card, dict):
        return None
    seal = bool(card.get("seal"))
    claims_beat = bool(card.get("claims_beat_spy")) and claims_allowed and seal
    mode = str(card.get("execution_mode") or "paper").lower()
    if mode not in {"paper", "shadow"}:
        mode = "paper"
    return {
        "schema": card.get("schema") or "session_card.v0",
        "seal": seal,
        "not_a_seal": bool(card.get("not_a_seal", not seal)),
        "claims_beat_spy": claims_beat,
        "execution_mode": mode,
        "note": str(card.get("note") or ""),
        "why_no_trade": card.get("why_no_trade") if isinstance(card.get("why_no_trade"), dict) else {},
        "data_fault": card.get("data_fault"),
    }


def morning_book(
    digest: Optional[Mapping[str, Any]],
    session_card: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Seal / vs-SPY honesty. Alpha is shown only when claims are allowed and the card is a seal."""
    digest = digest if isinstance(digest, Mapping) else {}
    bench = digest.get("benchmark") if isinstance(digest.get("benchmark"), Mapping) else {}
    pnl = digest.get("pnl") if isinstance(digest.get("pnl"), Mapping) else {}
    scan = digest.get("scan") if isinstance(digest.get("scan"), Mapping) else {}
    filled = digest.get("filled") if isinstance(digest.get("filled"), Mapping) else {}
    pending = digest.get("pending") if isinstance(digest.get("pending"), Mapping) else {}
    skips = digest.get("skips") if isinstance(digest.get("skips"), Mapping) else {}
    allowed = _claims_allowed(digest)
    card = public_session_card(session_card, claims_allowed=allowed)
    reason = str(bench.get("seal_reason") or pnl.get("seal_reason") or "")
    if not allowed and not reason:
        reason = "trades/days below min"
    alpha = _float_or_none(bench.get("alpha_net_of_costs_pct"))
    spy = _float_or_none(bench.get("spy_return_pct"))
    # Hero vs-SPY number only when the performance gate allows it and the
    # session card itself is a seal. An unsealed card withholds the figure.
    sealed = bool(card and card.get("seal"))
    show_alpha = bool(allowed and sealed and alpha is not None)
    if not show_alpha and not reason:
        reason = "not a seal"
    equity = bench.get("equity")
    if equity is None:
        equity = pnl.get("equity")
    return {
        "session_card": card,
        "seal": bool(card.get("seal")) if card else False,
        "not_a_seal": True if card is None else bool(card.get("not_a_seal", True)),
        "claims_beat_spy": bool(card.get("claims_beat_spy")) if card else False,
        "claims_allowed": allowed,
        "seal_reason": "" if show_alpha else reason,
        "alpha_net_of_costs_pct": alpha if show_alpha else None,
        "spy_return_pct": spy if show_alpha else None,
        "equity": equity,
        "equity_label": EQUITY_LABEL,
        "digest": {
            "scan_as_of": scan.get("as_of"),
            "scan_fresh": (not bool(scan.get("stale"))) and bool(scan.get("available")),
            "scan_label": scan.get("fresh_label_zh") or ("新鮮" if scan.get("available") and not scan.get("stale") else "—"),
            "top5": list(scan.get("top5") or [])[:5],
            "filled_count": int(filled.get("count") or 0),
            "working_count": int(pending.get("count") or 0),
            "working_note": WORKING_NOTE,
            "skips": str(skips.get("summary_zh") or skips.get("summary_en") or "—"),
        },
    }


def _agent_scan(scan: Mapping[str, Any], job: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    status = str((job or {}).get("status") or "idle").lower()
    state = "running" if status in {"queued", "running"} else "idle"
    top = list(scan.get("top5_tickers") or scan.get("top5") or [])[:3]
    return {
        "state": state,
        "as_of": scan.get("ts") or scan.get("as_of"),
        "top": top,
    }


def _agent_score(scan: Mapping[str, Any], job: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    status = str((job or {}).get("status") or "").lower()
    done = (job or {}).get("progress")
    total = (job or {}).get("total")
    if done is None:
        done = scan.get("ranking_count")
        if done is None and isinstance(scan.get("rankings"), list):
            done = len(scan.get("rankings") or [])
    if status in {"queued", "running"}:
        label = f"{int(done or 0)}/{int(total or 0)} done" if total else "running"
        state = "running"
    elif done:
        label = f"{int(done)} done"
        state = "done"
    else:
        label = "idle"
        state = "idle"
    return {"state": state, "done": int(done or 0), "total": int(total) if total else None, "label": label}


def _agent_risk(worker: Mapping[str, Any], *, halted: bool, reason: Optional[str]) -> Dict[str, Any]:
    explain = worker.get("explain") if isinstance(worker.get("explain"), Mapping) else {}
    detail = str(explain.get("message_zh") or explain.get("message_en") or "")
    skips = worker.get("skip_counts") if isinstance(worker.get("skip_counts"), Mapping) else {}
    running = bool(worker.get("running"))
    if halted:
        label = "HOLD: " + (reason or detail or "paper gate")
        state = "hold"
    elif not running:
        label = "paper gates · worker paused"
        state = "paused"
    elif skips:
        label = "paper gates 通過 · skips recorded"
        state = "pass"
    else:
        label = "paper gates 通過"
        state = "pass"
    return {"state": state, "label": label[:180], "detail": detail[:240]}


def _controls(*, operator: bool) -> Dict[str, bool]:
    paper = _paper_env()
    allowed = bool(operator and paper)
    return {
        "continue_paper": allowed,
        "pause_paper": allowed,
        "orders": False,
        "approve_live": False,
        "edit_live_rules": False,
        "scan_execute": False,
        "deep_execute": False,
        "halt": False,
    }


def _envelope(*, access: str, operator: bool, reader: bool) -> Dict[str, Any]:
    return {
        "access": access,
        "operator": operator,
        "reader": reader,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone_label": "HKT",
        "paper": _paper_env(),
        "live": False,
        "verified": False,
        "places_order": False,
        "adr_005": {"id": "ADR-005", "status": "Draft", "accepted": False},
        "controls": _controls(operator=operator),
        "honesty_zh": HONESTY_ZH,
        "unreachable_zh": UNREACHABLE_ZH,
        "empty_session_zh": EMPTY_SESSION_ZH,
        "guest_zh": GUEST_ZH,
        "equity_label": EQUITY_LABEL,
        "activity_note": ACTIVITY_NOTE,
    }


def _guest_snapshot() -> Dict[str, Any]:
    payload = _envelope(access="guest", operator=False, reader=False)
    payload.update(
        {
            "session_card": None,
            "seal": False,
            "not_a_seal": True,
            "claims_beat_spy": False,
            "claims_allowed": False,
            "seal_reason": "",
            "alpha_net_of_costs_pct": None,
            "spy_return_pct": None,
            "equity": None,
            "digest": None,
            "agents": None,
            "activity": [],
            "worker_running": False,
        }
    )
    return payload


def build_snapshot(request: Request) -> Dict[str, Any]:
    operator = is_operator(request)
    reader = is_reader(request)
    if not reader:
        return _guest_snapshot()

    from backend.api import paper_performance, research_jobs, trade_journal, worker_ctl
    from backend.api.intents import get_intent_store
    from backend.trading.safety import kill_switch

    worker: Dict[str, Any] = {}
    try:
        raw_worker = worker_ctl.status()
        worker = raw_worker if isinstance(raw_worker, dict) else {}
    except Exception as exc:
        logger.debug("mobile worker status skipped: %s", exc)

    digest: Dict[str, Any] = {}
    try:
        raw_digest = paper_performance.build_daily_digest(worker_status=worker, persist_paper=False)
        digest = raw_digest if isinstance(raw_digest, dict) else {}
    except Exception as exc:
        logger.debug("mobile digest skipped: %s", exc)

    scan: Dict[str, Any] = {}
    try:
        raw_scan = research_jobs.latest_scan()
        scan = raw_scan if isinstance(raw_scan, dict) else {}
    except Exception as exc:
        logger.debug("mobile scan read skipped: %s", exc)

    job: Optional[Dict[str, Any]] = None
    try:
        raw_job = research_jobs.latest_job("scan")
        job = raw_job if isinstance(raw_job, dict) else None
    except Exception as exc:
        logger.debug("mobile scan job skipped: %s", exc)

    pending = 0
    try:
        pending = len(get_intent_store().list(status="active", limit=100))
    except Exception as exc:
        logger.debug("mobile intents skipped: %s", exc)

    entries: List[Any] = []
    try:
        journal = trade_journal.build_journal_response(order_store=_ORDER_STORE, limit=40)
        entries = list(journal.get("entries") or [])
    except Exception as exc:
        logger.debug("mobile journal skipped: %s", exc)

    halted = bool(worker.get("halted"))
    reason = None
    try:
        if kill_switch.is_halted():
            halted = True
            reason = kill_switch.get_reason()
    except Exception as exc:
        logger.debug("mobile halt read skipped: %s", exc)

    session = worker.get("session_card") if isinstance(worker.get("session_card"), dict) else None
    book = morning_book(digest, session)
    skip_map = worker.get("skip_by_ticker") if isinstance(worker.get("skip_by_ticker"), dict) else {}
    activity = activity_rows(
        entries,
        skip_map,
        heartbeat_ts=str(worker.get("heartbeat_ts") or worker.get("last_run") or ""),
    )
    scan_view = digest.get("scan") if isinstance(digest.get("scan"), Mapping) else {}
    merged_scan = {**scan, "as_of": scan.get("ts") or scan_view.get("as_of"), "top5": scan_view.get("top5") or scan.get("top5_tickers") or []}
    access = "operator" if operator else "reader"
    payload = _envelope(access=access, operator=operator, reader=True)
    payload.update(book)
    payload["worker_running"] = bool(worker.get("running"))
    payload["agents"] = {
        "scan": _agent_scan(merged_scan, job),
        "score": _agent_score(scan, job),
        "intent": {
            "pending": pending,
            "note": "proposal ≠ 成交 · paper",
        },
        "risk": _agent_risk(worker, halted=halted, reason=reason),
    }
    payload["activity"] = activity
    payload["live"] = False
    payload["verified"] = False
    payload["places_order"] = False
    return payload


@router.get("/api/mobile/snapshot")
def mobile_snapshot(request: Request) -> Dict[str, Any]:
    """Read-only morning / status / activity bundle. No order side effects."""
    return build_snapshot(request)


@router.post("/api/mobile/paper/continue")
def mobile_continue(
    request: Request,
    body: Optional[PaperOnlyIn] = None,
) -> Dict[str, Any]:
    require_operator(request)
    return continue_paper(body)


@router.post("/api/mobile/paper/pause")
def mobile_pause(
    request: Request,
    body: Optional[PaperOnlyIn] = None,
) -> Dict[str, Any]:
    require_operator(request)
    return pause_paper(body)
