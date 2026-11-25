"""Clean installed wheel demonstration; synthetic callback only."""
import asyncio
from datetime import datetime, timezone
from importlib.util import find_spec
import json
from uuid import UUID

from gabfin.market.stream import QuoteStream


async def run():
    stream = QuoteStream(UUID('11111111-1111-4111-8111-111111111111'), 'US.AAPL')
    for price in range(1, 1001):
        assert stream.accept(dict(version=1, kind='quote', code='US.AAPL', price=str(price),
                                  event_at='2026-11-25T14:59:58Z', received_at='2026-11-25T15:00:00Z'),
                             available_at=datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
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
