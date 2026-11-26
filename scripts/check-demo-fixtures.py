"""Verify the shipped demo snapshots against canonical contracts, offline."""
from pathlib import Path

from gabfin.contracts.feed import MarketSnapshot


def main():
    root = Path(__file__).resolve().parents[1] / 'apps/desk-web/public/demo/markets'
    files = sorted(root.glob('*.json'))
    if len(files) != 3:
        raise ValueError('Expected three explicit sample snapshots')
    ids = set()
    for file in files:
        snapshot = MarketSnapshot.model_validate_json(file.read_bytes())
        if (snapshot.health.source != 'demo' or len(snapshot.quotes) != 1 or snapshot.bars
                or snapshot.quotes[0].source != 'demo'
                or snapshot.quotes[0].payload.entitlements.status.value != 'unknown'):
            raise ValueError('Demo fixture must not imply real provider rights or bars')
        ids.add(snapshot.quotes[0].instrument_id)
    if len(ids) != 3:
        raise ValueError('Sample stocks must have distinct canonical identities')
    print('3 demo MarketSnapshot fixtures passed canonical contract checks')


if __name__ == '__main__':
    main()
