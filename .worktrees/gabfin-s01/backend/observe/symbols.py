"""US-only symbol map. Internal symbols match the Desk chart: no market prefix."""
from __future__ import annotations

import re

from backend.observe.errors import ObserveFailure

# One optional class suffix (BRK.B). Market prefixes are rejected, not rewritten.
_INTERNAL = re.compile(r"^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,5})?$")
_MARKET_PREFIXES = ("HK.", "SH.", "SZ.", "SG.", "JP.", "US.")
_MAX_LEN = 16


def parse_internal(symbol: str) -> str:
    """Return the Desk symbol or raise ``unmapped_symbol``.

    ``AAPL`` and ``BRK.B`` map. ``US.AAPL``, ``HK.00700``, and blank do not.
    Callers pass the internal form; the ``US.`` prefix is added only on the way out.
    """
    text = (symbol or "").strip().upper()
    if not text or len(text) > _MAX_LEN or text.startswith(".") or text.startswith(_MARKET_PREFIXES):
        raise ObserveFailure("unmapped_symbol")
    if not _INTERNAL.fullmatch(text):
        raise ObserveFailure("unmapped_symbol")
    return text


def to_vendor(symbol: str) -> str:
    """``AAPL`` → ``US.AAPL``. ``BRK.B`` → ``US.BRK.B``."""
    return "US." + parse_internal(symbol)


def from_vendor(code: str) -> str:
    """``US.AAPL`` → ``AAPL``. ``US.BRK.B`` → ``BRK.B``. Other markets stay unmapped."""
    text = (code or "").strip().upper()
    if not text.startswith("US."):
        raise ObserveFailure("unmapped_symbol")
    return parse_internal(text[3:])
