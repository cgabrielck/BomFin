import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from gabfin.universe.store import CandidateStore


def test_import_source_bundle(tmp_path):
    from gabfin.universe.__main__ import import_bundle
    now = datetime.now(timezone.utc)
    eid, iid = str(uuid4()), str(uuid4())
    payload = {'evidence': [{'schema_version': '1.0', 'evidence_id': eid,
        'url': 'https://example.org/research', 'artifact_id': None, 'publisher': 'Manual fixture',
        'original_firm': None, 'published_at': now.isoformat(), 'first_seen_at': now.isoformat(),
        'available_at': now.isoformat(), 'content_hash': 'a' * 64, 'license_tag': 'manual-reference'}],
        'observations': [{'schema_version': '1.0', 'observation_id': str(uuid4()), 'instrument': iid,
        'reason': 'Published event', 'evidence': [eid], 'horizon': {'kind': 'unspecified', 'reason': 'Unknown'},
        'observed_at': now.isoformat(), 'expires_at': (now + timedelta(days=1)).isoformat(), 'action': 'include'}]}
    source = tmp_path / 'bundle.json'
    source.write_text(json.dumps(payload), encoding='utf-8')
    store = CandidateStore(tmp_path / 'u.sqlite')
    assert import_bundle(source, store) == {'evidence': 1, 'observations': 1}
    assert len(store.universe_at(now)) == 1
    # A later invalid reference rolls back the evidence written earlier in the bundle.
    import pytest
    new_id = str(uuid4())
    payload['evidence'][0]['evidence_id'] = new_id
    payload['observations'][0]['evidence'] = [str(uuid4())]
    source.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError):
        import_bundle(source, store)
    with pytest.raises(KeyError):
        store.evidence(new_id)
