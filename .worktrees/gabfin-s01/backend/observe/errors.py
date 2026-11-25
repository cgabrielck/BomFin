"""Closed degrade reasons for the OpenD observe path."""
from __future__ import annotations

DEGRADE_CODES = frozenset(
    {
        "opend_unreachable",
        "permission_denied",
        "quota_exhausted",
        "empty",
        "unmapped_symbol",
    }
)

_QUOTA_MARKERS = (
    "quota",
    "额度",
    "額度",
    "too many",
    "frequency",
    "too frequent",
    "限频",
    "限頻",
    "频率太高",
    "頻率太高",
)
_PERMISSION_MARKERS = (
    "permission",
    "no right",
    "not authorized",
    "无权",
    "無權",
    "没有权限",
    "沒有權限",
    "no authority",
    "denied",
)


class ObserveFailure(Exception):
    """A honest observe failure. ``detail`` is local wording, never an account id."""

    def __init__(self, code: str, detail: str = ""):
        if code not in DEGRADE_CODES:
            code = "opend_unreachable"
        super().__init__(code)
        self.code = code
        self.detail = detail


def classify_gateway_message(message: str) -> str:
    """Map a gateway failure onto the closed degrade set. Unknown stays unreachable."""
    text = (message or "").lower()
    if any(marker in text for marker in _QUOTA_MARKERS):
        return "quota_exhausted"
    if any(marker in text for marker in _PERMISSION_MARKERS):
        return "permission_denied"
    return "opend_unreachable"
