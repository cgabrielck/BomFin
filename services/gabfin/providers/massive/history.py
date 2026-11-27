"""Massive historical OHLCV with explicit vendor provenance."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import quote

from gabfin.providers.massive.rest import MassiveRestClient

#: The venues the indicator contract accepts. Massive history is
#: consolidated vendor data with no venue behind it, so a stored Massive
#: series that claims one of these is claiming a venue the provider cannot
#: support, and the write refuses to inherit it.
KNOWN_VENUES: frozenset[str] = frozenset({
    'iex', 'sip', 'futu_nasdaq_totalview', 'futu_arca',
})


def extract_bar(raw: dict) -> dict:
    """Refuse incomplete or inconsistent OHLCV rather than filling values."""
    try:
        values = {name: Decimal(str(raw[key])) for name, key in
                  [('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c'), ('volume', 'v')]}
        if any(not value.is_finite() or value < 0 for value in values.values()):
            raise ValueError
        if (values['high'] < max(values['open'], values['close'], values['low'])
                or values['low'] > min(values['open'], values['close'])):
            raise ValueError
        stamp = datetime.fromtimestamp(float(Decimal(str(raw['t'])) / 1000), tz=timezone.utc)
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        raise ValueError('Invalid Massive OHLCV bar') from None
    return {**values, 'event_at': stamp, 'source': 'massive'}


def _refuse_inconsistent_partitions(root, series, manifest):
    """Refuse a tape whose files and index disagree, before anything is written.

    The manifest is the index of the tape. When the files on disk and the
    index name different partitions, the tape has two stories about what it
    holds, and neither can be trusted to be the one the other describes.

    Two ways this happens, and both are refused:

    - A partition file exists that the manifest does not list. It was
      written but never committed to the index, so a later write over it
      would bless values nobody vouched for, and a reader would silently
      ignore a month of history.
    - The manifest is gone while partition files remain. Without the index
      there is no way to tell which file holds which month, so a write would
      rebuild an index that quietly drops what is already stored.

    This check lives at the Massive boundary rather than in the storage
    layer, because the storage layer's general recovery rule is to keep and
    read back a partition file that has no manifest entry. That rule is
    right for recovering history; it is wrong for a write that would then
    re-bless those values.
    """
    from gabfin.storage.tape import manifest_partition_paths, stored_partition_paths

    on_disk = stored_partition_paths(root, series)
    if manifest is None:
        if on_disk:
            raise ValueError('Massive tape partitions exist without a manifest')
        return
    listed = manifest_partition_paths(manifest)
    if on_disk != listed:
        raise ValueError('Massive tape partitions do not match the manifest')


class MassiveHistory:
    def __init__(self, client: MassiveRestClient):
        self._client = client

    def store(self, root, symbol: str, *, timeframe, start: date, end: date,
              now: datetime):
        """Persist validated adjusted vendor bars; venue coverage stays unverified."""
        from gabfin.storage.manifest import read_manifest, write_manifest
        from gabfin.storage.tape import (
            new_series, manifest_path, write_partitions, build_manifest,
            manifest_partition_paths, stored_partition_paths,
        )
        if not re.fullmatch(r'[A-Z0-9]+(?:\.[A-Z0-9]+)*', symbol):
            raise ValueError('Invalid Massive tape symbol')
        if now.tzinfo is None or start > end:
            raise ValueError('Invalid Massive tape clock or range')
        spans = {'second': 'second', 'minute': 'minute', 'hour': 'hour',
                 'trading_day': 'day', 'week': 'week', 'month': 'month'}
        if timeframe.unit.value not in spans:
            raise ValueError('Unsupported Massive tape timeframe')
        series = new_series(symbol, timeframe.model_dump(mode='json'), source='massive',
            venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
        path = manifest_path(root, series)
        existing = None
        if path.exists():
            existing = read_manifest(path)
            if (existing.series.source != 'massive'
                    or existing.series.adjustment != 'adjusted'):
                raise ValueError('Existing tape provenance does not match Massive history')
            if existing.series.venue_coverage in KNOWN_VENUES:
                # Massive history has no named venue behind it, so a stored
                # series that claims one is not a Massive series. Refuse it
                # rather than inherit a venue the provider cannot support.
                raise ValueError(
                    'Massive tape must not claim a venue, '
                    f'not {existing.series.venue_coverage}')
            from hashlib import sha256
            for partition in existing.partitions:
                if sha256((root / partition.path).read_bytes()).hexdigest() != partition.sha256:
                    raise ValueError('Existing tape partition checksum mismatch')
            series = existing.series
        _refuse_inconsistent_partitions(root, series, existing)
        rows = list(self.bars(symbol, multiplier=timeframe.count, timespan=spans[timeframe.unit.value],
                              start=start, end=end))
        if not rows:
            raise ValueError('No Massive history bars to store')
        seen = set()
        for row in rows:
            stamp = row['event_at']
            if row.get('source') != 'massive' or not start <= stamp.date() <= end or stamp > now:
                raise ValueError('Massive tape bar source or time range mismatch')
            if stamp in seen:
                raise ValueError('Duplicate Massive tape bar timestamp')
            seen.add(stamp)
        if existing is not None:
            from gabfin.storage.tape import read_rows
            # Every stored bar counts, not only the ones the retention window
            # still shows: a revised value for a bar the window hides is
            # still a changed bar, and it must not be written silently.
            stored = {row['event_at']: row for row in
                      read_rows(root, series, manifest=existing, apply_retention=False)}
            fields = ('open', 'high', 'low', 'close', 'volume')
            for row in rows:
                previous = stored.get(row['event_at'])
                # Compare under the tape's explicit float64 storage policy.
                if previous is not None and any(float(previous[name]) != float(row[name])
                                                for name in fields):
                    raise ValueError('Massive tape history conflict')
        written = write_partitions(root, series, rows, now=now)
        manifest = build_manifest(written.series, list(written.partitions), written_at=now)
        write_manifest(path, manifest)
        return manifest

    def bars(self, symbol: str, *, multiplier: int, timespan: str,
             start: date, end: date) -> tuple[dict, ...]:
        if (not re.fullmatch(r'(?:O:)?[A-Z0-9.]+', symbol)
                or isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier < 1
                or timespan not in ('second', 'minute', 'hour', 'day', 'week', 'month')
                or start > end):
            raise ValueError('Invalid Massive history query')
        path = (f'/v2/aggs/ticker/{quote(symbol, safe="")}/range/{multiplier}/{timespan}/'
                f'{start.isoformat()}/{end.isoformat()}?adjusted=true&sort=asc&limit=50000')
        return tuple(extract_bar(row) for row in self._client.results(path))


def main(argv=None):
    """Explicit read-only history import; credentials come from process environment."""
    import argparse
    import json
    from pathlib import Path
    from gabfin.contracts.market import Timeframe
    from gabfin.providers.massive.config import load_config

    parser = argparse.ArgumentParser(description='Import Massive equity history into the local tape')
    parser.add_argument('--tape', type=Path, required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--unit', choices=('minute', 'hour', 'trading_day', 'week', 'month'),
                        default='trading_day')
    args = parser.parse_args(argv)
    try:
        client = MassiveRestClient(load_config())
        manifest = MassiveHistory(client).store(args.tape, args.symbol,
            timeframe=Timeframe(count=args.count, unit=args.unit), start=args.start,
            end=args.end, now=datetime.now(timezone.utc))
        print(json.dumps({'status': 'stored', 'source': manifest.series.source,
            'rows': manifest.series.row_count, 'coverage': manifest.series.venue_coverage,
            'precision_policy': manifest.precision_policy, 'rest': client.stats}))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
