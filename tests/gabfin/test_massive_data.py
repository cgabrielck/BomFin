"""Historical bars and options retain vendor values and expose missing fields."""
import importlib
from datetime import date
from decimal import Decimal

import pytest

from gabfin.providers.massive.config import MassiveConfig
from gabfin.providers.massive.rest import MassiveRestClient, Response


def client(payloads, requests):
    def transport(request):
        requests.append(request)
        return Response(200, payloads.pop(0))
    return MassiveRestClient(MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'),
                             transport=transport)


def test_recorded_quote_parses_prices_time_and_keeps_entitlement_unknown():
    import json
    from datetime import datetime
    from pathlib import Path
    from uuid import uuid4
    from gabfin.providers.massive.adapter import parse_quote_message

    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/massive/recorded_quote_2026_11_27.json').read_text())
    received = datetime.fromisoformat(fixture['recorded_at'].replace('Z', '+00:00'))
    event = parse_quote_message(json.dumps(fixture['events'][0]), symbol='MSFT',
                                instrument_id=uuid4(), received_at=received)
    assert event.payload.bid.price == Decimal('500.91')
    assert event.payload.ask.price == Decimal('501.55')
    assert event.event_at.isoformat() == '2026-11-27T09:01:33.151000+00:00'
    assert event.payload.bid.age_ms == 2479
    assert event.payload.entitlements.status == 'unknown'


def test_recorded_provider_bars_and_option_snapshot_parse_without_fabrication():
    import json
    from pathlib import Path
    from gabfin.providers.massive.history import MassiveHistory
    from gabfin.providers.massive.options import MassiveOptions

    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/massive/recorded_rest_2026_11_27.json').read_text())
    rest = client([fixture['history'], fixture['options']], [])
    bars = MassiveHistory(rest).bars('AAPL', multiplier=1, timespan='day',
                                    start=date(2026, 11, 23), end=date(2026, 11, 25))
    assert len(bars) == 3
    assert bars[0]['volume'] == Decimal('58588703.300041')
    assert bars[2]['close'] == Decimal('355.58')
    options = MassiveOptions(rest).chain('AAPL')
    assert options[0]['coverage'] == 'available'
    assert options[0]['greeks_source'] == 'massive'
    assert options[0]['implied_volatility'] == 13.486260664462186


def test_history_preserves_volume_decimal_and_follows_pages():
    history = importlib.import_module('gabfin.providers.massive.history')
    requests = []
    rest = client([{'results': [{'t': 1795789800000, 'o': '100.1', 'h': '102',
        'l': '99', 'c': '101', 'v': '123.5'}], 'next_url': '/v2/aggs/ticker/AAPL/range/1/minute/2026-11-27/2026-11-27?cursor=two'},
        {'results': []}], requests)
    rows = history.MassiveHistory(rest).bars('AAPL', multiplier=1, timespan='minute',
                                            start=date(2026, 11, 27), end=date(2026, 11, 27))
    assert len(rows) == 1
    assert rows[0]['volume'] == Decimal('123.5')
    assert rows[0]['open'] == Decimal('100.1')
    assert rows[0]['source'] == 'massive'
    assert rows[0]['event_at'].utcoffset().total_seconds() == 0
    assert len(requests) == 2
    assert 'adjusted=true' in requests[0].url


@pytest.mark.parametrize('bad', [
    {'t': 1795789800000, 'o': 1, 'h': 2, 'l': 0, 'c': 1},
    {'t': 1795789800000, 'o': 1, 'h': 0, 'l': 2, 'c': 1, 'v': 1},
    {'t': 1795789800000, 'o': 1, 'h': 2, 'l': 0, 'c': 'NaN', 'v': 1},
])
def test_malformed_bars_fail_instead_of_becoming_zero_volume(bad):
    history = importlib.import_module('gabfin.providers.massive.history')
    with pytest.raises(ValueError):
        history.extract_bar(bad)


def test_options_all_pages_preserve_missing_greeks_without_invention():
    options = importlib.import_module('gabfin.providers.massive.options')
    requests = []
    rest = client([{'results': [{'details': {'ticker': 'O:SPY261218C00650000'},
                                'greeks': {'delta': 0.5}, 'implied_volatility': 0.2}],
                    'next_url': 'https://upstream.example.test/v3/snapshot/options/SPY?cursor=two&apiKey=vendor'},
                   {'results': [{'details': {'ticker': 'O:SPY261218P00650000'}}]}], requests)
    rows = options.MassiveOptions(rest).chain('SPY')
    assert len(rows) == 2
    assert rows[0]['greeks'] == {'delta': 0.5}
    assert rows[0]['coverage'] == 'partial_greeks'
    assert rows[0]['greeks_source'] == 'massive'
    assert rows[1]['greeks'] is None
    assert rows[1]['implied_volatility'] is None
    assert rows[1]['coverage'] == 'missing_greeks_iv'
    assert requests[1].url.startswith('https://proxy.example.test/')
