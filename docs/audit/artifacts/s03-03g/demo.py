"""Clean installed wheel demonstration; synthetic callback only."""
import asyncio
from datetime import datetime, timezone
from importlib.util import find_spec
import json
from uuid import UUID

from gabfin.market.stream import QuoteStream
from gabfin.contracts.events import QuoteMarketEvent


async def run():
    identifier = UUID('11111111-1111-4111-8111-111111111111')
    stream = QuoteStream(identifier)
    for price in range(1, 1001):
        event = QuoteMarketEvent.model_validate(dict(
            schema_version='1.0', event_id=UUID(int=price), instrument_id=identifier, kind='quote',
            source='synthetic', source_seq=None, dedup_key=f'synthetic:{price}',
            event_at='2026-11-25T14:59:58Z', received_at='2026-11-25T15:00:00Z',
            available_at='2026-11-25T15:00:00Z',
            payload=dict(schema_version='1.0', instrument_id=identifier, feed='synthetic',
                         as_of='2026-11-25T15:00:00Z', session='unknown', bid=None, ask=None,
                         last=dict(price=str(price), event_at='2026-11-25T14:59:58Z',
                                   received_at='2026-11-25T15:00:00Z', available_at='2026-11-25T15:00:00Z', age_ms=2000),
                         quality=['unknown'], entitlements=dict(status='unknown', checked_at=None))))
        assert stream.apply(event)
    assert stream.pending_count == 1
    iterator = stream.events()
    event = await anext(iterator)
    stream.close()
    await iterator.aclose()
    assert event.payload.last.price == 1000
    assert event.payload.last.age_ms == 2000
    assert find_spec('futu') is None and find_spec('pandas') is None
    return dict(accepted=stream.accepted, coalesced=stream.coalesced,
                last=str(event.payload.last.price), age_ms=event.payload.last.age_ms,
                entitlement=event.payload.entitlements.status, no_sdk_in_host=True)


print(json.dumps(asyncio.run(run())))
