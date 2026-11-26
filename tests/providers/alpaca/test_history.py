"""Alpaca history: cross-symbol pagination, throttling, and volume fidelity.

The load-bearing test here is `test_pagination_covers_every_symbol`. Alpaca's
`limit` counts rows across all requested symbols, so a naive reader that
stops at one page silently loses every symbol after the first.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from gabfin.contracts.market import Timeframe
from gabfin.providers.alpaca import history
from gabfin.providers.alpaca.history import (
    AlpacaHistoryClient,
    AlpacaHistoryError,
    Request,
    Response,
)
from gabfin.providers.alpaca.rate_limit import TokenBucket

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
DAY = Timeframe.model_validate({'count': 1, 'unit': 'trading_day'})
MINUTE = Timeframe.model_validate({'count': 1, 'unit': 'minute'})


def bar(stamp: str, close: str = '100.00', volume: str = '12345') -> dict:
    return {
        't': stamp,
        'o': close,
        'h': close,
        'l': close,
        'c': close,
        'v': volume,
        'n': 42,
        'vw': close,
    }


def transport_for(pages: list):
    """A transport that replays a fixed list of pages.

    A page may be a raw payload dict or a whole `Response`, so a test can
    describe an error status as easily as a successful page.
    """
    seen: list[Request] = []

    def transport(request: Request) -> Response:
        seen.append(request)
        index = len(seen) - 1
        if index >= len(pages):
            return Response(200, {})
        page = pages[index]
        if isinstance(page, Response):
            return page
        return Response(200, page)

    transport.requests = seen
    return transport


def client_for(pages: list, **kwargs):
    transport = transport_for(pages)
    kwargs.setdefault('clock', lambda: NOW)
    client = AlpacaHistoryClient(transport, **kwargs)
    return client, transport


def test_pagination_covers_every_symbol():
    """Three symbols, a limit smaller than the total, and every one is seen."""
    pages = [
        {
            'bars': {
                'AAPL': [bar('2026-11-02T05:00:00Z'), bar('2026-11-03T05:00:00Z')],
            },
            'next_page_token': 'page-2',
        },
        {
            'bars': {
                'AAPL': [bar('2026-11-04T05:00:00Z')],
                'MSFT': [bar('2026-11-04T05:00:00Z')],
            },
            'next_page_token': 'page-3',
        },
        {
            'bars': {
                'MSFT': [bar('2026-11-05T05:00:00Z')],
                'NVDA': [bar('2026-11-05T05:00:00Z')],
            },
            'next_page_token': None,
        },
    ]
    client, transport = client_for(pages)
    bars, report = client.fetch_bars(
        ['AAPL', 'MSFT', 'NVDA'], DAY, NOW - timedelta(days=30), NOW
    )
    assert report.pages == 3
    assert report.missing_symbols == ()
    assert report.fetched_symbols == ('AAPL', 'MSFT', 'NVDA')
    assert len(bars) == 6
    assert len(transport.requests) == 3


def test_a_symbol_missing_from_every_page_is_reported():
    pages = [
        {'bars': {'AAPL': [bar('2026-11-02T05:00:00Z')]}, 'next_page_token': None}
    ]
    client, _ = client_for(pages)
    bars, report = client.fetch_bars(
        ['AAPL', 'NVDA'], DAY, NOW - timedelta(days=30), NOW
    )
    assert report.missing_symbols == ('NVDA',)
    assert report.fetched_symbols == ('AAPL',)
    assert len(bars) == 1


def test_the_next_page_token_is_sent_on_later_pages():
    pages = [
        {'bars': {'AAPL': [bar('2026-11-02T05:00:00Z')]}, 'next_page_token': 'tok'},
        {'bars': {'AAPL': [bar('2026-11-03T05:00:00Z')]}, 'next_page_token': None},
    ]
    client, transport = client_for(pages)
    client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)
    assert 'page_token' not in transport.requests[0].params
    assert transport.requests[1].params['page_token'] == 'tok'


def test_an_empty_token_ends_the_pagination():
    pages = [{'bars': {'AAPL': []}, 'next_page_token': ''}]
    client, transport = client_for(pages)
    _, report = client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)
    assert report.pages == 1
    assert len(transport.requests) == 1


def test_volume_is_preserved_exactly():
    pages = [
        {
            'bars': {'AAPL': [bar('2026-11-02T05:00:00Z', volume='98765.25')]},
            'next_page_token': None,
        }
    ]
    client, _ = client_for(pages)
    bars, _ = client.fetch_bars(
        ['AAPL'], DAY, NOW - timedelta(days=30), NOW
    )
    assert bars[0]['volume'] == Decimal('98765.25')


def test_a_bar_without_volume_keeps_it_absent_rather_than_zero():
    raw = bar('2026-11-02T05:00:00Z')
    del raw['v']
    pages = [{'bars': {'AAPL': [raw]}, 'next_page_token': None}]
    client, _ = client_for(pages)
    bars, _ = client.fetch_bars(
        ['AAPL'], DAY, NOW - timedelta(days=30), NOW
    )
    assert bars[0]['volume'] is None


def test_a_malformed_bar_is_refused():
    pages = [{'bars': {'AAPL': [{'t': '2026-11-02T05:00:00Z'}]}, 'next_page_token': None}]
    client, _ = client_for(pages)
    with pytest.raises(ValueError):
        client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)


def test_the_feed_is_degraded_when_the_end_is_inside_the_sip_window():
    pages = [{'bars': {'AAPL': []}, 'next_page_token': None}]
    client, transport = client_for(pages)
    _, report = client.fetch_bars(
        ['AAPL'], DAY, NOW - timedelta(days=30), NOW - timedelta(minutes=5)
    )
    assert report.feed == 'iex'
    assert report.degraded is True
    assert transport.requests[0].params['feed'] == 'iex'


def test_the_feed_is_sip_when_the_end_is_outside_the_window():
    pages = [{'bars': {'AAPL': []}, 'next_page_token': None}]
    client, transport = client_for(pages)
    _, report = client.fetch_bars(
        ['AAPL'], DAY, NOW - timedelta(days=30), NOW - timedelta(minutes=20)
    )
    assert report.feed == 'sip'
    assert report.degraded is False
    assert transport.requests[0].params['feed'] == 'sip'


def test_an_entitlement_failure_is_distinguished_from_no_data():
    pages = [
        Response(
            403,
            {},
            message='subscription does not permit querying recent SIP data',
        )
    ]
    client, _ = client_for(pages)
    with pytest.raises(AlpacaHistoryError) as error:
        client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)
    assert error.value.reason == 'entitlement'


def test_a_rate_limit_is_reported_as_such():
    pages = [Response(429, {}, message='too many requests')]
    client, _ = client_for(pages)
    with pytest.raises(AlpacaHistoryError) as error:
        client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)
    assert error.value.reason == 'rate_limited'


def test_a_malformed_payload_is_refused():
    pages = [{'bars': 'not-an-object', 'next_page_token': None}]
    client, _ = client_for(pages)
    with pytest.raises(AlpacaHistoryError) as error:
        client.fetch_bars(['AAPL'], DAY, NOW - timedelta(days=30), NOW)
    assert error.value.reason == 'malformed_payload'


def test_no_symbols_is_refused():
    client, _ = client_for([{}])
    with pytest.raises(ValueError):
        client.fetch_bars([], DAY, NOW - timedelta(days=30), NOW)


def test_the_timeframe_is_sent_in_alpaca_shape():
    pages = [{'bars': {}, 'next_page_token': None}]
    client, transport = client_for(pages)
    client.fetch_bars(['AAPL'], MINUTE, NOW - timedelta(days=1), NOW)
    assert transport.requests[0].params['timeframe'] == '1Min'


def test_option_contracts_are_structure_only():
    pages = [
        {
            'option_contracts': [
                {
                    'symbol': 'AAPL261218C00100000',
                    'underlying_symbol': 'AAPL',
                    'expiration_date': '2026-12-18',
                    'strike_price': '100',
                    'type': 'call',
                    'multiplier': '100',
                    'status': 'active',
                }
            ]
        }
    ]
    client, transport = client_for(pages)
    contracts = client.fetch_option_contracts('AAPL')
    assert len(contracts) == 1
    assert contracts[0]['expiry'] == '2026-12-18'
    assert contracts[0]['right'] == 'call'
    assert 'price' not in contracts[0]
    assert 'ask_price' not in contracts[0]
    assert transport.requests[0].params['underlying_symbols'] == 'AAPL'


def test_the_screener_top_count_is_bounded():
    client, _ = client_for([{}])
    with pytest.raises(ValueError):
        client.fetch_screener('most-actives', top=51)
    with pytest.raises(ValueError):
        client.fetch_screener('unknown-kind', top=10)


def test_the_screener_returns_symbols():
    pages = [{'most_actives': [{'symbol': 'AAPL'}, {'symbol': 'NVDA'}]}]
    client, _ = client_for(pages)
    assert client.fetch_screener('most-actives', top=2) == ['AAPL', 'NVDA']
