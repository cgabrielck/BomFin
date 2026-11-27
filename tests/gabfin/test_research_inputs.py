"""The research input wiring: FRED rows, local files and the frozen snapshot.

Two things are pinned down here, and both are about honesty.

The first is the FRED seam. `FredMacroSource.observations` hands back the
raw rows exactly as FRED wrote them, and those rows carry a vintage
(`realtime_start`) rather than a release date. A vintage says which
revision of a value was served, not the day the value was published.
The adapter that turns those rows into research input therefore has to
say which day each value became knowable, and it says it from the
canonical conversion in `fred/fetch.py`, not from a guess made inside
the snapshot builder.

The second is the CLI seam. The capture command may read local JSON
files, but it must never read one that describes a moment after the
snapshot cutoff. A file that says "this was available at 21:00" and a
snapshot taken at 20:00 are contradictory, and the command refuses
rather than quietly freezing the later fact into the earlier snapshot.

The rules:
    10|- A FRED row with no release stamp is refused. The adapter does not
  invent one, and it never falls back to the series date.
- An observation released after `as_of` is left out, not clamped.
- The adapter reads the raw rows once and hands the builder rows that
  already carry an explicit `release_date`.
- A local file that names a moment after `as_of` is refused by the CLI.
- A local file that names no moment at all is refused too: an unstamped
  fact cannot be proven knowable.
- A file that is not provided is simply absent, and the snapshot says
  so in its data quality.
- The snapshot's `massive_snapshot` is the frozen quote when there is
  one, so a role that asks for the market snapshot gets the same
  evidence the quote carries.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gabfin.contracts.market import Timeframe, TimeUnit


AS_OF = datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc)
INSTRUMENT = UUID('11111111-1111-4111-8111-111111111111')
SYMBOL = 'AAPL'
DAILY = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)
ROOT = Path(__file__).resolve().parents[2]


# --- stubs ------------------------------------------------------------------

class FakeStore:
    """A store that records what the builder asked it to write."""

    def __init__(self):
        self.calls = []

    def create_snapshot(self, *, as_of, context, data_quality, evidence_ids):
        snapshot_id = uuid4()
        self.calls.append({
            'snapshot_id': snapshot_id,
            'as_of': as_of,
            'context': context,
            'data_quality': list(data_quality),
            'evidence_ids': frozenset(evidence_ids),
        })
        return snapshot_id

    @property
    def call(self):
        assert self.calls, 'the builder did not write a snapshot'
        return self.calls[-1]


class StubFredClient:
    """A FRED client that answers from a fixture instead of the network."""

    def __init__(self, rows):
        self._rows = list(rows)
        self.requested = []

    def observations(self, series_id, start=None, end=None):
        self.requested.append(series_id)
        return [dict(row) for row in self._rows]


def raw_fred_rows(*rows):
    """Raw FRED observation rows, exactly as the provider serves them."""
    return [
        {
            'realtime_start': row['realtime_start'],
            'realtime_end': row['realtime_end'],
            'date': row['date'],
            'value': row['value'],
        }
        for row in rows
    ]


class StubFredSource:
    """The shape of `FredMacroSource`: raw rows for one series."""

    def __init__(self, rows):
        self._rows = list(rows)

    def observations(self, series_id):
        return [dict(row) for row in self._rows]


def write_tape(root: Path, symbol='AAPL', *, count=60, venue='sip', source='fixture',
               timeframe=DAILY, start=datetime(2026, 10, 1, tzinfo=timezone.utc),
               step=None):
    """Write a deterministic series into the tape and return its manifest."""
    from datetime import timedelta

    from gabfin.storage.manifest import write_manifest
    from gabfin.storage.tape import build_manifest, manifest_path, new_series, write_partitions

    if step is None:
        step = timedelta(days=1)
    series = new_series(
        symbol, {'count': timeframe.count, 'unit': timeframe.unit.value}, source=source,
        venue_coverage=venue, adjustment='unadjusted', retention='rolling_2y')
    rows = []
    for index in range(count):
        close = Decimal('100') + Decimal((index * 7) % 23) - Decimal(11)
        rows.append({
            'event_at': start + step * index,
            'open': close - Decimal('0.10'),
            'high': close + Decimal('1.50'),
            'low': close - Decimal('1.25'),
            'close': close,
            'volume': Decimal(1000 + index * 37),
        })
    written = write_partitions(root, series, rows, now=datetime(2026, 11, 20, tzinfo=timezone.utc))
    manifest = build_manifest(written.series, written.partitions,
                              written_at=datetime(2026, 11, 20, tzinfo=timezone.utc))
    write_manifest(manifest_path(root, written.series), manifest)
    return manifest


def write_cli_tape(root: Path, symbol='AAPL', *, count=60):
    """Write the tape the capture command reads.

    The command reads the Massive tape, and a Massive series carries no
    venue behind it, so the coverage is `unknown`.
    """
    return write_tape(root, symbol, count=count, venue='unknown', source='massive')


def _capture(store, *, tape_root=None, observations=None, quote=..., account=..., limits=...):
    from gabfin.analysis.sources import TapeBarSource
    from gabfin.research.capture import SnapshotCapture

    if tape_root is None:
        import tempfile
        tape_root = Path(tempfile.mkdtemp(prefix='gabfin-tape-'))
        write_tape(tape_root, count=60, venue='sip')
    if quote is ...:
        quote = lambda: {'price': '211.50', 'evidence_id': str(uuid4())}
    if account is ...:
        account = lambda: {'equity': '100000.00', 'evidence_id': str(uuid4()),
                           'position_count': 2, 'max_weight': '0.25'}
    if limits is ...:
        limits = lambda: {'per_trade_risk': '0.01', 'daily_loss': '0.02'}
    return SnapshotCapture(store, bars=TapeBarSource(tape_root, symbol=SYMBOL, source='fixture'),
                           observations=observations, quote=quote, account=account, limits=limits)


# --- the FRED adapter --------------------------------------------------------

def test_the_adapter_hands_the_builder_rows_with_an_explicit_release_date():
    """The builder's rule is explicit release dates, so the adapter supplies them."""
    from gabfin.research.capture import fred_observations

    source = StubFredSource(raw_fred_rows({
        'realtime_start': '2026-11-01', 'realtime_end': '2026-11-01',
        'date': '2026-10-01', 'value': '310.5',
    }))
    read = fred_observations(source, 'CPIAUCSL')
    rows = read(AS_OF)
    assert len(rows) == 1
    assert rows[0]['release_date'] == '2026-11-01'
    assert rows[0]['observation_date'] == '2026-10-01'
    assert rows[0]['series_id'] == 'CPIAUCSL'


