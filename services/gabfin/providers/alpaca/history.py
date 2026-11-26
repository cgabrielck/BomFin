"""Alpaca historical bars, read as a tape source.

The hard part of this adapter is not the request. It is that Alpaca's
`limit` counts **rows across all requested symbols**, not rows per symbol.
A request for three symbols with `limit=10000` can be exhausted by the
first symbol's data, leaving the other two silently absent. The only
defence is to follow `next_page_token` until it is empty, and to keep
asking until every requested symbol has been seen.

Every page is accounted for. A symbol that never appears in any page is
reported as missing rather than quietly yielding no bars.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterator

from gabfin.contracts.market import Timeframe, TimeUnit
from gabfin.providers.alpaca.feed_guard import FeedDecision, resolve_feed
from gabfin.providers.alpaca.rate_limit import TokenBucket

DATA_URL = 'https://data.alpaca.markets'
TRADES_URL = 'https://api.alpaca.markets'
OPTION_URL = 'https://api.alpaca.markets'

#: The free tier allows 200 requests per minute.
FREE_TIER_RATE = 200

#: Alpaca's maximum rows per page, counted across all symbols.
MAX_PAGE_ROWS = 10000


@dataclass
class Response:
    """One provider response, reduced to what this adapter reads."""

    status: int
    payload: dict
    message: str = ''


@dataclass
class Request:
    """One provider request."""

    url: str
    params: dict
    method: str = 'GET'


Transport = Callable[[Request], Response]


class AlpacaHistoryError(RuntimeError):
    """A provider call failed in a way the caller must know about."""

    def __init__(self, message: str, *, status: int = 0, reason: str = 'unknown'):
        super().__init__(message)
        self.status = status
        self.reason = reason


@dataclass
class FetchReport:
    """What a fetch actually did, including what it could not do."""

    requested_symbols: tuple[str, ...]
    fetched_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    pages: int = 0
    rows: int = 0
    throttled_waits: int = 0
    degraded: bool = False
    feed: str = ''
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            'requested_symbols': list(self.requested_symbols),
            'fetched_symbols': list(self.fetched_symbols),
            'missing_symbols': list(self.missing_symbols),
            'pages': self.pages,
            'rows': self.rows,
            'throttled_waits': self.throttled_waits,
            'degraded': self.degraded,
            'feed': self.feed,
            'reason': self.reason,
        }


def timeframe_to_alpaca(timeframe: Timeframe) -> tuple[int, str]:
    """The Alpaca (amount, unit) pair for a timeframe."""
    units = {
        TimeUnit.MINUTE: 'Min',
        TimeUnit.HOUR: 'Hour',
        TimeUnit.TRADING_DAY: 'Day',
        TimeUnit.WEEK: 'Week',
        TimeUnit.MONTH: 'Month',
    }
    if timeframe.unit not in units:
        raise ValueError(f'Alpaca does not support the {timeframe.unit} timeframe')
    return timeframe.count, units[timeframe.unit]


def _parse_timestamp(value) -> datetime:
    """Alpaca timestamps are RFC3339 with a Z or an explicit offset."""
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value)
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        raise ValueError('An Alpaca timestamp must carry an offset')
    return stamp.astimezone(timezone.utc)


def extract_bar(raw: dict) -> dict:
    """One Alpaca bar, in the shape the tape writer consumes.

    Volume is kept as a Decimal and is never dropped: a bar without
    volume cannot feed a volume indicator, and a silently absent volume
    looks like zero volume.
    """
    if not isinstance(raw, dict):
        raise ValueError('An Alpaca bar must be an object')
    required = ('t', 'o', 'h', 'l', 'c')
    if any(field not in raw for field in required):
        raise ValueError('An Alpaca bar is missing a required field')
    volume = raw.get('v')
    return {
        'event_at': _parse_timestamp(raw['t']),
        'open': Decimal(str(raw['o'])),
        'high': Decimal(str(raw['h'])),
        'low': Decimal(str(raw['l'])),
        'close': Decimal(str(raw['c'])),
        'volume': None if volume is None else Decimal(str(volume)),
        'trade_count': raw.get('n'),
        'vwap': None if raw.get('vw') is None else Decimal(str(raw['vw'])),
    }


class AlpacaHistoryClient:
    """Reads historical bars from Alpaca for the tape plane.

    The transport is injected, so the adapter's pagination and rate
    limiting can be exercised without a network or an account.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        bucket: TokenBucket | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._transport = transport
        self._api_key = api_key
        self._api_secret = api_secret
        self._bucket = bucket or TokenBucket(FREE_TIER_RATE)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def throttled_waits(self) -> int:
        return self._bucket.waits

    def fetch_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        *,
        feed: str | None = None,
        adjustment: str | None = None,
        limit: int = MAX_PAGE_ROWS,
    ) -> tuple[list[dict], FetchReport]:
        """Read bars for every requested symbol, following every page.

        Returns the bars and a report of what was fetched, what was
        missing and whether the feed was degraded.
        """
        if not symbols:
            raise ValueError('At least one symbol is required')
        unique = tuple(dict.fromkeys(symbols))
        for symbol in unique:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError('A symbol must be a nonempty string')

        now = self._clock()
        decision = self._decide_feed(feed, end, now)
        amount, unit = timeframe_to_alpaca(timeframe)

        params = {
            'symbols': ','.join(unique),
            'timeframe': f'{amount}{unit}',
            'start': _format_timestamp(start),
            'feed': decision.feed,
            'limit': limit,
            'sort': 'asc',
        }
        if end is not None:
            params['end'] = _format_timestamp(end)
        if adjustment is not None:
            params['adjustment'] = adjustment

        collected: dict[str, list[dict]] = {symbol: [] for symbol in unique}
        seen: set[str] = set()
        token = None
        pages = 0
        rows = 0
        while True:
            page_params = dict(params)
            if token:
                page_params['page_token'] = token
            response = self._request(
                Request(f'{DATA_URL}/v2/stocks/bars', page_params)
            )
            pages += 1
            payload = response.payload or {}
            bars = payload.get('bars') or {}
            if not isinstance(bars, dict):
                raise AlpacaHistoryError(
                    'The Alpaca bars payload is not an object',
                    status=response.status,
                    reason='malformed_payload',
                )
            for symbol, series in bars.items():
                if symbol not in collected:
                    # A symbol we did not ask for is not an error, but it is
                    # not ours either; it is dropped rather than mixed in.
                    continue
                for raw in series or []:
                    collected[symbol].append(extract_bar(raw))
                    rows += 1
                seen.add(symbol)
            token = payload.get('next_page_token')
            if not token:
                break

        missing = tuple(symbol for symbol in unique if symbol not in seen)
        results = []
        for symbol in unique:
            results.extend(collected[symbol])
        report = FetchReport(
            requested_symbols=unique,
            fetched_symbols=tuple(symbol for symbol in unique if symbol in seen),
            missing_symbols=missing,
            pages=pages,
            rows=rows,
            throttled_waits=self._bucket.waits,
            degraded=decision.degraded,
            feed=decision.feed,
            reason=decision.reason,
        )
        return results, report

    def _decide_feed(
        self, feed: str | None, end: datetime | None, now: datetime
    ) -> FeedDecision:
        if feed is None:
            feed = 'sip'
        return resolve_feed(feed, now, end=end)

    def _request(self, request: Request) -> Response:
        self._bucket.acquire()
        response = self._transport(request)
        if response.status == 200:
            return response
        from gabfin.providers.alpaca.feed_guard import classify_status

        reason = classify_status(response.status, response.message)
        if reason == 'entitlement':
            raise AlpacaHistoryError(
                response.message or 'The account plan does not cover this feed',
                status=response.status,
                reason='entitlement',
            )
        if reason == 'rate_limited':
            raise AlpacaHistoryError(
                response.message or 'Alpaca rate limit reached',
                status=response.status,
                reason='rate_limited',
            )
        raise AlpacaHistoryError(
            response.message or f'Alpaca returned HTTP {response.status}',
            status=response.status,
            reason=reason,
        )

    def fetch_option_contracts(self, underlying: str) -> list[dict]:
        """Read option contract structure only; no prices are requested.

        Structure is expiry, strike, right and multiplier. A price would
        imply an entitlement the free tier does not have, and would make
        an unavailable market look available.
        """
        if not underlying or not str(underlying).strip():
            raise ValueError('An underlying symbol is required')
        request = Request(
            f'{OPTION_URL}/v1beta1/options/contracts',
            {'underlying_symbols': underlying, 'limit': 1000},
        )
        response = self._request(request)
        payload = response.payload or {}
        contracts = payload.get('option_contracts') or payload.get('contracts') or []
        results = []
        for raw in contracts:
            if not isinstance(raw, dict):
                raise AlpacaHistoryError(
                    'An option contract is not an object',
                    status=response.status,
                    reason='malformed_payload',
                )
            results.append(
                {
                    'symbol': raw.get('symbol'),
                    'underlying_symbol': raw.get('underlying_symbol'),
                    'expiry': raw.get('expiration_date'),
                    'strike': raw.get('strike_price'),
                    'right': raw.get('type'),
                    'multiplier': raw.get('multiplier'),
                    'status': raw.get('status'),
                }
            )
        return results

    def fetch_screener(self, kind: str, top: int = 50) -> list[str]:
        """Build a candidate pool from Alpaca's screener endpoints."""
        if top <= 0 or top > 50:
            raise ValueError('The screener top count must be between 1 and 50')
        if kind == 'most-actives':
            url = f'{TRADES_URL}/v1beta1/screener/stocks/most-actives'
            params = {'top': top}
        elif kind in ('gainers', 'losers'):
            url = f'{TRADES_URL}/v1beta1/screener/stocks/{kind}'
            params = {'top': top}
        else:
            raise ValueError(f'Unknown screener kind: {kind}')
        response = self._request(Request(url, params))
        payload = response.payload or {}
        candidates = payload.get('most_actives') or payload.get('gainers') or payload.get('losers') or []
        symbols = []
        for item in candidates:
            if isinstance(item, dict) and item.get('symbol'):
                symbols.append(item['symbol'])
        return symbols


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('An aware timestamp is required')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
