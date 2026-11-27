"""Unit tests for Massive adapter message parsing."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from gabfin.contracts.market import QuoteQuality, EntitlementStatus
from gabfin.providers.massive.adapter import parse_quote_message


@pytest.fixture
def _now():
    return datetime(2026, 11, 27, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def _inst_id():
    return uuid4()


@pytest.fixture
def _symbol():
    return 'AAPL'


def test_parse_quote_basic(_inst_id, _now, _symbol):
    """Single quote with bid and ask."""
    msg = json.dumps({'ev': 'Q', 'sym': 'AAPL', 'bp': '150.50', 'ap': '150.51', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is not None
    assert evt.kind == 'quote'
    assert evt.payload.bid.price == Decimal('150.50')
    assert evt.payload.ask.price == Decimal('150.51')
    assert evt.payload.session.__class__.__name__ == 'MarketSession'


def test_parse_quote_missing_symbol(_inst_id, _now, _symbol):
    """Quote for different symbol is ignored."""
    msg = json.dumps({'ev': 'Q', 'sym': 'MSFT', 'bp': '150.50', 'ap': '150.51', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is None


def test_parse_non_quote(_inst_id, _now, _symbol):
    """Non-quote events (trades, etc.) are ignored."""
    msg = json.dumps({'ev': 'T', 'sym': 'AAPL', 'p': '150.50', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is None


def test_parse_malformed_json(_inst_id, _now, _symbol):
    """Malformed JSON returns None (graceful skip)."""
    msg = 'not json'
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is None


def test_parse_quote_bid_only(_inst_id, _now, _symbol):
    """Quote with only bid (ask is None)."""
    msg = json.dumps({'ev': 'Q', 'sym': 'AAPL', 'bp': '150.50', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is not None
    assert evt.payload.bid.price == Decimal('150.50')
    assert evt.payload.ask is None


def test_parse_quote_crossed_bid_ask(_inst_id, _now, _symbol):
    """Crossed bid-ask is marked with QuoteQuality.CROSSED."""
    msg = json.dumps({'ev': 'Q', 'sym': 'AAPL', 'bp': '150.51', 'ap': '150.50', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is not None
    assert QuoteQuality.CROSSED in evt.payload.quality


def test_parse_quote_future_event_time(_inst_id, _now, _symbol):
    """Event time in future adds clock_skew quality."""
    future_t = int((_now + timedelta(seconds=1)).timestamp() * 1000)
    msg = json.dumps({'ev': 'Q', 'sym': 'AAPL', 'bp': '150.50', 'ap': '150.51', 't': future_t})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is not None
    assert QuoteQuality.CLOCK_SKEW in evt.payload.quality


def test_parse_quote_missing_both_prices(_inst_id, _now, _symbol):
    """Quote without any prices fails gracefully."""
    msg = json.dumps({'ev': 'Q', 'sym': 'AAPL', 't': int(_now.timestamp() * 1000)})
    evt = parse_quote_message(msg, symbol=_symbol, instrument_id=_inst_id, received_at=_now)
    
    assert evt is None


def test_adapter_accepts_massive_config_and_uses_plan_capacity():
    import asyncio
    from gabfin.providers.massive.adapter import MassiveQuoteAdapter
    from gabfin.providers.massive.config import MassiveConfig

    cfg = MassiveConfig(base_url='https://proxy.example.test', api_key='fixture', max_subscriptions=100)
    adapter = MassiveQuoteAdapter(instrument_id=uuid4(), symbol='AAPL', config=cfg)
    assert asyncio.run(adapter.capabilities()).max_subscriptions == 100


def test_managed_adapter_streams_all_quotes_in_batch_and_confirms_cleanup():
    import asyncio
    from gabfin.providers.massive.adapter import MassiveQuoteAdapter
    from gabfin.providers.massive.config import MassiveConfig
    from gabfin.protocols import ManagedFeedAdapter

    async def scenario():
        frames = asyncio.Queue()
        class Wire:
            async def send(self, message):
                await frames.put('{"status":"ok","message":"subscribed"}')
            async def recv(self):
                return await frames.get()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
        adapter = MassiveQuoteAdapter(instrument_id=uuid4(), symbol='AAPL',
            config=MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'),
            _connect=lambda url, key: Wire())
        assert isinstance(adapter, ManagedFeedAdapter)
        await adapter.subscribe([adapter.key])
        await frames.put(json.dumps([{'ev': 'Q', 'sym': 'AAPL', 'bp': 100, 't': 1000},
                                     {'ev': 'Q', 'sym': 'AAPL', 'bp': 101, 't': 2000}]))
        events = adapter.events()
        event = await asyncio.wait_for(anext(events), .5)
        assert event.payload.bid.price == Decimal('101')
        assert adapter.stats['accepted'] == 2
        assert adapter.health.connection_started_at is not None
        await adapter.close()
        await events.aclose()
        assert adapter.cleanup.context_closed
        assert adapter.cleanup.release_confirmed
        assert adapter.cleanup.requested_keys == (adapter.key,)
    asyncio.run(scenario())


def test_failed_close_never_claims_release_confirmed():
    import asyncio
    from gabfin.providers.massive.adapter import MassiveQuoteAdapter
    from gabfin.providers.massive.config import MassiveConfig

    async def scenario():
        frames = asyncio.Queue()
        class Wire:
            async def send(self, message):
                await frames.put('{"status":"ok","message":"subscribed"}')
            async def recv(self):
                return await frames.get()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                raise RuntimeError('fixture-secret')
        adapter = MassiveQuoteAdapter(instrument_id=uuid4(), symbol='AAPL',
            config=MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'),
            _connect=lambda url, key: Wire())
        await adapter.subscribe([adapter.key])
        await adapter.close()
        assert adapter.cleanup.release_confirmed is False
        assert adapter.cleanup.context_closed is False
    asyncio.run(scenario())


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