def test_the_adapter_asks_the_source_for_the_named_series():
    from gabfin.research.capture import fred_observations

    class Recording(StubFredSource):
        def __init__(self, rows):
            super().__init__(rows)
            self.asked = []

        def observations(self, series_id):
            self.asked.append(series_id)
            return super().observations(series_id)

    source = Recording(raw_fred_rows({
        'realtime_start': '2026-11-01', 'realtime_end': '2026-11-01',
        'date': '2026-10-01', 'value': '310.5',
    }))
    fred_observations(source, 'CPIAUCSL')(AS_OF)
    assert source.asked == ['CPIAUCSL']


def test_the_adapter_leaves_out_an_observation_released_after_as_of():
    """A value published after the cutoff was not knowable at the cutoff."""
    from gabfin.research.capture import fred_observations

    source = StubFredSource(raw_fred_rows(
        {'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
         'date': '2026-10-01', 'value': '310.5'},
        {'realtime_start': '2026-12-30', 'realtime_end': '2026-12-30',
         'date': '2026-11-01', 'value': '311.5'},
    ))
    rows = fred_observations(source, 'CPIAUCSL')(AS_OF)
    assert len(rows) == 1
    assert rows[0]['release_date'] == '2026-11-20'


def test_the_adapter_refuses_a_row_with_no_release_stamp():
    """No stamp means no release date, and the adapter does not invent one."""
    from gabfin.research.capture import fred_observations

    rows = raw_fred_rows({'realtime_start': '2026-11-01', 'realtime_end': '2026-11-01',
                           'date': '2026-10-01', 'value': '310.5'})
    rows[0].pop('realtime_start')
    source = StubFredSource(rows)
    with pytest.raises(Exception) as error:
        fred_observations(source, 'CPIAUCSL')(AS_OF)
    assert 'release' in str(error.value).lower()


def test_the_adapter_never_substitutes_the_series_date_for_the_release_date():
    """The series date describes the period, not the publication."""
    from gabfin.research.capture import fred_observations

    rows = raw_fred_rows({'realtime_start': '2026-11-01', 'realtime_end': '2026-11-01',
                           'date': '2026-10-01', 'value': '310.5'})
    rows[0].pop('realtime_start')
    rows[0].pop('realtime_end')
    source = StubFredSource(rows)
    with pytest.raises(Exception):
        fred_observations(source, 'CPIAUCSL')(AS_OF)


