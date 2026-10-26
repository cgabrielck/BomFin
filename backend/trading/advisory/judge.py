"""Closed-output entry judge.

Phase 1 default is off (``AI_JUDGE=0``): :func:`evaluate_entry` returns allow
and does not call a client. There is no network model in this package.

A known veto, a timeout, bad JSON, empty sources, or a size field means
silence (no buy). An unknown veto code is logged and does not block.
``conviction_tier`` is recorded by the caller and must not change quantity.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

# MODULAR §5.3 / method §5. Unknown codes do not block.
KNOWN_VETO_CODES = frozenset(
    {
        "CALENDAR_BLACKOUT",
        "STALE_DATA",
        "CORR_CAP",
        "KILL_ACTIVE",
        "EVENT_FREEZE",
    }
)

CONVICTION_TIERS = frozenset({"low", "med", "high"})

# Size, broker, and constitution fields. A payload that carries them is not
# an order and is not handed to a sizer.
FORBIDDEN_JUDGE_FIELDS = frozenset(
    {
        "quantity",
        "qty",
        "shares",
        "notional",
        "size",
        "raw_size",
        "order_type",
        "order_class",
        "broker_order_id",
        "broker_id",
        "mandate",
        "kill",
        "kill_switch",
        "tune",
        "live",
        "allow_live",
    }
)

JUDGE_TIMEOUT_S = 3.0

JudgeClient = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class JudgeDecision:
    """Result of one entry-judge call. ``allow`` is the only buy switch."""

    allow: bool
    veto_codes: tuple[str, ...] = ()
    ignored_codes: tuple[str, ...] = ()
    conviction_tier: Optional[str] = None
    sources: tuple[dict, ...] = ()
    notes: str = ""
    failure: Optional[str] = None
    noop: bool = False

    @property
    def blocks_buy(self) -> bool:
        return not self.allow


def ai_judge_enabled() -> bool:
    """``AI_JUDGE=0`` (and unset) is off. Only an explicit on-token enables."""
    token = str(os.getenv("AI_JUDGE", "0") or "").strip().lower()
    return token in {"1", "true", "yes", "on"}


def _allow_noop() -> JudgeDecision:
    return JudgeDecision(allow=True, noop=True, notes="AI_JUDGE=0")


def _silence(reason: str, *, ignored: Sequence[str] = (), notes: str = "") -> JudgeDecision:
    return JudgeDecision(
        allow=False,
        ignored_codes=tuple(ignored),
        failure=reason,
        notes=notes,
    )


def _valid_sources(raw: Any) -> tuple[dict, ...]:
    if not isinstance(raw, list) or not raw:
        return ()
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            return ()
        type_ = str(item.get("type") or "").strip()
        ref = str(item.get("ref") or "").strip()
        asof = str(item.get("asof") or "").strip()
        if not type_ or not ref or not asof:
            return ()
        out.append({"type": type_, "ref": ref, "asof": asof})
    return tuple(out)


def parse_judge_payload(raw: Any) -> JudgeDecision:
    """Parse a model payload. Failure and known vetoes do not allow a buy.

    Unknown veto codes are returned on ``ignored_codes`` and do not block
    when the rest of the payload is valid. ``quantity`` / ``notional`` (and
    the other forbidden fields) are a schema failure, not an order.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return _silence("bad_json")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return _silence("bad_json", notes="judge payload was not JSON")
    elif isinstance(raw, Mapping):
        data = dict(raw)
    else:
        return _silence("bad_json")

    if not isinstance(data, dict):
        return _silence("bad_json")

    forbidden = sorted(
        str(key)
        for key in data.keys()
        if str(key).strip().lower() in FORBIDDEN_JUDGE_FIELDS
    )
    if forbidden:
        return _silence(
            "forbidden_fields",
            notes="judge payload rejected size/broker fields: " + ", ".join(forbidden),
        )

    raw_codes = data.get("veto_codes") or []
    if isinstance(raw_codes, str):
        raw_codes = [raw_codes]
    if not isinstance(raw_codes, list):
        return _silence("bad_json", notes="veto_codes must be a list")

    known: list[str] = []
    ignored: list[str] = []
    for item in raw_codes:
        code = str(item or "").strip()
        if not code:
            continue
        if code in KNOWN_VETO_CODES:
            if code not in known:
                known.append(code)
        elif code not in ignored:
            ignored.append(code)

    tier_raw = data.get("conviction_tier")
    tier: Optional[str]
    if tier_raw in (None, ""):
        tier = None
    else:
        tier = str(tier_raw).strip().lower()
        if tier not in CONVICTION_TIERS:
            return _silence("bad_tier", ignored=ignored, notes=f"conviction_tier {tier_raw!r}")

    sources = _valid_sources(data.get("sources"))
    if not sources:
        return _silence("empty_sources", ignored=ignored, notes="judge sources empty")

    notes = str(data.get("notes") or "")
    if known:
        return JudgeDecision(
            allow=False,
            veto_codes=tuple(known),
            ignored_codes=tuple(ignored),
            conviction_tier=tier,
            sources=sources,
            notes=notes,
        )
    return JudgeDecision(
        allow=True,
        veto_codes=(),
        ignored_codes=tuple(ignored),
        conviction_tier=tier,
        sources=sources,
        notes=notes,
    )


def _invoke_client(client: JudgeClient, setup: Mapping[str, Any], timeout_s: float) -> JudgeDecision:
    box: dict[str, Any] = {}

    def _run() -> None:
        try:
            box["value"] = client(setup)
        except TimeoutError:
            box["failure"] = "timeout"
        except Exception as exc:  # model/stub errors are silence, not a buy
            box["failure"] = "judge_error"
            box["notes"] = str(exc)

    worker = threading.Thread(target=_run, name="ai-judge", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        return _silence("timeout", notes=f"judge exceeded {timeout_s:.1f}s")
    if box.get("failure"):
        return _silence(str(box["failure"]), notes=str(box.get("notes") or ""))
    return parse_judge_payload(box.get("value"))


def evaluate_entry(
    setup: Mapping[str, Any],
    *,
    client: Optional[JudgeClient] = None,
    timeout_s: float = JUDGE_TIMEOUT_S,
) -> JudgeDecision:
    """Judge one playbook-VALID buy. Off means no-op and the client is not called.

    The setup must not be treated as an order. This function never returns a
    quantity. Callers keep the quantity they already sized.
    """
    if not ai_judge_enabled():
        return _allow_noop()
    if client is None:
        return _silence("judge_unconfigured", notes="AI_JUDGE=1 but no judge client is installed")
    try:
        limit = float(timeout_s)
    except (TypeError, ValueError):
        limit = JUDGE_TIMEOUT_S
    if limit <= 0:
        limit = JUDGE_TIMEOUT_S
    return _invoke_client(client, setup, limit)
