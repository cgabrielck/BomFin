"""Desk zone evidence store.

Read geometry + meta for journal, proposal cites, and the Streamlit mirror.
Owner writes are limited to role, notes, and archive|active. Drawing geometry
is replaced only by a Desk snapshot (``source=desk_draw``). Agents may cite an
existing ``zone_id`` and cannot create or reprice a band. ``verified`` and
``live`` are always false.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.api.desk_auth import require_operator
from backend.utils.constants import DATA_DIR

SCHEMA = "desk_zones.v1"
ROLES = ("neutral", "support", "resist")
ROLE_CITE = {"neutral": "中性", "support": "支撐", "resist": "阻力"}
STATUSES = ("active", "archive")
CITE_PREFIX = "用戶標註價區"
NOTES_MAX = 280
LABEL_MAX = 40
AGENT_ACTORS = frozenset({"ai", "agent", "llm", "auto", "worker", "scout", "assistant"})
_ID_RE = re.compile(r"^[\w-]{1,40}$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_STAMP_RE = re.compile(
    r"必買|止蝕|止損|必賣|verified|已驗證|已验证|AI\s*已|AI\s*confirmed",
    re.IGNORECASE,
)
_LOCK = threading.RLock()

router = APIRouter(tags=["desk-zones"])

UNABLE = {"code": "unable_to_cite", "message": "無法引用"}


class ZoneError(ValueError):
    """Fail-closed zone write."""


class ZoneNotFound(ZoneError):
    """Unknown zone_id. Callers must not invent a band."""


def zones_path() -> Path:
    override = (os.getenv("DESK_ZONES_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(DATA_DIR) / "desk_zones.json"


def cite_role(role: str) -> str:
    """Chinese cite label. Storage stays on the English role token."""
    return ROLE_CITE.get(str(role or ""), "中性")


def format_cite(zone_id: str, role: str, notes: str = "") -> str:
    """Exact cite. Notes segment is omitted when empty. No confidence or stamp.

    The role segment is ``中性`` / ``支撐`` / ``阻力``. Callers pass the stored
    token ``neutral`` | ``support`` | ``resist``.
    """
    base = f"{CITE_PREFIX} {zone_id}｜{cite_role(role)}"
    text = str(notes or "").strip()
    if text:
        return f"{base}｜{text}"
    return base


def _symbol(raw: Any) -> str:
    sym = str(raw or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise ZoneError("invalid symbol")
    return sym


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _day(value: Any) -> str:
    text = str(value or "")[:10]
    return text if _DAY_RE.match(text) else ""


def _clean_text(raw: Any, limit: int) -> str:
    text = re.sub(r"[\r\n]+", " ", str(raw if raw is not None else ""))
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit]


def sanitize_notes(raw: Any, *, reject_stamp: bool = False) -> str:
    original = re.sub(r"[\r\n]+", " ", str(raw if raw is not None else ""))
    original = re.sub(r"[ \t]+", " ", original).strip()
    if len(original) > NOTES_MAX:
        if reject_stamp:
            raise ZoneError("notes_too_long")
    text = original[:NOTES_MAX]
    if not text:
        return ""
    if text.lower() == "live" or _STAMP_RE.search(text):
        if reject_stamp:
            raise ZoneError("notes_stamp")
        return ""
    return text


def _sanitize_label(raw: Any) -> str:
    text = _clean_text(raw, LABEL_MAX)
    if not text or text.lower() == "live" or _STAMP_RE.search(text):
        return ""
    return text


def _flag(raw: Mapping[str, Any], *names: str) -> bool:
    for name in names:
        if name in raw:
            return raw.get(name) is True
    return False


def sanitize_zone_record(raw: Any, *, symbol: str) -> Optional[Dict[str, Any]]:
    """Drop illegal objects. Never persist verified/live true."""
    if not isinstance(raw, Mapping):
        return None
    origin = str(raw.get("origin") or raw.get("created_by") or "").strip().lower()
    if origin in AGENT_ACTORS:
        return None
    zone_id = str(raw.get("zone_id") or raw.get("id") or "").strip()
    if zone_id == "preview" or not _ID_RE.match(zone_id):
        return None
    geom = raw.get("geometry") if isinstance(raw.get("geometry"), Mapping) else {}
    high = _num(
        raw.get("price_high", raw.get("priceHigh", geom.get("price_high", geom.get("priceHigh"))))
    )
    low = _num(raw.get("price_low", raw.get("priceLow", geom.get("price_low", geom.get("priceLow")))))
    if high is None or low is None:
        return None
    price_high = max(high, low)
    price_low = min(high, low)
    if not price_high > price_low:
        return None
    time_left = _day(
        raw.get("time_left") or raw.get("timeLeft") or geom.get("time_left") or geom.get("timeLeft")
    )
    time_right = _day(
        raw.get("time_right")
        or raw.get("timeRight")
        or geom.get("time_right")
        or geom.get("timeRight")
    )
    if not time_left or not time_right:
        return None
    if time_left > time_right:
        time_left, time_right = time_right, time_left
    role = str(raw.get("role") or "neutral")
    if role not in ROLES:
        role = "neutral"
    status = str(raw.get("status") or "active")
    if status not in STATUSES:
        status = "active"
    try:
        sym = _symbol(symbol)
    except ZoneError:
        return None
    extend_src = dict(geom)
    extend_src.update(raw)
    return {
        "zone_id": zone_id,
        "symbol": sym,
        "role": role,
        "notes": sanitize_notes(raw.get("notes")),
        "status": status,
        "label": _sanitize_label(raw.get("label")),
        "price_high": price_high,
        "price_low": price_low,
        "time_left": time_left,
        "time_right": time_right,
        "extend_left": _flag(extend_src, "extend_left", "extendLeft"),
        "extend_right": _flag(extend_src, "extend_right", "extendRight"),
    }


def public_zone(row: Mapping[str, Any]) -> Dict[str, Any]:
    notes = str(row.get("notes") or "")
    role = str(row.get("role") or "neutral")
    zone_id = str(row.get("zone_id") or "")
    return {
        "zone_id": zone_id,
        "symbol": str(row.get("symbol") or ""),
        "role": role if role in ROLES else "neutral",
        "notes": notes,
        "status": "archive" if row.get("status") == "archive" else "active",
        "label": str(row.get("label") or ""),
        "geometry": {
            "price_high": row.get("price_high"),
            "price_low": row.get("price_low"),
            "time_left": row.get("time_left"),
            "time_right": row.get("time_right"),
            "extend_left": bool(row.get("extend_left")),
            "extend_right": bool(row.get("extend_right")),
        },
        "cite": format_cite(zone_id, role if role in ROLES else "neutral", notes),
        "verified": False,
        "live": False,
    }


def _empty_doc() -> Dict[str, Any]:
    return {"schema": SCHEMA, "verified": False, "live": False, "zones": []}


def _load(path: Optional[Path] = None) -> Dict[str, Any]:
    target = path or zones_path()
    if not target.exists():
        return _empty_doc()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_doc()
    rows = raw.get("zones") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return _empty_doc()
    zones: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = sanitize_zone_record(row, symbol=str(row.get("symbol") or ""))
        if clean:
            zones.append(clean)
    return {"schema": SCHEMA, "verified": False, "live": False, "zones": zones}


def _save(doc: Mapping[str, Any], path: Optional[Path] = None) -> None:
    target = path or zones_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "verified": False,
        "live": False,
        "zones": list(doc.get("zones") or []),
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp.replace(target)


def list_zones(
    *,
    symbol: str = "",
    status: str = "all",
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    token = str(status or "all").strip().lower()
    if token not in {"all", "active", "archive"}:
        raise ZoneError("invalid status")
    want = ""
    if str(symbol or "").strip():
        want = _symbol(symbol)
    with _LOCK:
        rows = _load(path)["zones"]
    out: List[Dict[str, Any]] = []
    for row in rows:
        if want and row["symbol"] != want:
            continue
        if token == "active" and row["status"] != "active":
            continue
        if token == "archive" and row["status"] != "archive":
            continue
        out.append(public_zone(row))
    return out


def get_zone(zone_id: str, *, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    want = str(zone_id or "").strip()
    if not want:
        return None
    with _LOCK:
        rows = _load(path)["zones"]
    for row in rows:
        if row["zone_id"] == want:
            return public_zone(row)
    return None


def replace_symbol_snapshot(
    symbol: str,
    raw_zones: List[Any],
    *,
    path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Replace one symbol's stored geometry from a Desk drawing snapshot.

    Role, notes, and status already stored for a ``zone_id`` are kept.
    A new id defaults to neutral / empty notes / active — meta changes go
    through :func:`update_zone_meta`. Ids without a stable id are dropped.
    Geometry for other symbols is left alone. Colliding ids owned by another
    symbol are not stolen.
    """
    sym = _symbol(symbol)
    incoming: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_zones or []:
        clean = sanitize_zone_record(raw, symbol=sym)
        if not clean or clean["zone_id"] in seen:
            continue
        seen.add(clean["zone_id"])
        incoming.append(clean)
    target = path or zones_path()
    with _LOCK:
        doc = _load(target)
        previous = {row["zone_id"]: row for row in doc["zones"] if row["symbol"] == sym}
        kept: List[Dict[str, Any]] = []
        for row in doc["zones"]:
            if row["symbol"] == sym:
                continue
            if row["zone_id"] in seen:
                incoming = [item for item in incoming if item["zone_id"] != row["zone_id"]]
                seen.discard(row["zone_id"])
            kept.append(row)
        for item in incoming:
            prev = previous.get(item["zone_id"])
            if prev:
                item["role"] = prev["role"]
                item["notes"] = prev["notes"]
                item["status"] = prev["status"]
            else:
                item["role"] = "neutral"
                item["notes"] = ""
                item["status"] = "active"
        doc["zones"] = kept + incoming
        doc["verified"] = False
        doc["live"] = False
        _save(doc, target)
    return [public_zone(item) for item in incoming]


