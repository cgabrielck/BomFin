"""Explicit local research operations. Credentials are read only from the process.

The capture command reads the local tape and, optionally, local JSON
files for the macro observations, the quote, the account and the risk
limits. Everything it reads is local, and everything it reads must have
been knowable at the moment the snapshot was taken.

That last rule is what the local files have to satisfy. A file names
when its fact became available, and a fact available after the cutoff
cannot be frozen into the snapshot: the snapshot would then cite
evidence that did not exist when it was taken. So a file that names a
moment after `as_of` is refused, and a file that names no moment at
all is refused too, because an unstamped fact cannot be proven
knowable.

A file that is not provided is simply absent. The capture records the
absence in its data quality and invents nothing: no account file means
no account, and no equity balance is made up to fill the gap.
"""
import argparse
import asyncio
from datetime import date, datetime, timezone
import json
from pathlib import Path
from uuid import UUID


#: The keys a local file may use to say when its fact was available.
#: `as_of` is the moment the fact was true; `available_at` is the
#: moment it could first be read. Either one is enough to place the
#: fact in time, and neither may be after the snapshot cutoff.
AVAILABILITY_KEYS = ('as_of', 'available_at')

#: The keys a local file may use to say when its fact was published.
PUBLICATION_KEYS = ('release_date', 'published_at')


class InputError(ValueError):
    """A local input file cannot be used for this snapshot.

    The message names the reason and never the payload.
    """


