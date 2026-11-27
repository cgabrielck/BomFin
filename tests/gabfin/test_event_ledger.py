"""Canonical events persist idempotently without silently replacing evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from gabfin.providers.massive.adapter import parse_quote_message


def event():
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/massive/recorded_quote_2026_11_27.json').read_text())
    return parse_quote_message(json.dumps(fixture['events'][0]), symbol='MSFT',
        instrument_id=uuid4(), received_at=datetime.fromisoformat(fixture['recorded_at'].replace('Z', '+00:00')))


def test_event_ledger_roundtrip_and_duplicate_after_reopen(tmp_path):
    from gabfin.storage.events import EventLedger
    path = tmp_path / 'events.sqlite'
    original = event()
    assert EventLedger(path).append(original) is True
    assert EventLedger(path).append(original) is False
    assert EventLedger(path).read(original.event_id) == original
    assert EventLedger(path).read(uuid4()) is None


def test_event_ledger_recapture_keeps_first_observation(tmp_path):
    from datetime import timedelta
    from gabfin.storage.events import EventLedger
    ledger = EventLedger(tmp_path / 'events.sqlite')
    original = event()
    later = original.model_copy(deep=True, update={'event_id': uuid4(),
        'received_at': original.received_at + timedelta(seconds=1),
        'available_at': original.available_at + timedelta(seconds=1)})
    snapshot = later.payload
    points = {name: getattr(snapshot, name).model_copy(update={
        'received_at': later.received_at, 'available_at': later.available_at,
        'age_ms': getattr(snapshot, name).age_ms + 1000})
        for name in ('bid', 'ask')}
    later = later.model_copy(update={'payload': snapshot.model_copy(
        update={'as_of': later.received_at, **points})})
    assert ledger.append(original)
    assert ledger.append(later) is False
    assert ledger.read(original.event_id) == original
    assert ledger.read(later.event_id) is None


def test_event_ledger_rejects_conflicting_dedup_key(tmp_path):
    from gabfin.storage.events import EventLedger
    ledger = EventLedger(tmp_path / 'events.sqlite')
    original = event()
    ledger.append(original)
    changed = original.model_copy(update={'source_seq': 'different'})
    with pytest.raises(ValueError, match='conflict'):
        ledger.append(changed)
    assert ledger.read(original.event_id) == original


def test_event_ledger_rejects_invalid_model_copy_before_write(tmp_path):
    from gabfin.storage.events import EventLedger
    ledger = EventLedger(tmp_path / 'events.sqlite')
    original = event()
    with pytest.raises(ValueError):
        ledger.append(original.model_copy(update={'source': 'foreign'}))
    assert ledger.read(original.event_id) is None
