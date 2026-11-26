"""Bounded read-only browser market routes, sharing the existing auth authority."""
import asyncio

from fastapi import APIRouter, HTTPException, Request, WebSocket
from pydantic import ValidationError
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect, WebSocketState

from gabfin.api.auth import validate_request
from gabfin.api.capabilities import authorize
from gabfin.api.market_gateway import MarketBusy, MarketUnavailable
from gabfin.contracts.identity import Capability, Resource
from gabfin.contracts.internal_stream import SnapshotFrame, ErrorFrame
from gabfin.contracts.web_market import MarketRequest, MarketStreamRequest


async def durable_thread(function, *args, **kwargs):
    """Cancellation waits for SQLite connections to finish before host cleanup."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


def check_access(store, token, origin, allowed_origin, query, csrf, *, write, keys=()):
    principal = validate_request(store, token, origin=origin, allowed_origin=allowed_origin,
        write=write, query=query, csrf=csrf)
    for key in keys:
        authorize(principal, Capability.READ_MARKET,
            Resource(schema_version='1.0', kind='instrument', id=key.instrument_id, owner=principal.actor_id))
    return store.remaining(token)


async def request_body(request, model):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON required')
    data = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(data) + len(chunk) > 16384:
                    raise HTTPException(413, 'Market request too large')
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, 'Market request timed out') from None
    try:
        return model.model_validate_json(bytes(data))
    except (ValueError, ValidationError):
        raise HTTPException(400, 'Invalid market request') from None


def market_router(store, *, allowed_origin, gateway):
    router = APIRouter()
    pending_streams = asyncio.BoundedSemaphore(8)

    @router.post('/market/snapshot')
    async def snapshot(request: Request):
        token = request.cookies.get('gabfin_session')
        access = dict(store=store, token=token, origin=request.headers.get('origin'),
            allowed_origin=allowed_origin, query=dict(request.query_params),
            csrf=request.headers.get('x-csrf-token'), write=True)
        try:
            await durable_thread(check_access, **access)
        except PermissionError:
            raise HTTPException(401, 'Unauthorized') from None
        body = await request_body(request, MarketRequest)
        try:
            await durable_thread(check_access, **access, keys=body.keys)
            gateway.validate_keys(body.keys)
        except PermissionError:
            raise HTTPException(403, 'Market access denied') from None
        try:
            async with gateway.open(body.keys) as feed:
                frame = await feed.receive(timeout=3)
                if not isinstance(frame, SnapshotFrame):
                    raise MarketUnavailable('Full snapshot required')
                payload = frame.payload.model_dump(mode='json')
            await durable_thread(check_access, **access, keys=body.keys)
            return JSONResponse(payload, headers={'Cache-Control':'no-store'})
        except PermissionError:
            raise HTTPException(401, 'Unauthorized') from None
        except MarketBusy:
            raise HTTPException(503, 'Market capacity reached') from None
        except Exception:
            raise HTTPException(503, 'Market unavailable') from None

    @router.websocket('/market/stream')
    async def stream(ws: WebSocket):
        access = dict(store=store, token=ws.cookies.get('gabfin_session'),
            origin=ws.headers.get('origin'), allowed_origin=allowed_origin,
            query=dict(ws.query_params), csrf=None, write=False)
        try:
            await durable_thread(check_access, **access)
        except Exception:
            await ws.close(code=1008)
            return
        if pending_streams.locked():
            await ws.close(code=1013)
            return
        await pending_streams.acquire()
        incoming = None
        code = 1000
        try:
            await ws.accept()
            message = await asyncio.wait_for(ws.receive(), 3)
            text = message.get('text')
            if message['type'] != 'websocket.receive' or not isinstance(text, str) or len(text.encode()) > 16384:
                code = 1008
                return
            body = MarketStreamRequest.model_validate_json(text)
            await durable_thread(check_access, **access, keys=body.keys)
            gateway.validate_keys(body.keys)
            # Every new browser connection starts from a full snapshot. Browser
            # cursors are validated input, never authority to skip missing state.
            async with gateway.open(body.keys) as feed:
                incoming = asyncio.create_task(ws.receive())
                while True:
                    if incoming.done():
                        message = incoming.result()
                        code = 1000 if message['type'] == 'websocket.disconnect' else 1008
                        break  # No writes or subscription mutation after handshake.
                    remaining = await durable_thread(check_access, **access, keys=body.keys)
                    try:
                        frame = await feed.receive(timeout=min(.25, remaining))
                    except TimeoutError:
                        continue  # Quiet market is not fabricated provider health.
                    encoded = frame.model_dump_json()
                    if len(encoded.encode()) > 1048576:
                        code = 1011
                        break
                    remaining = await durable_thread(check_access, **access, keys=body.keys)
                    await asyncio.wait_for(ws.send_text(encoded), min(2, remaining))
                    if isinstance(frame, ErrorFrame):
                        code = 1013
                        break
        except MarketBusy:
            code = 1013
        except MarketUnavailable:
            code = 1011
        except (PermissionError, ValueError, ValidationError):
            code = 1008
        except TimeoutError:
            code = 1013
        except WebSocketDisconnect:
            pass
        except Exception:
            code = 1011  # Never disclose internal credentials or raw failures.
        finally:
            try:
                if incoming is not None:
                    incoming.cancel()
                    await asyncio.gather(incoming, return_exceptions=True)
                if ws.client_state != WebSocketState.DISCONNECTED:
                    await ws.close(code=code)
            finally:
                pending_streams.release()

    return router