def test_the_adapter_drops_an_observation_with_no_published_value():
    """A period FRED published without a number is information, not a value."""
    from gabfin.research.capture import fred_observations

    source = StubFredSource(raw_fred_rows({
        'realtime_start': '2026-11-01', 'realtime_end': '2026-11-01',
        'date': '2026-10-01', 'value': '.',
    }))
    assert fred_observations(source, 'CPIAUCSL')(AS_OF) == []


def test_a_real_fred_source_with_a_stub_client_feeds_the_capture():
    """The seam works end to end with the real source class.

    The client is a stub, so no network is touched, but the source is
    the real one and the rows are the real raw shape.
    """
    from gabfin.analysis.sources import FredMacroSource
    from gabfin.research.capture import fred_observations

    client = StubFredClient(raw_fred_rows(
        {'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
         'date': '2026-10-01', 'value': '310.5'},
        {'realtime_start': '2026-12-30', 'realtime_end': '2026-12-30',
         'date': '2026-11-01', 'value': '311.5'},
    ))
    source = FredMacroSource(client)
    rows = fred_observations(source, 'CPIAUCSL')(AS_OF)
    assert client.requested == ['CPIAUCSL']
    assert [row['release_date'] for row in rows] == ['2026-11-20']


def test_the_capture_uses_the_adapter_output_without_reinterpreting_it():
    """The builder sees the adapter's rows and accepts them as they are."""
    from gabfin.analysis.sources import FredMacroSource
    from gabfin.research.capture import fred_observations

    client = StubFredClient(raw_fred_rows({
        'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
        'date': '2026-10-01', 'value': '310.5',
    }))
    store = FakeStore()
    capture = _capture(store, observations=fred_observations(FredMacroSource(client), 'CPIAUCSL'))
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    rows = store.call['context']['observations']
    assert len(rows) == 1
    assert rows[0]['release_date'] == '2026-11-20'
    assert rows[0]['observation_date'] == '2026-10-01'


def test_the_capture_still_refuses_a_row_the_adapter_never_vintaged():
    """A raw row handed straight to the builder is still refused."""
    store = FakeStore()
    capture = _capture(store, observations=lambda as_of: [
        {'series_id': 'CPIAUCSL', 'date': '2026-10-01', 'value': '310.5',
         'realtime_start': '2026-11-01'},
    ])
    with pytest.raises(Exception) as error:
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert 'release' in str(error.value).lower()
    assert store.calls == []


def test_the_adapter_does_not_change_the_canonical_fred_contract():
    """The canonical contract still refuses a release before the period."""
    from gabfin.providers.fred.fetch import to_point

    with pytest.raises(Exception):
        to_point({'realtime_start': '2026-01-01', 'realtime_end': '2026-01-01',
                  'date': '2026-01-15', 'value': '1.5'}, series_id='UNRATE')


# --- the frozen market snapshot ---------------------------------------------

def test_the_market_snapshot_is_the_frozen_quote_when_there_is_one():
    """A role that asks for the market snapshot gets the quote's evidence."""
    store = FakeStore()
    quote_evidence = str(uuid4())
    capture = _capture(store, quote=lambda: {
        'price': '211.50', 'evidence_id': quote_evidence, 'symbol': SYMBOL})
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    snapshot = result['context']['massive_snapshot']
    assert snapshot
    assert snapshot['evidence_id'] == quote_evidence
    assert snapshot['price'] == '211.50'


