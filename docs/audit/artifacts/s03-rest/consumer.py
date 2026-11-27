"""Separate-process read-only consumer; token is private stdin, never output."""
import asyncio
from datetime import datetime, timezone
import json
import sys
from uuid import UUID

from gabfin.market.internal_stream import InternalMarketClient


async def run(config):
    client = await InternalMarketClient.connect(config['host'], config['port'],
        token=config['token'], instrument_ids=[UUID(config['instrument_id'])])
    result = dict(quote_observations=0, updates=0, connected_seen=False, resynced_seen=False,
                  traces=[], errors=[], latest=None)
    try:
        async with asyncio.timeout(config['seconds']):
            while True:
                frame = await client.receive(timeout=config['seconds'])
                received = datetime.now(timezone.utc).isoformat()
                if frame.kind == 'error':
                    result['errors'].append(frame.code)
                    break
                if frame.kind == 'snapshot':
                    health = frame.payload.health
                    events = frame.payload.quotes
                    processed_at = None
                elif frame.kind == 'update':
                    result['updates'] += 1
                    health = frame.payload.health
                    event = frame.payload.event
                    events = [event] if event is not None and event.kind == 'quote' else []
                    processed_at = frame.payload.processed_at.isoformat()
                else:
                    continue
                result['connected_seen'] |= health.connected
                result['resynced_seen'] |= health.connected and not health.gap_pending
                for event in events:
                    result['quote_observations'] += 1
                    result['latest'] = event.model_dump(mode='json')
                    if len(result['traces']) < 3:
                        result['traces'].append(dict(event_at=event.event_at.isoformat(),
                            source_received_at=event.received_at.isoformat(),
                            available_at=event.available_at.isoformat(), processed_at=processed_at,
                            consumer_received_at=received))
    except TimeoutError:
        pass
    finally:
        await client.close()
    return result


if __name__ == '__main__':
    try:
        config = json.loads(sys.stdin.buffer.read(4096))
        result = asyncio.run(run(config))
    except Exception:
        result = dict(errors=['consumer_failed'], quote_observations=0)
    print(json.dumps(result))
