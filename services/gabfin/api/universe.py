"""Authenticated candidate provenance and bounded list resolution."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from gabfin.api.auth import read_origin, validate_request
from gabfin.api.capabilities import require_scope
from gabfin.api.research import _guarded_query, _json_body
from gabfin.contracts.identity import Capability
from gabfin.universe.resolve import resolve_batch


class SymbolList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbols: StrictStr


def universe_router(store, *, allowed_origin, candidates, lookup, directory=None):
    router = APIRouter()

    def guard(request, *, write=False):
        token = request.cookies.get('gabfin_session')
        origin = request.headers.get('origin')
        query = _guarded_query(request.query_params)
        if write and (not token or origin != allowed_origin or query):
            raise HTTPException(401, 'Unauthorized')
        try:
            user = validate_request(store, token, origin=read_origin(origin, allowed_origin),
                allowed_origin=allowed_origin, write=False, query=query, csrf=None)
        except PermissionError:
            raise HTTPException(401, 'Unauthorized') from None
        if write:
            try:
                validate_request(store, token, origin=origin, allowed_origin=allowed_origin,
                    write=True, query=query, csrf=request.headers.get('x-csrf-token'))
            except PermissionError:
                raise HTTPException(403, 'Forbidden') from None
        try:
            require_scope(user, Capability.START_RESEARCH)
        except PermissionError:
            raise HTTPException(403, 'Research access denied') from None

    @router.get('/v1/universe')
    async def universe(request: Request):
        guard(request)
        now = datetime.now(timezone.utc)
        results = []
        for row in candidates.universe_at(now):
            metadata = None
            if directory is not None:
                try:
                    metadata = directory.by_id(row.instrument)
                except KeyError:
                    pass
            results.append({'observation': row.model_dump(mode='json'), 'instrument': metadata,
                'evidence': [candidates.evidence(identity).model_dump(mode='json') for identity in row.evidence]})
        return {'as_of': now.isoformat(), 'candidates': results, 'source_mode': 'manual'}

    @router.post('/v1/universe/resolve')
    async def resolve(request: Request):
        guard(request, write=True)
        try:
            body = SymbolList.model_validate(await _json_body(request))
            results = await asyncio.to_thread(resolve_batch, body.symbols, lookup)
        except (ValidationError, ValueError):
            raise HTTPException(422, 'Provide between 1 and 50 valid list entries') from None
        return {'results': results}

    return router
