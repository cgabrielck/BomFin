"""Desk observe routes. Read-only. Alpaca paper remains the only order path.

GET quote and GET bars read the current symbol. The optional websocket polls
the same quote envelope for that symbol and unsubscribes on disconnect.
Responses keep ``source=futu_opend`` and ``verified`` / ``live`` false.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.observe.futu_adapter import FutuObserveAdapter, build_adapter
from backend.observe.timeframes import allowed_timeframes, resolve_timeframe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observe"])

STREAM_POLL_SECONDS = 15.0
_adapter: Optional[FutuObserveAdapter] = None
_guard = threading.Lock()


def _paper_symbols() -> list[str]:
    """Alpaca paper holdings for the on-demand set. Failure subscribes nothing extra."""
    try:
        from backend.api.app import _broker

        summary = _broker.get_account_summary()
    except Exception:
        logger.info("futu observe paper positions unavailable")
        return []
    symbols: list[str] = []
    for pos in getattr(summary, "positions", None) or []:
        symbol = getattr(pos, "symbol", "")
        if symbol:
            symbols.append(str(symbol))
    return symbols


def build_default_adapter() -> FutuObserveAdapter:
    return build_adapter(position_symbols=_paper_symbols)


def get_adapter() -> FutuObserveAdapter:
    global _adapter
    with _guard:
        if _adapter is None:
            _adapter = build_default_adapter()
        return _adapter


def reset_adapter(adapter: Optional[FutuObserveAdapter] = None) -> None:
    global _adapter
    with _guard:
        previous = _adapter
        _adapter = adapter
    if previous is not None and previous is not adapter:
        previous.close()


def shutdown() -> None:
    reset_adapter(None)


def _seal_route(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(payload)
    body["source"] = "futu_opend"
    body["vendor"] = "futu_opend"
    body["verified"] = False
    body["live"] = False
    return body


@router.get("/api/observe/quote/{symbol}")
def observe_quote(symbol: str) -> Dict[str, Any]:
    return _seal_route(get_adapter().quote(symbol))


@router.get("/api/observe/bars/{symbol}")
def observe_bars(symbol: str, tf: str, limit: int = 300) -> Dict[str, Any]:
    try:
        resolve_timeframe(tf)
    except ValueError as exc:
        allowed = ", ".join(allowed_timeframes())
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe. Allowed: {allowed}") from exc
    return _seal_route(get_adapter().bars(symbol, tf, limit=limit))


@router.post("/api/observe/leave")
def observe_leave() -> Dict[str, Any]:
    """Drop the current chart symbol and unsubscribe it when nothing else needs it."""
    return _seal_route(get_adapter().leave_chart())


def _stream_frame(symbol: str) -> Dict[str, Any]:
    frame = _seal_route(get_adapter().quote(symbol))
    frame["delivery"] = "poll"
    return frame


@router.websocket("/api/observe/stream")
async def observe_stream(websocket: WebSocket) -> None:
    """Poll the quote envelope for one symbol. Disconnect unsubscribes the chart."""
    await websocket.accept()
    symbol = ""
    held_gen: Optional[int] = None
    try:
        while True:
            timeout = STREAM_POLL_SECONDS if symbol else 30.0
            try:
                incoming = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
            except asyncio.TimeoutError:
                incoming = None
            if isinstance(incoming, dict):
                if incoming.get("op") == "leave":
                    break
                raw_symbol = incoming.get("symbol")
                if raw_symbol:
                    symbol = str(raw_symbol).strip()
            if not symbol:
                continue
            frame = await asyncio.to_thread(_stream_frame, symbol)
            raw_gen = frame.get("view_gen")
            if isinstance(raw_gen, int):
                held_gen = raw_gen
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        return
    finally:
        # Synchronous so a cancelled socket still drops the chart subscription.
        if held_gen is not None:
            try:
                get_adapter().leave_chart(generation=held_gen)
            except Exception:
                logger.info("futu observe degrade: opend_unreachable")