def update_zone_meta(
    zone_id: str,
    *,
    role: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Owner meta write. Geometry is not an argument and is not changed."""
    want = str(zone_id or "").strip()
    if role is not None and role not in ROLES:
        raise ZoneError("invalid role")
    if status is not None and status not in STATUSES:
        raise ZoneError("invalid status")
    clean_notes = None
    if notes is not None:
        clean_notes = sanitize_notes(notes, reject_stamp=True)
    target = path or zones_path()
    with _LOCK:
        doc = _load(target)
        found = None
        for row in doc["zones"]:
            if row["zone_id"] == want:
                found = row
                break
        if found is None:
            raise ZoneNotFound(want)
        before = (
            found["price_high"],
            found["price_low"],
            found["time_left"],
            found["time_right"],
            found["extend_left"],
            found["extend_right"],
        )
        if role is not None:
            found["role"] = role
        if clean_notes is not None:
            found["notes"] = clean_notes
        if status is not None:
            found["status"] = status
        after = (
            found["price_high"],
            found["price_low"],
            found["time_left"],
            found["time_right"],
            found["extend_left"],
            found["extend_right"],
        )
        if before != after:
            raise ZoneError("geometry is read-only")
        doc["verified"] = False
        doc["live"] = False
        _save(doc, target)
        return public_zone(found)


def session_zone_evidence(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """Harness block for ``session_card.evidence``. Not a seal."""
    try:
        zones = list_zones(status="all", path=path)
    except ZoneError:
        zones = []
    return {"zones": zones, "verified": False, "live": False, "seal": False}


def attach_proposal_zone_ref(
    proposal: Optional[Mapping[str, Any]],
    zone_id: str,
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Attach an existing zone cite. Missing ids do not invent a price band.

    P1 wires this library and ``POST /api/journal`` (``zone_id``). This repo
    has no proposal HTTP route or proposal UI; do not treat this helper as one.
    """
    out: Dict[str, Any] = dict(proposal or {})
    refs: List[Dict[str, Any]] = []
    for item in out.get("evidenceRefs") or []:
        if not isinstance(item, Mapping):
            continue
        copied = {
            "type": str(item.get("type") or "zone"),
            "zone_id": str(item.get("zone_id") or ""),
            "ref": str(item.get("ref") or ""),
            "verified": False,
            "live": False,
        }
        if copied["zone_id"] and copied["ref"]:
            refs.append(copied)
    zone = get_zone(zone_id, path=path)
    out["verified"] = False
    out["live"] = False
    out["seal"] = False
    if zone is None:
        out["evidenceRefs"] = refs
        out["zone_cite_error"] = "無法引用"
        return out
    refs.append(
        {
            "type": "zone",
            "zone_id": zone["zone_id"],
            "ref": zone["cite"],
            "verified": False,
            "live": False,
        }
    )
    out["evidenceRefs"] = refs
    out.pop("zone_cite_error", None)
    return out


def _reject_agent(request: Request, actor: Optional[str]) -> None:
    header = (request.headers.get("x-cgab-actor") or "").strip().lower()
    body_actor = str(actor or "").strip().lower()
    if header in AGENT_ACTORS or body_actor in AGENT_ACTORS:
        raise HTTPException(status_code=403, detail="Agents may only cite an existing zone_id.")


class ZoneMetaIn(BaseModel):
    """Owner meta. Geometry, verified, and live are rejected."""

    model_config = ConfigDict(extra="forbid")

    role: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("role")
    @classmethod
    def _role(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in ROLES:
            raise ValueError("invalid role")
        return value

    @field_validator("status")
    @classmethod
    def _status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in STATUSES:
            raise ValueError("invalid status")
        return value

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            return sanitize_notes(value, reject_stamp=True)
        except ZoneError as exc:
            raise ValueError(str(exc)) from exc


class ZoneSnapshotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    source: str
    zones: List[Dict[str, Any]] = Field(default_factory=list)
    actor: Optional[str] = None

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        if value != "desk_draw":
            raise ValueError("snapshot source must be desk_draw")
        return value


def _meta_http(exc: ZoneError) -> HTTPException:
    if isinstance(exc, ZoneNotFound):
        return HTTPException(status_code=404, detail=UNABLE)
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/api/desk/zones")
def list_zones_api(symbol: str = "", status: str = "all") -> Dict[str, Any]:
    try:
        rows = list_zones(symbol=symbol, status=status)
    except ZoneError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "schema": SCHEMA,
        "symbol": str(symbol or "").strip().upper(),
        "status": status,
        "zones": rows,
        "verified": False,
        "live": False,
    }


@router.put("/api/desk/zones/snapshot")
def snapshot_zones_api(
    body: ZoneSnapshotIn,
    request: Request,
    _auth: None = Depends(require_operator),
) -> Dict[str, Any]:
    _reject_agent(request, body.actor)
    try:
        rows = replace_symbol_snapshot(body.symbol, body.zones)
    except ZoneError as exc:
        raise _meta_http(exc) from exc
    return {
        "schema": SCHEMA,
        "symbol": str(body.symbol or "").strip().upper(),
        "source": "desk_draw",
        "zones": rows,
        "verified": False,
        "live": False,
    }


@router.get("/api/desk/zones/{zone_id}")
def get_zone_api(zone_id: str) -> Dict[str, Any]:
    row = get_zone(zone_id)
    if row is None:
        raise HTTPException(status_code=404, detail=UNABLE)
    return row


@router.patch("/api/desk/zones/{zone_id}")
def patch_zone_api(
    zone_id: str,
    body: ZoneMetaIn,
    request: Request,
    _auth: None = Depends(require_operator),
) -> Dict[str, Any]:
    _reject_agent(request, None)
    if body.role is None and body.notes is None and body.status is None:
        raise HTTPException(status_code=400, detail="role, notes, or status required")
    try:
        return update_zone_meta(
            zone_id,
            role=body.role,
            notes=body.notes,
            status=body.status,
        )
    except ZoneError as exc:
        raise _meta_http(exc) from exc
