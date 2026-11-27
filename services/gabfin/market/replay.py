"""Constant-memory replay of an available-time-ordered event journal."""
from pydantic import TypeAdapter
from gabfin.contracts.common import UtcTimestamp
from gabfin.contracts.events import MarketEvent


def replay_events(events, consumer, *, as_of):
    as_of = TypeAdapter(UtcTimestamp).validate_python(as_of)
    previous = None
    for value in events:
        event = TypeAdapter(MarketEvent).validate_python(value.model_dump(mode='python'))
        if previous is not None and event.available_at < previous:
            raise ValueError('Replay input must be available-time ordered')
        previous = event.available_at
        if event.available_at <= as_of:
            yield from consumer.apply(event)