def test_a_missing_market_snapshot_is_an_explicit_absence():
    """No quote means no market snapshot, and the snapshot says so."""
    store = FakeStore()
    result = _capture(store, quote=None).capture(
        instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert result['context']['massive_snapshot'] is None
    assert 'massive_snapshot' in ' '.join(result['data_quality'])


def test_the_market_snapshot_carries_the_same_evidence_as_the_quote():
    """The tool and the context must not disagree about what was seen."""
    store = FakeStore()
    quote_evidence = str(uuid4())
    capture = _capture(store, quote=lambda: {
        'price': '211.50', 'evidence_id': quote_evidence})
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    context = result['context']
    assert context['massive_snapshot']['evidence_id'] == context['quote']['evidence_id']


def test_the_market_snapshot_tool_reads_the_frozen_quote():
    """`read_massive_snapshot` returns the snapshot, not a missing field."""
    from gabfin.research.tools import SnapshotTools

    store = FakeStore()
    capture = _capture(store, quote=lambda: {'price': '211.50', 'evidence_id': str(uuid4())})
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    tools = SnapshotTools(result['context']).mapping()
    import asyncio
    data = asyncio.run(tools['read_massive_snapshot']({}))
    assert data['price'] == '211.50'


def test_the_market_snapshot_tool_reports_a_missing_snapshot_honestly():
    """Without a quote the tool has nothing to report, and says so.

    The tool answers with nothing rather than with an invented market
    view, and the snapshot names the absence in its data quality.
    """
    from gabfin.research.tools import SnapshotTools

    store = FakeStore()
    result = _capture(store, quote=None).capture(
        instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    tools = SnapshotTools(result['context']).mapping()
    import asyncio
    data = asyncio.run(tools['read_massive_snapshot']({}))
    assert data is None
    assert 'massive_snapshot' in ' '.join(result['data_quality'])


# --- the CLI -----------------------------------------------------------------

def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def _run(argv):
    from gabfin.research.__main__ import main

    return main(argv)


def test_the_capture_command_accepts_the_local_input_files(tmp_path, capsys):
    """The command reads what it is told to read, and nothing else."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    observations = _write(tmp_path / 'observations.json', [
        {'series_id': 'CPIAUCSL', 'date': '2026-10-01', 'value': '310.5',
         'release_date': '2026-11-20', 'available_at': '2026-11-20T00:00:00Z'},
    ])
    quote = _write(tmp_path / 'quote.json', {
        'price': '211.50', 'evidence_id': str(uuid4()),
        'available_at': '2026-11-27T20:00:00Z'})
    account = _write(tmp_path / 'account.json', {
        'equity': '100000.00', 'evidence_id': str(uuid4()), 'position_count': 2,
        'max_weight': '0.25', 'available_at': '2026-11-27T20:00:00Z'})
    limits = _write(tmp_path / 'limits.json', {
        'per_trade_risk': '0.01', 'daily_loss': '0.02',
        'available_at': '2026-11-27T20:00:00Z'})

    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--observations-file', str(observations),
        '--quote-file', str(quote),
        '--account-file', str(account),
        '--limits-file', str(limits),
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'captured'
    assert payload['snapshot_id']


def test_the_capture_command_works_without_the_optional_files(tmp_path, capsys):
    """A file that is not provided is absent, and the capture still succeeds."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'captured'
    quality = ' '.join(payload['data_quality'])
    assert 'quote' in quality
    assert 'account' in quality


def test_the_capture_command_refuses_a_file_that_is_from_the_future(tmp_path, capsys):
    """A fact available after the cutoff cannot be frozen into the snapshot."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    quote = _write(tmp_path / 'quote.json', {
        'price': '211.50', 'evidence_id': str(uuid4()),
        'available_at': '2026-11-28T09:00:00Z'})
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--quote-file', str(quote),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_refuses_a_file_with_no_moment(tmp_path, capsys):
    """An unstamped fact cannot be proven knowable, so it is refused."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    quote = _write(tmp_path / 'quote.json', {
        'price': '211.50', 'evidence_id': str(uuid4())})
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--quote-file', str(quote),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_refuses_an_observation_released_after_as_of(tmp_path, capsys):
    """An observation released after the cutoff is refused, not clamped."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    observations = _write(tmp_path / 'observations.json', [
        {'series_id': 'CPIAUCSL', 'date': '2026-11-01', 'value': '311.5',
         'release_date': '2026-12-30', 'available_at': '2026-12-30T00:00:00Z'},
    ])
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--observations-file', str(observations),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_reads_a_fred_fixture_through_the_adapter(tmp_path, capsys):
    """Raw FRED rows may be converted by the adapter before the capture."""
    from gabfin.analysis.sources import FredMacroSource

    class LocalClient:
        def __init__(self, rows):
            self._rows = list(rows)

        def observations(self, series_id, start=None, end=None):
            return [dict(row) for row in self._rows]

    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    fred_file = _write(tmp_path / 'fred.json', raw_fred_rows({
        'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
        'date': '2026-10-01', 'value': '310.5',
    }))
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--fred-file', str(fred_file),
        '--fred-series-id', 'CPIAUCSL',
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'captured'


def test_the_capture_command_refuses_a_fred_row_with_no_release_stamp(tmp_path, capsys):
    """The adapter refuses the row rather than inventing a release date."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    rows = raw_fred_rows({'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
                           'date': '2026-10-01', 'value': '310.5'})
    rows[0].pop('realtime_start')
    rows[0].pop('realtime_end')
    fred_file = _write(tmp_path / 'fred.json', rows)
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--fred-file', str(fred_file),
        '--fred-series-id', 'CPIAUCSL',
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_never_fabricates_an_account(tmp_path, capsys):
    """Without an account file there is no account, and no invented equity."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert 'account' in ' '.join(payload['data_quality'])
    assert 'equity' not in json.dumps(payload)


def test_the_capture_command_refuses_a_naive_as_of(tmp_path, capsys):
    """A cutoff with no zone is ambiguous, and an ambiguous cutoff is refused."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00',
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_refuses_a_fred_file_without_a_series(tmp_path, capsys):
    """Raw rows with no series id cannot be placed, so they are refused."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    fred_file = _write(tmp_path / 'fred.json', raw_fred_rows({
        'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
        'date': '2026-10-01', 'value': '310.5',
    }))
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--fred-file', str(fred_file),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_refuses_an_observation_available_after_the_cutoff(tmp_path, capsys):
    """The availability stamp is checked, not only the release date."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    observations = _write(tmp_path / 'observations.json', [
        {'series_id': 'CPIAUCSL', 'date': '2026-10-01', 'value': '310.5',
         'release_date': '2026-11-20', 'available_at': '2026-11-28T09:00:00Z'},
    ])
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--observations-file', str(observations),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