def _moment_of(value: object, label: str) -> datetime | date:
    """Read a moment from a local file.

    A date-only value stays a date, so a day is never mistaken for the
    midnight that starts it.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise InputError(f'{label} must be a timestamp')
    text = value.strip()
    if not text:
        raise InputError(f'{label} must be a timestamp')
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        raise InputError(f'{label} must be a timestamp') from None


def _check_in_time(record: dict, cutoff: datetime, label: str) -> None:
    """Refuse a local fact that was not knowable at the cutoff.

    A moment after the cutoff is look-ahead. A date after the cutoff
    day is look-ahead as well, and a date on the cutoff day is not: a
    release dated the cutoff day happened during that day.
    """
    for key in AVAILABILITY_KEYS:
        if key not in record:
            continue
        moment = _moment_of(record[key], f'{label} {key}')
        if isinstance(moment, datetime):
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            if moment.astimezone(timezone.utc) > cutoff:
                raise InputError(f'{label} {key} falls after the snapshot cutoff')
        elif moment > cutoff.date():
            raise InputError(f'{label} {key} falls after the snapshot cutoff')
    for key in PUBLICATION_KEYS:
        if key not in record:
            continue
        moment = _moment_of(record[key], f'{label} {key}')
        if isinstance(moment, datetime):
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            if moment.astimezone(timezone.utc) > cutoff:
                raise InputError(f'{label} {key} falls after the snapshot cutoff')
        elif moment > cutoff.date():
            raise InputError(f'{label} {key} falls after the snapshot cutoff')


def _check_stamped(record: dict, label: str) -> None:
    """Refuse a local fact that names no moment at all.

    A fact with no timestamp cannot be shown to have been knowable, so
    it cannot enter a snapshot that only holds knowable facts.
    """
    if not any(key in record for key in AVAILABILITY_KEYS):
        raise InputError(f'{label} names no moment; it cannot be shown to be knowable')


def _read_json(path: Path) -> object:
    """Read one local JSON document."""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except OSError as exc:
        raise InputError(f'{path.name} could not be read') from exc
    except json.JSONDecodeError as exc:
        raise InputError(f'{path.name} is not valid JSON') from exc


def _observation_reader(path: Path, cutoff: datetime):
    """A read-only observation source over a local JSON file.

    The rows already carry an explicit release date, because the file
    is a research input and not a raw FRED record. A row whose release
    date falls after the cutoff is refused here rather than filtered
    later, so the command fails loudly instead of quietly freezing a
    smaller set.
    """
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise InputError(f'{path.name} must hold a list of observations')
    rows = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise InputError(f'{path.name} observation {index} must be an object')
        _check_stamped(row, f'{path.name} observation {index}')
        _check_in_time(row, cutoff, f'{path.name} observation {index}')
        release = row.get('release_date')
        if release in (None, ''):
            raise InputError(
                f'{path.name} observation {index} has no release date; a macro '
                'point without one cannot be used in a backtest')
        release_day = _moment_of(release, 'release_date')
        if isinstance(release_day, datetime):
            release_day = release_day.astimezone(timezone.utc).date()
        if release_day > cutoff.date():
            raise InputError(
                f'{path.name} observation {index} was released after the '
                'snapshot cutoff')
        rows.append(row)

    def read(as_of: datetime) -> list[dict]:
        return rows

    return read


def _fact_reader(path: Path, cutoff: datetime, label: str):
    """A read-only source over one local JSON fact."""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise InputError(f'{path.name} must hold an object')
    _check_stamped(payload, label)
    _check_in_time(payload, cutoff, label)
    if label == 'account' and payload.get('equity') in (None, ''):
        raise InputError(
            f'{path.name} has no equity balance; an account without one '
            'cannot be read by the portfolio role')

    def read() -> dict:
        return payload

    return read


def _fred_reader(path: Path, series_id: str, cutoff: datetime):
    """A read-only observation source over a raw FRED file.

    The file holds the raw rows as FRED wrote them, and they carry a
    vintage rather than a release date. The adapter in
    `gabfin.research.capture` turns them into rows with an explicit
    release date, so the builder never sees a raw row.
    """
    from gabfin.analysis.sources import FredMacroSource
    from gabfin.research.capture import fred_observations

    payload = _read_json(path)
    if not isinstance(payload, list):
        raise InputError(f'{path.name} must hold a list of observations')

    class _LocalClient:
        """A client that answers from the local file, never the network."""

        def __init__(self, rows):
            self._rows = list(rows)

        def observations(self, series_id, start=None, end=None):
            return [dict(row) for row in self._rows]

    source = FredMacroSource(_LocalClient(payload))
    return fred_observations(source, series_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Snapshot capture, research run and durable checks')
    parser.add_argument('--database', type=Path, required=True)
    commands = parser.add_subparsers(dest='operation', required=True)
    capture = commands.add_parser('capture', help='Freeze local Massive tape for research')
    capture.add_argument('--tape', type=Path, required=True)
    capture.add_argument('--symbol', required=True)
    capture.add_argument('--instrument-id', type=UUID, required=True)
    capture.add_argument('--as-of', type=datetime.fromisoformat, required=True)
    capture.add_argument('--unit', choices=['minute', 'hour', 'trading_day'], default='trading_day')
    capture.add_argument('--observations-file', type=Path,
                         help='Local JSON file holding macro observations')
    capture.add_argument('--quote-file', type=Path,
                         help='Local JSON file holding the quote at the cutoff')
    capture.add_argument('--account-file', type=Path,
                         help='Local JSON file holding the account at the cutoff')
    capture.add_argument('--limits-file', type=Path,
                         help='Local JSON file holding the risk limits')
    capture.add_argument('--fred-file', type=Path,
                         help='Local JSON file holding raw FRED observation rows')
    capture.add_argument('--fred-series-id',
                         help='The FRED series id the raw rows belong to')
    run = commands.add_parser('run', help='Run a registered snapshot using configured LLM_* provider')
    run.add_argument('--snapshot-id', type=UUID, required=True)
    run.add_argument('--role', choices=['discovery', 'technical', 'portfolio'])
    run.add_argument('--roles', type=Path, default=Path('config/agents'))
    run.add_argument('--schemas', type=Path, default=Path('schemas/research'))
    checks = commands.add_parser('checks', help='Read durable research validation records')
    checks.add_argument('--snapshot-id', type=UUID, required=True)
    args = parser.parse_args(argv)
    try:
        from gabfin.research.store import ResearchStore
        store = ResearchStore(args.database)
        if args.operation == 'capture':
            from gabfin.analysis.sources import TapeBarSource
            from gabfin.contracts.market import Timeframe
            from gabfin.research.capture import SnapshotCapture
            cutoff = args.as_of
            if cutoff.tzinfo is None or cutoff.utcoffset() is None:
                # A naive moment means different things in different
                # places, and a snapshot with an ambiguous cutoff is not
                # a snapshot. The command refuses it rather than
                # assuming a zone.
                raise InputError('--as-of must be an aware UTC datetime')
            cutoff = cutoff.astimezone(timezone.utc)
            observations = None
            if args.observations_file is not None:
                observations = _observation_reader(args.observations_file, cutoff)
            elif args.fred_file is not None:
                if not args.fred_series_id:
                    raise InputError('--fred-file needs --fred-series-id')
                observations = _fred_reader(args.fred_file, args.fred_series_id, cutoff)
            quote = None if args.quote_file is None else _fact_reader(
                args.quote_file, cutoff, 'quote')
            account = None if args.account_file is None else _fact_reader(
                args.account_file, cutoff, 'account')
            limits = None if args.limits_file is None else _fact_reader(
                args.limits_file, cutoff, 'limits')
            snapshot = SnapshotCapture(
                store,
                bars=TapeBarSource(args.tape, symbol=args.symbol, source='massive'),
                observations=observations, quote=quote, account=account, limits=limits,
            ).capture(
                instrument_id=args.instrument_id, symbol=args.symbol,
                timeframe=Timeframe(count=1, unit=args.unit), as_of=args.as_of)
            response = {'status': 'captured', 'snapshot_id': str(snapshot['snapshot_id']),
                        'data_quality': snapshot['data_quality']}
        elif args.operation == 'checks':
            response = {'checks': [record.model_dump(mode='json') for record in store.checks(args.snapshot_id)]}
        else:
            from gabfin.research.service import configured_service
            result = asyncio.run(configured_service(store, roles_dir=args.roles, schema_dir=args.schemas).run(
                args.snapshot_id, role=args.role))
            response = {'status': result['status'], 'reports': result.get('reports', result.get('report')),
                        'audit_count': len(result['audit'])}
        print(json.dumps(response))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
