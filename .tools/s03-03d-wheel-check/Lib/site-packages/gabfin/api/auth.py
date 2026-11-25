"""Transport-independent HTTP/WebSocket guard; no IP/header-derived identity."""
from urllib.parse import urlsplit

def validate_request(store,token,*,origin,allowed_origin,write,query,csrf):
    parsed=urlsplit(allowed_origin)
    if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:raise ValueError('Exact HTTPS origin required')
    if query or origin!=allowed_origin or not token:raise PermissionError('Unauthorized')
    principal=store.resolve(token)
    if write:store.check_csrf(token,csrf)
    return principal

import asyncio
from starlette.websockets import WebSocketDisconnect
from fastapi import FastAPI,Request,WebSocket,HTTPException
from pydantic import BaseModel,ConfigDict,StrictStr
class PairingInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code: StrictStr

def create_app(store,*,allowed_origin):
    parsed=urlsplit(allowed_origin)
    if parsed.scheme!='https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:raise ValueError('Exact HTTPS origin required')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    def guard(request,write=False):
        try:return validate_request(store,request.cookies.get('gabfin_session'),origin=(request.headers.get('origin') or (allowed_origin if not write else None)),allowed_origin=allowed_origin,write=write,query=dict(request.query_params),csrf=request.headers.get('x-csrf-token'))
        except PermissionError:raise HTTPException(401,'Unauthorized') from None
    @app.post('/pair')
    def pair(body:PairingInput,request:Request):
        if request.headers.get('origin')!=allowed_origin or request.query_params:raise HTTPException(401,'Unauthorized')
        try:token,csrf=store.issue_session(body.code)
        except PermissionError:raise HTTPException(401,'Unauthorized') from None
        from fastapi.responses import JSONResponse
        response=JSONResponse({'csrf':csrf});response.set_cookie('gabfin_session',token,httponly=True,secure=True,samesite='strict',max_age=store.session_seconds)
        return response
    @app.get('/session')
    def session(request:Request):return guard(request).model_dump(mode='json')
    @app.post('/logout')
    def logout(request:Request):
        guard(request,True);store.revoke(request.cookies['gabfin_session'])
        from fastapi.responses import JSONResponse
        response=JSONResponse({'ok':True});response.delete_cookie('gabfin_session',httponly=True,secure=True,samesite='strict');return response
    @app.websocket('/ws')
    async def websocket(ws:WebSocket):
        try:validate_request(store,ws.cookies.get('gabfin_session'),origin=ws.headers.get('origin'),allowed_origin=allowed_origin,write=False,query=dict(ws.query_params),csrf=None)
        except PermissionError:
            await ws.close(code=1008);return
        await ws.accept()
        try:
            while True:
                try:remaining=store.remaining(ws.cookies["gabfin_session"])
                except PermissionError:
                    await ws.close(code=1008);return
                await asyncio.wait_for(ws.receive_text(),timeout=remaining)
                try:store.resolve(ws.cookies['gabfin_session'])
                except PermissionError:
                    await ws.close(code=1008);return
                await ws.send_json({'authenticated':True})
        except asyncio.TimeoutError:
            await ws.close(code=1008)
        except WebSocketDisconnect:
            return
    return app
