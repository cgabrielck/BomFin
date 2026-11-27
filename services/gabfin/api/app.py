"""Compose the existing pairing/session app with read-only market routes."""
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from gabfin.api.auth import create_app
from gabfin.api.market import market_router
from gabfin.api.analysis import analysis_router
from gabfin.api.research import research_router


class ExactTlsOrigin:
    """No proxy-header or localhost identity shortcut; applies to auth too."""
    def __init__(self, app, *, origin):
        self.app = app
        self.authority = urlsplit(origin).netloc.lower()

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            headers = dict(scope['headers'])
            host = headers.get(b'host', b'').decode('latin1').lower()
            if scope['scheme'] not in ('https', 'wss') or host != self.authority:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                else:
                    await JSONResponse({'detail': 'Secure origin required'}, status_code=401)(scope, receive, send)
                return
        async def private_send(message):
            if message['type'] == 'http.response.start':
                private = (scope['path'].startswith('/market/') or scope['path'].startswith('/v1/')
                           or scope['path'] in ('/pair', '/session', '/logout'))
                if private:
                    headers = [(key,value) for key,value in message.get('headers', []) if key.lower() != b'cache-control']
                    message = {**message, 'headers': headers + [(b'cache-control', b'no-store')]}
            await send(message)
        await self.app(scope, receive, private_send)


def create_market_app(store, *, allowed_origin, gateway, static_dir: Path | None = None,
                      analysis=None, research=None, universe=None):
    """The browser app: pairing, market, analysis and research routes.

    `analysis` is optional so that a deployment without a tape or a FRED
    key still serves the market routes. When it is absent the analysis
    routes are not mounted, and the browser gets a 404 rather than a
    route that answers with an empty series.

    `research` is optional for the same reason: a deployment with no
    configured research model still serves the market routes. It holds
    `{'jobs': ResearchJobs(...)}`, the one injected object the research
    routes need.

    A research job runs in the background, so the app stops them when
    it shuts down. The handler is registered here rather than in the
    launcher, so every way of building the app gets the same teardown.
    """
    app = create_app(store, allowed_origin=allowed_origin)
    app.add_middleware(ExactTlsOrigin, origin=allowed_origin)

    app.include_router(market_router(store, allowed_origin=allowed_origin, gateway=gateway))
    if analysis is not None:
        app.include_router(analysis_router(store, allowed_origin=allowed_origin, **analysis))
    if research is not None:
        app.include_router(research_router(store, allowed_origin=allowed_origin, **research))
        _stop_research_on_shutdown(app, research.get('jobs'))
    if universe is not None:
        from gabfin.api.universe import universe_router
        app.include_router(universe_router(store, allowed_origin=allowed_origin, **universe))
    if static_dir is not None:
        app.mount('/', StaticFiles(directory=static_dir, html=True), name='desk')
    return app


def _stop_research_on_shutdown(app, jobs) -> None:
    """Cancel the background research jobs when the app stops.

    A job that outlived the process would keep paying for model calls
    that nobody is waiting for. The jobs object records the
    cancellation itself, so the job ends as failed rather than as
    queued forever.

    The app's lifespan is extended rather than replaced: the pairing
    and session app owns its own startup and shutdown, and this only
    adds the research teardown to it.
    """
    if jobs is None:
        return
    existing = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with existing(app) as state:
            yield state
        shutdown = getattr(jobs, 'shutdown', None)
        if shutdown is not None:
            await shutdown()

    app.router.lifespan_context = lifespan