def test_the_capture_command_refuses_an_account_without_equity(tmp_path, capsys):
    """An account with no equity balance cannot be read by the portfolio role."""
    database = tmp_path / 'research.sqlite'
    tape = tmp_path / 'tape'
    write_cli_tape(tape, count=60)
    account = _write(tmp_path / 'account.json', {
        'position_count': 2, 'max_weight': '0.25',
        'available_at': '2026-11-27T20:00:00Z'})
    code = _run([
        '--database', str(database), 'capture',
        '--tape', str(tape), '--symbol', SYMBOL,
        '--instrument-id', str(INSTRUMENT),
        '--as-of', '2026-11-27T21:00:00Z',
        '--account-file', str(account),
    ])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['status'] == 'failed'


# --- the store round trip ----------------------------------------------------

def test_the_real_store_accepts_a_capture_built_from_the_adapter(tmp_path):
    """The adapter's rows pass the store's own look-ahead and evidence rules."""
    from gabfin.analysis.sources import FredMacroSource
    from gabfin.research.capture import fred_observations
    from gabfin.research.store import ResearchStore

    client = StubFredClient(raw_fred_rows(
        {'realtime_start': '2026-11-20', 'realtime_end': '2026-11-20',
         'date': '2026-10-01', 'value': '310.5'},
    ))
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = _capture(store, observations=fred_observations(FredMacroSource(client), 'CPIAUCSL'))
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    stored = store.get_snapshot(result['snapshot_id'])
    rows = stored['context']['observations']
    assert rows[0]['release_date'] == '2026-11-20'


def test_the_real_store_refuses_a_capture_that_cites_a_future_observation(tmp_path):
    """A row released after the cutoff cannot reach the store."""
    from gabfin.analysis.sources import FredMacroSource
    from gabfin.research.capture import fred_observations
    from gabfin.research.store import ResearchStore

    client = StubFredClient(raw_fred_rows(
        {'realtime_start': '2026-12-30', 'realtime_end': '2026-12-30',
         'date': '2026-11-01', 'value': '311.5'},
    ))
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = _capture(store, observations=fred_observations(FredMacroSource(client), 'CPIAUCSL'))
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    stored = store.get_snapshot(result['snapshot_id'])
    assert stored['context']['observations'] == []


def test_the_real_store_holds_the_market_snapshot_with_the_quote_evidence(tmp_path):
    """The frozen quote and the market snapshot carry one evidence id."""
    from gabfin.research.store import ResearchStore

    store = ResearchStore(tmp_path / 'research.sqlite')
    quote_evidence = str(uuid4())
    capture = _capture(store, quote=lambda: {
        'price': '211.50', 'evidence_id': quote_evidence})
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    stored = store.get_snapshot(result['snapshot_id'])
    context = stored['context']
    assert context['massive_snapshot']['evidence_id'] == context['quote']['evidence_id']
    assert quote_evidence in store.evidence_ids(result['snapshot_id'])
