"""Owner-operated OpenD endpoint. Loopback by default; no public tunnel."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass

from backend.observe.errors import ObserveFailure
from backend.observe.symbols import parse_internal

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11111
MAX_WATCHLIST = 8


@dataclass(frozen=True)
class OpenDConfig:
    host: str
    port: int
    watchlist: tuple[str, ...]


def _local_or_private(host: str) -> str:
    text = (host or "").strip()
    if not text:
        raise ObserveFailure("opend_unreachable", "OpenD host is empty")
    if text.lower() == "localhost":
        return "localhost"
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ObserveFailure("opend_unreachable", "OpenD host is not a local address") from exc
    if address.is_loopback or address.is_private or address.is_link_local:
        return str(address)
    raise ObserveFailure("opend_unreachable", "OpenD host is not a local or private address")


def _port(raw: str) -> int:
    try:
        port = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ObserveFailure("opend_unreachable", "OpenD port is not a number") from exc
    if port < 1 or port > 65535:
        raise ObserveFailure("opend_unreachable", "OpenD port is out of range")
    return port


def _watchlist(raw: str) -> tuple[str, ...]:
    found: list[str] = []
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            symbol = parse_internal(token)
        except ObserveFailure:
            continue
        if symbol not in found:
            found.append(symbol)
        if len(found) >= MAX_WATCHLIST:
            break
    return tuple(found)


def load_config(env: dict[str, str] | None = None) -> OpenDConfig:
    """Read ``FUTU_OPEND_HOST`` / ``PORT`` / ``WATCHLIST``. Defaults are local."""
    source = os.environ if env is None else env
    host = _local_or_private(source.get("FUTU_OPEND_HOST", DEFAULT_HOST))
    port = _port(source.get("FUTU_OPEND_PORT", str(DEFAULT_PORT)))
    watchlist = _watchlist(source.get("FUTU_OPEND_WATCHLIST", ""))
    return OpenDConfig(host=host, port=port, watchlist=watchlist)
