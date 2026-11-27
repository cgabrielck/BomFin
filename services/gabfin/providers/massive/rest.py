"""Bounded Massive REST requests and proxy-pinned pagination."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit
import urllib.error
import urllib.request

from gabfin.providers.massive.config import MassiveConfig


@dataclass(frozen=True)
class Request:
    url: str = field(repr=False)
    headers: dict[str, str] = field(repr=False)


@dataclass(frozen=True)
class Response:
    status: int
    payload: dict = field(repr=False)


class MassiveRestError(RuntimeError):
    """Stable failure codes with no provider payload or endpoint."""

    def __init__(self, reason: str, *, status: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _transport(request: Request) -> Response:
    req = urllib.request.Request(request.url, headers=request.headers)
    # Never follow a redirect with the customer's credential header.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=15) as handle:
            return Response(handle.status, json.load(handle))
    except urllib.error.HTTPError as error:
        return Response(error.code, {})


class MassiveRestClient:
    """One shared per-key limiter; callers must reuse this client across planes."""

    def __init__(self, config: MassiveConfig, *, transport=None, clock=time.monotonic):
        self._config = config
        self._transport = transport or _transport
        self._clock = clock
        self._window = deque()
        self._lock = threading.Lock()
        self._requests = 0
        self._limited = 0

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {'requests': self._requests, 'rate_limited': self._limited}

    def _reserve(self):
        with self._lock:
            now = self._clock()
            while self._window and self._window[0] <= now - 60:
                self._window.popleft()
            if len(self._window) >= self._config.rest_qpm:
                self._limited += 1
                raise MassiveRestError('rate_limited', status=429)
            self._window.append(now)
            self._requests += 1

    def get(self, path: str) -> dict:
        parts = urlsplit(path)
        if (parts.scheme or parts.netloc or not path.startswith('/') or path.startswith('//')
                or parts.fragment or '\\' in path
                or any(ord(char) < 32 for char in path)):
            raise MassiveRestError('invalid_path')
        pairs = [(name, value) for name, value in parse_qsl(parts.query, keep_blank_values=True)
                 if name.lower() not in ('apikey', 'api_key', 'key', 'token', 'access_token')]
        query = urlencode(pairs)
        safe_path = parts.path + ('?' + query if query else '')
        self._reserve()
        request = Request(self._config.base_url + safe_path,
                          {'X-Proxy-Key': self._config.api_key.get_secret_value(),
                           'Accept': 'application/json'})
        try:
            response = self._transport(request)
        except Exception:
            raise MassiveRestError('transport_failed') from None
        if response.status != 200:
            raise MassiveRestError('http_error', status=response.status)
        if not isinstance(response.payload, dict):
            raise MassiveRestError('invalid_response')
        if response.payload.get('status') in ('ERROR', 'NOT_AUTHORIZED'):
            raise MassiveRestError('provider_error')
        return response.payload

    def results(self, path: str, *, max_pages: int = 1000):
        seen = set()
        for _ in range(max_pages):
            if path in seen:
                raise MassiveRestError('pagination_cycle')
            seen.add(path)
            payload = self.get(path)
            rows = payload.get('results', [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise MassiveRestError('invalid_results')
            yield from rows
            next_url = payload.get('next_url')
            if not next_url:
                return
            if not isinstance(next_url, str):
                raise MassiveRestError('invalid_pagination')
            parts = urlsplit(next_url)
            path = parts.path + ('?' + parts.query if parts.query else '')
        raise MassiveRestError('pagination_limit')
