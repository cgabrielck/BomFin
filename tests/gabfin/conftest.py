"""Hand-written market fixtures; no production model imports during collection."""
from copy import deepcopy

import pytest


@pytest.fixture
def instrument_payload():
    return {
        "schema_version": "1.0",
        "instrument_id": "11111111-1111-4111-8111-111111111111",
        "asset_class": "equity",
        "vendor_symbols": {"feed": "TEST", "other": "US.TEST"},
        "currency": "USD", "tick_size": "0.01", "lot_size": "0.001",
    }


@pytest.fixture
def option_payload(instrument_payload):
    instrument_payload = deepcopy(instrument_payload)
    instrument_payload.update(
        instrument_id="22222222-2222-4222-8222-222222222222",
        asset_class="option", lot_size="1",
        vendor_symbols={"feed": "TEST  261218C00100000"},
        option={
            "underlying_id": "11111111-1111-4111-8111-111111111111",
            "expiry": "2026-12-18", "right": "call", "strike": "100.00", "multiplier": "10",
        },
    )
    return instrument_payload


@pytest.fixture
def quote_payload():
    return {
        "schema_version": "1.0", "instrument_id": "11111111-1111-4111-8111-111111111111",
        "as_of": "2026-11-25T14:30:01Z", "feed": "test-feed", "session": "regular",
        "bid": {"price": "100.10", "event_at": "2026-11-25T14:30:00Z", "received_at": "2026-11-25T14:30:00.100Z", "available_at": "2026-11-25T14:30:00.200Z", "age_ms": 1000},
        "ask": {"price": "100.20", "event_at": "2026-11-25T14:30:00.500Z", "received_at": "2026-11-25T14:30:00.600Z", "available_at": "2026-11-25T14:30:00.700Z", "age_ms": 500},
        "last": None, "quality": [],
        "entitlements": {"status": "realtime", "checked_at": "2026-11-25T14:00:00Z", "capability_snapshot_id": None},
    }


@pytest.fixture
def bar_payload():
    return {
        "schema_version": "1.0", "instrument_id": "11111111-1111-4111-8111-111111111111",
        "source": "test-feed", "timeframe": {"count": 1, "unit": "minute"}, "session": "regular",
        "start": "2026-11-24T14:30:00Z", "end": "2026-11-24T14:31:00Z",
        "open": "100.00", "high": "102.00", "low": "99.00", "close": "101.00", "volume": "12345.5",
        "status": "final", "revision": 0, "corporate_action_policy": "raw-v1",
        "event_at": "2026-11-24T14:31:00Z", "received_at": "2026-11-24T14:31:00.100Z", "available_at": "2026-11-24T14:31:00.200Z",
    }


@pytest.fixture
def trade_payload():
    return {"schema_version": "1.0", "instrument_id": "11111111-1111-4111-8111-111111111111", "price": "100.15", "quantity": "0.1", "trade_id": None}
