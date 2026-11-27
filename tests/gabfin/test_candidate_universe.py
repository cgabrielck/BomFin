from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from gabfin.contracts.research import EvidenceItem
from gabfin.contracts.support import CandidateObservation

NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)


def evidence(**changes):
    return EvidenceItem(schema_version='1.0', **{
        'evidence_id': uuid4(), 'url': 'https://example.org/research',
        'artifact_id': None, 'publisher': 'Manual source', 'original_firm': None,
        'published_at': NOW, 'first_seen_at': NOW, 'available_at': NOW,
        'content_hash': 'a' * 64, 'license_tag': 'manual-reference', **changes})


def observation(item, **changes):
    return CandidateObservation(schema_version='1.0', **{
        'observation_id': uuid4(), 'instrument': uuid4(), 'reason': 'Published catalyst',
        'evidence': (item.evidence_id,), 'horizon': {'kind': 'unspecified', 'reason': 'Not supplied'},
        'observed_at': NOW, 'expires_at': NOW + timedelta(days=1), 'action': 'include', **changes})


def test_persistence_expiry_and_exclusion(tmp_path):
    from gabfin.universe.store import CandidateStore
    path = tmp_path / 'universe.sqlite'
    store = CandidateStore(path)
    item = evidence()
    store.ingest(item)
    row = observation(item)
    store.observe(row)
    assert CandidateStore(path).universe_at(NOW) == (row,)
    assert store.universe_at(NOW - timedelta(seconds=1)) == ()
    assert store.universe_at(row.expires_at) == ()
    store.observe(observation(item, instrument=row.instrument, action='exclude', observed_at=NOW + timedelta(hours=1)))
    assert store.universe_at(NOW + timedelta(hours=2)) == ()
    assert store.universe_at(NOW) == (row,)


def test_evidence_cannot_travel_backwards_or_be_missing(tmp_path):
    from gabfin.universe.store import CandidateStore
    store = CandidateStore(tmp_path / 'u.sqlite')
    item = evidence(first_seen_at=NOW + timedelta(hours=1), available_at=NOW + timedelta(hours=1))
    store.ingest(item)
    with pytest.raises(ValueError):
        store.observe(observation(item))
    with pytest.raises(ValueError):
        store.observe(observation(evidence()))


def test_identity_conflicts_and_reimports(tmp_path):
    from gabfin.universe.store import CandidateStore
    store = CandidateStore(tmp_path / 'u.sqlite')
    item = evidence()
    assert store.ingest(item) == item.evidence_id
    assert store.ingest(item) == item.evidence_id
    with pytest.raises(ValueError):
        store.ingest(item.model_copy(update={'publisher': 'Changed'}))
    row = observation(item)
    store.observe(row)
    store.observe(row)
    assert store.universe_at(NOW) == (row,)
    with pytest.raises(ValueError):
        store.observe(row.model_copy(update={'reason': 'Changed'}))


def test_future_publication_and_naive_cutoff_are_rejected(tmp_path):
    from gabfin.universe.store import CandidateStore
    store = CandidateStore(tmp_path / 'u.sqlite')
    with pytest.raises(ValueError):
        store.ingest(evidence(published_at=NOW + timedelta(days=1)))
    with pytest.raises(ValueError):
        store.universe_at(NOW.replace(tzinfo=None))


def test_batch_parser_preserves_each_outcome_and_normalizes():
    from gabfin.universe.resolve import resolve_batch
    calls = []
    def lookup(symbol):
        calls.append(symbol)
        return {'symbol': symbol, 'instrument_id': str(uuid4())} if symbol == 'AAPL' else None
    rows = resolve_batch('aapl, MSFT\nAAPL $bad !bad', lookup)
    assert [row['symbol'] for row in rows] == ['AAPL', 'MSFT', '$BAD', '!BAD']
    assert [row['status'] for row in rows] == ['resolved', 'unknown', 'invalid', 'invalid']
    assert calls == ['AAPL', 'MSFT']
    with pytest.raises(ValueError):
        resolve_batch(' '.join(f'A{i}' for i in range(51)), lookup)
