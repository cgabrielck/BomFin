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
    chart_files=sorted(root.with_name('bars').glob('*.json'))
    if len(chart_files)!=3: raise ValueError('Expected three explicit chart snapshots')
    count=0
    for file in chart_files:
        snapshot=MarketSnapshot.model_validate_json(file.read_bytes())
        quote=MarketSnapshot.model_validate_json((root/file.name).read_bytes()).quotes[0]
        if snapshot.health.source!='demo' or snapshot.quotes: raise ValueError('Synthetic chart scope mismatch')
        expected=0 if file.stem=='NVDA' else 30
        if len(snapshot.bars)!=expected: raise ValueError('Unexpected synthetic bar count')
        for event in snapshot.bars:
            if (event.instrument_id!=quote.instrument_id or event.source!='demo'
                or event.payload.corporate_action_policy!='synthetic-unadjusted'
                or event.payload.timeframe.count!=1 or event.payload.timeframe.unit!='minute'):
                raise ValueError('Synthetic chart provenance mismatch')
        count+=len(snapshot.bars)
    print(f'3 quote / 3 synthetic bar snapshots passed canonical checks ({count} bars; NVDA empty)')


if __name__ == '__main__':
    main()
