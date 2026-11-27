"""The FRED REST client.

FRED requires its API key in the query string. That means the key will
end up in any URL this module produces, so every path out of this module
has to be careful with it: it must not appear in a log line, in an
exception message, or in anything that reaches a user or a browser.

The rule this module enforces is that the key is read from the
environment, is put in the URL, and is then removed from the URL before
anything else sees it. Errors carry the series id and the status, never
the request.
"""
import json
import urllib.parse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

#: FRED's base URL for series observations.
SERIES_URL = 'https://api.stlouisfed.org/fred/series/observations'

#: FRED's base URL for series metadata.
SERIES_INFO_URL = 'https://api.stlouisfed.org/fred/series'

#: The environment variable that holds the key.
KEY_VARIABLE = 'FRED_API_KEY'


class MacroError(RuntimeError):
    """A FRED request failed.

    The message never contains the API key or the full request URL.
    """


class MacroKeyMissing(MacroError):
    """The API key is not configured."""


@dataclass(frozen=True)
class Request:
    """An outgoing request. The key lives here and nowhere else."""

    url: str
    params: dict[str, str]
    method: str = 'GET'


@dataclass(frozen=True)
class Response:
    """An incoming response."""

    status: int
    body: str
    headers: dict[str, str] | None = None


#: A transport sends a request and returns a response. It is injected so
#: the client can be tested without a network or a key.
Transport = object


def build_url(params: dict[str, str]) -> str:
    """Build a URL with its query string, sorted for a stable cache key."""
    query = urllib.parse.urlencode(sorted(params.items()))
    return f'{SERIES_URL}?{query}'


def redact(text: str, key: str | None) -> str:
    """Remove the API key from any text that might be logged.

    This is the single choke point for the key. Every error message and
    every log line that could contain a URL passes through it, so a key
    that appears in an unexpected place still cannot reach a log.
    """
    if not key:
        return text
    if key in text:
        return text.replace(key, 'REDACTED')
    # The key may be URL-encoded in a query string.
    encoded = urllib.parse.quote(key, safe='')
    if encoded and encoded in text:
        return text.replace(encoded, 'REDACTED')
    return text


def read_key(environ: dict[str, str] | None = None) -> str | None:
    """Read the API key from the environment."""
    source = environ if environ is not None else _environment()
    value = source.get(KEY_VARIABLE)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _environment() -> dict[str, str]:
    import os

    return dict(os.environ)


class FredClient:
    """A FRED client that keeps its key out of sight."""

    def __init__(
        self,
        key: str | None = None,
        transport: Transport | None = None,
        rate_limiter=None,
    ):
        self._key = key if key is not None else read_key()
        self._transport = transport
        self._rate_limiter = rate_limiter

    @property
    def configured(self) -> bool:
        return self._key is not None

    def _require_key(self) -> str:
        if self._key is None:
            raise MacroKeyMissing(
                f'{KEY_VARIABLE} is not set; macro data cannot be fetched'
            )
        return self._key

    def observations(
        self,
        series_id: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict]:
        """Fetch the observations of one series.

        The result is a list of raw FRED observation dicts. Parsing them
        into contracts happens in `series.py`, which is where the rules
        about missing values and release dates live.
        """
        key = self._require_key()
        params = {
            'series_id': series_id,
            'file_type': 'json',
            'api_key': key,
        }
        if start is not None:
            params['observation_start'] = start.isoformat()
        if end is not None:
            params['observation_end'] = end.isoformat()

        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        request = Request(url=build_url(params), params=params)
        response = self._send(request)
        return _parse(response, series_id, key)

    def _send(self, request: Request) -> Response:
        if self._transport is None:
            raise MacroError('No transport is configured')
        try:
            return self._transport(request)
        except MacroError:
            raise
        except Exception as error:
            # The request URL carries the key, so a transport error that
            # quotes it would leak the key into a log. The message is
            # rebuilt from the series and the error type instead.
            raise MacroError(
                redact(
                    f'{request.params.get("series_id", "the series")}: the '
                    f'request failed ({type(error).__name__})',
                    self._key,
                )
            ) from None

    def release(
        self,
        series_id: str,
    ) -> dict | None:
        """Fetch the latest release of one series, or None if there is none."""
        key = self._require_key()
        params = {
            'series_id': series_id,
            'file_type': 'json',
            'api_key': key,
        }
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        request = Request(url=build_url(params), params=params)
        response = self._send(request)
        try:
            payload = json.loads(response.body)
        except json.JSONDecodeError as error:
            raise MacroError(
                redact(
                    f'{series_id}: the response was not JSON ({error})',
                    key,
                )
            ) from None
        if response.status != 200:
            raise MacroError(
                redact(
                    f'{series_id}: FRED returned {response.status}',
                    key,
                )
            )
        observations = payload.get('observations')
        if not observations:
            return None
        return observations[-1]


def _parse(response: Response, series_id: str, key: str) -> list[dict]:
    """Parse a FRED response, keeping the key out of any message."""
    if response.status != 200:
        raise MacroError(
            redact(f'{series_id}: FRED returned {response.status}', key)
        )
    try:
        payload = json.loads(response.body)
    except json.JSONDecodeError as error:
        raise MacroError(
            redact(f'{series_id}: the response was not JSON ({error})', key)
        ) from None
    observations = payload.get('observations')
    if observations is None:
        raise MacroError(redact(f'{series_id}: the response had no observations', key))
    return observations


def parse_value(raw: object) -> Decimal | None:
    """Parse an observation value.

    FRED writes a missing value as the string '.', and a value that has
    not been published yet as an empty string. Both mean "no
    observation", not "zero". Returning zero for a missing observation
    would put a flat zero into every macro chart.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    text = str(raw).strip()
    if not text or text == '.':
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
