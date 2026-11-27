"""Import an explicitly sourced local bundle, without fetching external URLs."""
import argparse
import json
from pathlib import Path

from gabfin.contracts.research import EvidenceItem
from gabfin.contracts.support import CandidateObservation
from gabfin.universe.store import CandidateStore


def import_bundle(path: Path, store: CandidateStore) -> dict:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Source bundle too large')
    body = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(body, dict) or set(body) != {'evidence', 'observations'}:
        raise ValueError('Source bundle requires evidence and observations')
    evidence = [EvidenceItem.model_validate(item) for item in body['evidence']]
    observations = [CandidateObservation.model_validate(item) for item in body['observations']]
    # One transaction prevents partially imported bundles if any row conflicts.
    with store._connect() as db:
        for item in evidence:
            if item.published_at is not None and item.published_at > item.available_at:
                raise ValueError('Evidence published after availability')
            store._insert(db, 'candidate_evidence', item.evidence_id, item.model_dump_json())
        for item in observations:
            for identity in item.evidence:
                row = db.execute('SELECT payload FROM candidate_evidence WHERE id=?', (str(identity),)).fetchone()
                if row is None or EvidenceItem.model_validate_json(row[0]).available_at > item.observed_at:
                    raise ValueError('Evidence unavailable at observation')
            store._insert(db, 'candidate_observations', item.observation_id, item.model_dump_json())
    return {'evidence': len(evidence), 'observations': len(observations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_bundle(args.bundle, CandidateStore(args.database))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, 'Source bundle rejected\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
