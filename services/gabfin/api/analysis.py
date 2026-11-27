"""Read-only analysis routes for the browser.

These routes read. They never write, never decide, and never order.
The authentication and capability authority is the same one the market
routes use: a session, an exact origin, and a capability in scope.

Every failure has a shape the browser can act on. A missing series is
a 404, an invalid request is a 400, and a plane that cannot answer
right now is a 503 with a reason. None of them leak an internal
detail.
"""
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from gabfin.api.auth import validate_request
from gabfin.api.capabilities import authorize, require_scope
from gabfin.contracts.analysis import (
    CapabilitiesResponse,
    IndicatorResponse,
    MacroResponse,
)
from gabfin.contracts.identity import Capability, Resource
from gabfin.contracts.market import Timeframe, TimeUnit

#: Query names that would carry a credential. The auth guard refuses a
#: request that puts a secret in the URL, so these are checked and the
#: rest of the query is free to carry analysis parameters.
CREDENTIAL_QUERY_NAMES = frozenset({
    'token', 'csrf', 'session', 'authorization', 'gabfin_session',
    'gabfin_csrf', 'access_token', 'api_key',
})


def _guarded_query(params) -> dict[str, str]:
    """The credential-bearing part of a query, which the guard refuses."""
    return {
        key: value for key, value in params.items()
        if key.lower() in CREDENTIAL_QUERY_NAMES
    }


def _timeframe(text: str | None) -> Timeframe:
    """Parse the `1min` / `1day` timeframe notation."""
    if not text:
        raise HTTPException(400, 'Invalid indicator request')
    unit = text.lstrip('0123456789')
    count = text[: len(text) - len(unit)]
    if not count or not unit:
        raise HTTPException(400, 'Invalid indicator request')
    units = {
        'min': TimeUnit.MINUTE,
        'hour': TimeUnit.HOUR,
        'day': TimeUnit.TRADING_DAY,
        'week': TimeUnit.WEEK,
        'month': TimeUnit.MONTH,
    }
    if unit not in units:
        raise HTTPException(400, 'Invalid indicator request')
    try:
        return Timeframe(count=int(count), unit=units[unit])
    except (ValueError, ValidationError):
        raise HTTPException(400, 'Invalid indicator request') from None


def _uuid(text: str | None) -> UUID:
    try:
        return UUID(text)
    except (TypeError, ValueError):
        raise HTTPException(400, 'Invalid indicator request') from None


def _date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPException(400, 'Invalid macro request') from None


def analysis_router(store, *, allowed_origin, indicators, macro, capabilities):
    """The analysis routes. The planes are injected, so the routes own
    no provider client and no stored history."""
    router = APIRouter()

    def principal(request: Request):
        token = request.cookies.get('gabfin_session')
        try:
            return validate_request(
                store, token, origin=request.headers.get('origin'),
                allowed_origin=allowed_origin, write=False,
                query=_guarded_query(request.query_params), csrf=None)
        except PermissionError:
            raise HTTPException(401, 'Unauthorized') from None

    @router.get('/v1/indicators')
    async def indicator_series(request: Request):
        user = principal(request)
        instrument_id = _uuid(request.query_params.get('instrument_id'))
        try:
            authorize(user, Capability.READ_MARKET,
                     Resource(schema_version='1.0', kind='instrument',
                              id=instrument_id, owner=user.actor_id))
        except PermissionError:
            raise HTTPException(403, 'Market access denied') from None
        timeframe = _timeframe(request.query_params.get('timeframe'))
        names = request.query_params.getlist('indicator')
        limit_text = request.query_params.get('limit')
        try:
            limit = int(limit_text) if limit_text else 500
        except ValueError:
            raise HTTPException(400, 'Invalid indicator request') from None
        try:
            response: IndicatorResponse = indicators.series(
                instrument_id, timeframe, indicators=names or None, limit=limit)
        except Exception as error:
            reason = getattr(error, 'reason', None)
            if reason == 'unknown_indicator':
                raise HTTPException(400, 'Invalid indicator request') from None
            if reason == 'invalid_limit':
                raise HTTPException(400, 'Invalid indicator request') from None
            if reason == 'insufficient_history':
                raise HTTPException(404, 'Indicator series not found') from None
            if reason == 'unknown_source_coverage':
                # The stored history does not name a venue the contract
                # accepts, so no indicator can be computed from it. This is
                # a missing series, not an outage.
                raise HTTPException(404, 'Indicator series not found') from None
            raise HTTPException(503, 'Indicator plane unavailable') from None
        return response

    @router.get('/v1/macro')
    async def macro_snapshot(request: Request):
        user = principal(request)
        try:
            require_scope(user, Capability.READ_MARKET)
        except PermissionError:
            raise HTTPException(403, 'Market access denied') from None
        series_id = request.query_params.get('series_id')
        # The date is parsed outside the plane's failure handling: a bad
        # date is an invalid request, not an unavailable plane.
        as_of = _date(request.query_params.get('as_of'))
        try:
            response: MacroResponse = macro.snapshot(series_id, as_of=as_of)
        except Exception as error:
            reason = getattr(error, 'reason', None)
            if reason == 'unknown_series':
                raise HTTPException(404, 'Macro series not found') from None
            raise HTTPException(503, 'Macro plane unavailable') from None
        return response

    @router.get('/v1/capabilities')
    async def feed_capabilities(request: Request):
        user = principal(request)
        try:
            require_scope(user, Capability.READ_MARKET)
        except PermissionError:
            raise HTTPException(403, 'Market access denied') from None
        try:
            response: CapabilitiesResponse = capabilities.snapshot()
        except Exception:
            raise HTTPException(503, 'Capability plane unavailable') from None
        return response

    return router
