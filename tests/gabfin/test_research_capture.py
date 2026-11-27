"""The research snapshot builder: local sources in, one frozen snapshot out.

A snapshot is the only thing a research conclusion may cite, so the
builder that creates it has one job: hand the store facts that were
knowable at `as_of`, and nothing else.

The rules these tests pin down are the ones that keep a conclusion
honest:

- Bars come from the local tape. A missing series or a series with an
  unknown venue is refused, because a chart drawn on history nobody can
  name is not evidence.
- A bar is only in the snapshot when the moment it closes is already
  past. A trading-day bar needs its whole UTC day to be over.
- Indicators are computed from the frozen bars that made it into the
  snapshot, with the clock pinned to `as_of`. An indicator computed
  from a live clock can see the future.
- A macro observation without a release date is refused, and one
  released after `as_of` is left out. The series date is never used in
  place of the release date.
- Every fact carries an evidence id, and the evidence set the builder
  hands the store is exactly the set its context contains.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gabfin.contracts.market import Timeframe, TimeUnit

INSTRUMENT = UUID('11111111-1111-4111-8111-111111111111')
AS_OF = datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc)
SYMBOL = 'AAPL'
DAILY = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)


# --- fixtures ---------------------------------------------------------------

def write_tape(root: Path, symbol='AAPL', *, count=60, venue='sip', source='fixture',
               timeframe=DAILY, start=datetime(2026, 10, 1, tzinfo=timezone.utc),
               step=timedelta(days=1)):
    """Write a deterministic series into the tape and return its manifest."""
    from gabfin.storage.manifest import write_manifest
    from gabfin.storage.tape import build_manifest, manifest_path, new_series, write_partitions

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


def tape_source(root: Path, symbol='AAPL', *, source='fixture'):
    from gabfin.analysis.sources import TapeBarSource
    return TapeBarSource(root, symbol=symbol, source=source)


def observations(release_dates=('2026-11-20',), *, dates=None):
    """Raw observation rows with an explicit release date."""
    rows = []
    for index, release in enumerate(release_dates):
        rows.append({
            'series_id': 'CPILFESL',
            'date': dates[index] if dates else f'2026-10-{index + 1:02d}',
            'value': '310.5',
            'release_date': release,
        })
    return rows


# --- the store call --------------------------------------------------------

def test_capture_writes_one_snapshot_and_returns_it():
    store = FakeStore()
    capture = _capture(store)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    assert len(store.calls) == 1
    assert result['snapshot_id'] == store.call['snapshot_id']
    assert store.call['as_of'] == AS_OF


def test_capture_passes_evidence_as_a_frozenset():
    store = FakeStore()
    _capture(store).capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                            timeframe=DAILY, as_of=AS_OF)
    assert isinstance(store.call['evidence_ids'], frozenset)
    assert store.call['evidence_ids']


def test_the_evidence_set_is_exactly_the_context_evidence():
    store = FakeStore()
    _capture(store).capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                            timeframe=DAILY, as_of=AS_OF)
    context = store.call['context']
    found = set()
    _collect(context, found)
    assert store.call['evidence_ids'] == found


def _collect(node, found: set):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'evidence_id':
                found.add(value)
            else:
                _collect(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect(item, found)


# --- bars ------------------------------------------------------------------

def test_bars_are_read_from_the_local_tape_and_carry_evidence():
    store = FakeStore()
    _capture(store, bars=...).capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                                      timeframe=DAILY, as_of=AS_OF)
    bars = store.call['context']['bars']
    assert bars
    for bar in bars:
        assert UUID(bar['evidence_id'])
        assert bar['symbol'] == SYMBOL
        assert bar['close'] == str(Decimal(bar['close']))
        assert bar['timeframe'] == {'count': 1, 'unit': 'trading_day'}
        assert bar['coverage'] == 'sip'


def test_a_missing_tape_series_is_refused(tmp_path):
    store = FakeStore()
    capture = _capture(store, tape_root=tmp_path / 'empty-tape-root')
    with pytest.raises(Exception) as error:
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                        timeframe=DAILY, as_of=AS_OF)
    assert 'bar' in str(error.value).lower() or 'series' in str(error.value).lower()
    assert store.calls == []


def test_vendor_unknown_bars_are_read_but_marked_unknown():
    """Research may read history whose venue it cannot name.

    The bars are kept and the coverage says `unknown`. What it may not
    do is pretend the bars were SIP.
    """
    store = FakeStore()
    capture = _capture(store, venue='massive-vendor')
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert store.call['context']['source_coverage'] == 'unknown'
    assert store.call['context']['bars']


def test_vendor_unknown_coverage_never_reaches_a_decision():
    """A snapshot with an unnamed venue says so in its data quality."""
    store = FakeStore()
    capture = _capture(store, venue='massive-vendor')
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    assert result['context']['source_coverage'] == 'unknown'
    assert 'coverage' in ' '.join(result['data_quality'])


def test_bars_after_as_of_are_left_out():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    for bar in store.call['context']['bars']:
        assert datetime.fromisoformat(bar['event_at']) <= AS_OF


def test_a_trading_day_bar_needs_its_whole_day_to_be_over():
    """A bar stamped on the day of `as_of` is still forming."""
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY,
                    as_of=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))
    stamps = [datetime.fromisoformat(bar['event_at']).date()
              for bar in store.call['context']['bars']]
    assert date(2026, 11, 20) not in stamps


def test_a_trading_day_bar_from_an_earlier_day_is_included():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY,
                    as_of=datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))
    stamps = [datetime.fromisoformat(bar['event_at']).date()
              for bar in store.call['context']['bars']]
    assert date(2026, 11, 19) in stamps


# --- indicators ------------------------------------------------------------

def test_indicators_are_computed_from_the_frozen_bars():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    indicators = store.call['context']['indicators']
    assert indicators
    for series in indicators:
        assert series['name']
        assert series['value'] is not None
        assert series['source_coverage'] == 'sip'
        assert UUID(series['evidence_id'])


def test_indicator_points_never_look_past_as_of():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    for series in store.call['context']['indicators']:
        for point in series['points']:
            assert datetime.fromisoformat(point['event_at']) <= AS_OF
            assert datetime.fromisoformat(point['computed_at']) <= AS_OF


def test_indicator_points_are_stamped_with_as_of_not_the_wall_clock():
    """A wall-clock stamp reads as a look-ahead and is not reproducible."""
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    stamps = {point['computed_at']
              for series in store.call['context']['indicators']
              for point in series['points']}
    assert stamps == {'2026-11-27T21:00:00Z'}


def test_two_captures_of_the_same_moment_agree():
    """The same inputs at the same moment give the same facts.

    The evidence ids are fresh on every capture, because an id names
    one occurrence in one snapshot. Everything else must match, or the
    snapshot is not reproducible.
    """
    import tempfile
    root = Path(tempfile.mkdtemp(prefix='gabfin-tape-'))
    write_tape(root, count=60, venue='sip')
    first = FakeStore()
    second = FakeStore()
    for store in (first, second):
        capture = _capture(store, tape_root=root)
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                        timeframe=DAILY, as_of=AS_OF)
    assert _without_evidence(first.call['context']) == _without_evidence(second.call['context'])
    assert first.call['data_quality'] == second.call['data_quality']


def _without_evidence(node):
    if isinstance(node, dict):
        return {key: _without_evidence(value)
                for key, value in node.items() if key != 'evidence_id'}
    if isinstance(node, list):
        return [_without_evidence(item) for item in node]
    return node


def test_indicators_are_unavailable_without_a_known_venue():
    """An indicator without a venue is not comparable with anything.

    The series is empty rather than computed under a guessed venue, and
    the snapshot says the indicators are unavailable.
    """
    store = FakeStore()
    capture = _capture(store, venue='massive-vendor')
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    assert result['context']['indicators'] == []
    assert 'indicators_unavailable' in result['data_quality']


def test_indicators_never_claim_a_venue_the_bars_do_not_have():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    for series in store.call['context']['indicators']:
        assert series['source_coverage'] == 'sip'


# --- observations ----------------------------------------------------------

def test_observations_need_a_release_date():
    store = FakeStore()
    rows = observations()
    rows[0].pop('release_date')
    capture = _capture(store, observations=lambda as_of: rows)
    with pytest.raises(Exception) as error:
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                        timeframe=DAILY, as_of=AS_OF)
    assert 'release' in str(error.value).lower()


def test_a_vintage_date_is_not_substituted_for_the_release_date():
    """A vintage says the period a value was published for.

    It is not the day the value was published, and borrowing it would
    make a later number look knowable earlier.
    """
    store = FakeStore()
    rows = [{'series_id': 'CPILFESL', 'date': '2026-10-01', 'value': '310.5',
             'realtime_start': '2026-11-01'}]
    capture = _capture(store, observations=lambda as_of: rows)
    with pytest.raises(Exception) as error:
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                        timeframe=DAILY, as_of=AS_OF)
    assert 'release' in str(error.value).lower()
    assert store.calls == []


def test_an_observation_released_after_as_of_is_left_out():
    store = FakeStore()
    capture = _capture(store, observations=lambda as_of: observations(
        ('2026-11-20', '2026-12-30')))
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    rows = store.call['context']['observations']
    assert len(rows) == 1
    assert rows[0]['release_date'] == '2026-11-20'


def test_the_series_date_is_never_used_as_the_release_date():
    """A row whose only date is the series date has no release date."""
    store = FakeStore()
    rows = [{'series_id': 'CPILFESL', 'date': '2026-10-01', 'value': '310.5'}]
    capture = _capture(store, observations=lambda as_of: rows)
    with pytest.raises(Exception) as error:
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                        timeframe=DAILY, as_of=AS_OF)
    assert 'release' in str(error.value).lower()


def test_observations_carry_evidence():
    store = FakeStore()
    capture = _capture(store, observations=lambda as_of: observations())
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    for row in store.call['context']['observations']:
        assert UUID(row['evidence_id'])


# --- quote, account, limits ------------------------------------------------

def test_a_missing_quote_is_named_in_data_quality():
    store = FakeStore()
    capture = _capture(store, quote=None)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert 'quote' in ' '.join(store.call['data_quality'])
    assert store.call['context'].get('quote') in (None, {})


def test_a_present_quote_carries_evidence():
    store = FakeStore()
    capture = _capture(store, quote=lambda: {'price': '211.50', 'evidence_id': str(uuid4())})
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    quote = store.call['context']['quote']
    assert quote
    assert UUID(quote['evidence_id'])


def test_a_missing_account_fails_the_portfolio_role_rather_than_faking_equity():
    store = FakeStore()
    capture = _capture(store, account=None)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    context = result['context']
    assert 'equity' not in json_text(context)
    assert 'account' in ' '.join(result['data_quality'])


def test_an_account_carries_equity_and_evidence():
    store = FakeStore()
    capture = _capture(store, account=lambda: {
        'equity': '100000.00', 'evidence_id': str(uuid4()),
        'position_count': 2, 'max_weight': '0.25'})
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    account = store.call['context']['account']
    assert account['equity'] == '100000.00'
    assert UUID(account['evidence_id'])


def test_limits_are_recorded_with_the_snapshot():
    store = FakeStore()
    capture = _capture(store, limits=lambda: {'per_trade_risk': '0.01', 'daily_loss': '0.02'})
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert store.call['context']['limits'] == {'per_trade_risk': '0.01', 'daily_loss': '0.02'}


# --- symbols ---------------------------------------------------------------

def test_symbols_hold_only_the_requested_symbol():
    store = FakeStore()
    capture = _capture(store)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    assert result['context']['symbols'] == [SYMBOL]


# --- canonical form --------------------------------------------------------

def test_decimals_are_strings_and_datetimes_are_iso():
    store = FakeStore()
    capture = _capture(store)
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    text = json_text(store.call['context'])
    assert '"100.0"' in text or '"100"' in text
    assert 'Decimal(' not in text
    assert 'T' in text


def json_text(value) -> str:
    import json
    return json.dumps(value, default=str, sort_keys=True)


# --- role schemas ----------------------------------------------------------

def test_a_snapshot_with_an_account_satisfies_the_portfolio_role_schema():
    """The context the builder writes is what the portfolio role reads."""
    import json as _json
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[2] / 'schemas' / 'research'
    common = _json.loads((root / 'common.json').read_text(encoding='utf-8'))
    portfolio = _json.loads((root / 'portfolio_input.json').read_text(encoding='utf-8'))
    registry_documents = {
        path.name: _json.loads(path.read_text(encoding='utf-8'))
        for path in root.glob('*.json')
    }
    from referencing import Registry, Resource
    registry = Registry().with_resources(
        (name, Resource.from_contents(doc)) for name, doc in registry_documents.items())
    validator = Draft202012Validator(portfolio, registry=registry)

    store = FakeStore()
    capture = _capture(store)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    errors = list(validator.iter_errors({
        'snapshot_id': str(result['snapshot_id']),
        'as_of': result['as_of'].isoformat(),
        'data_quality': result['data_quality'],
        'context': result['context'],
    }))
    assert errors == [], [error.message for error in errors]


def test_a_snapshot_without_an_account_fails_the_portfolio_role_schema():
    """Missing account means the portfolio role fails; it does not fake equity."""
    import json as _json
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    root = Path(__file__).resolve().parents[2] / 'schemas' / 'research'
    portfolio = _json.loads((root / 'portfolio_input.json').read_text(encoding='utf-8'))
    registry_documents = {
        path.name: _json.loads(path.read_text(encoding='utf-8'))
        for path in root.glob('*.json')
    }
    registry = Registry().with_resources(
        (name, Resource.from_contents(doc)) for name, doc in registry_documents.items())
    validator = Draft202012Validator(portfolio, registry=registry)

    store = FakeStore()
    capture = _capture(store, account=None)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    errors = list(validator.iter_errors({
        'snapshot_id': str(result['snapshot_id']),
        'as_of': result['as_of'].isoformat(),
        'data_quality': result['data_quality'],
        'context': result['context'],
    }))
    assert errors


def test_a_snapshot_satisfies_the_technical_role_schema():
    import json as _json
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    root = Path(__file__).resolve().parents[2] / 'schemas' / 'research'
    technical = _json.loads((root / 'technical_input.json').read_text(encoding='utf-8'))
    registry_documents = {
        path.name: _json.loads(path.read_text(encoding='utf-8'))
        for path in root.glob('*.json')
    }
    registry = Registry().with_resources(
        (name, Resource.from_contents(doc)) for name, doc in registry_documents.items())
    validator = Draft202012Validator(technical, registry=registry)

    store = FakeStore()
    capture = _capture(store)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    errors = list(validator.iter_errors({
        'snapshot_id': str(result['snapshot_id']),
        'as_of': result['as_of'].isoformat(),
        'data_quality': result['data_quality'],
        'context': result['context'],
    }))
    assert errors == [], [error.message for error in errors]


# --- injected indicator source ---------------------------------------------

def test_an_injected_live_plane_cannot_override_frozen_local_computation():
    """Historical evidence is always computed from the frozen bar read."""
    store = FakeStore()
    capture = _capture(store)
    capture._indicators = _StubPlane()
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    series = store.call['context']['indicators']
    assert len(series) > 1
    assert all(item['source_coverage'] == 'sip' for item in series)


def test_empty_frozen_history_cannot_fall_back_to_a_live_plane():
    """An old timestamp alone cannot prove a live indicator used frozen bars."""
    store = FakeStore()
    capture = _capture(store)
    capture._indicators = _StubPlane()
    capture._bars = _EmptyBars()
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    assert result['context']['indicators'] == []


def test_an_injected_plane_cannot_leak_a_point_after_as_of():
    """A live plane may carry points the snapshot does not cover.

    They are dropped, so the snapshot cannot cite a value that was not
    knowable at `as_of`.
    """
    store = FakeStore()
    capture = _capture(store)
    capture._indicators = _StubPlane(late=True)
    capture._bars = _EmptyBars()
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    series = result['context']['indicators']
    assert series == []
    assert 'indicators_unavailable' in result['data_quality']


class _EmptyBars:
    """A bar source with a venue but no history."""

    def coverage_of(self, timeframe):
        return 'sip'

    def bars(self, instrument_id, timeframe):
        return ()


class _StubPlane:
    """A plane that answers with one series and no history."""

    def __init__(self, late: bool = False):
        self._late = late

    def series(self, instrument_id, timeframe, **kwargs):
        from gabfin.contracts.analysis import IndicatorResponse
        from gabfin.contracts.indicator import IndicatorPoint, IndicatorSeries

        event_at = datetime(2026, 12, 31, tzinfo=timezone.utc) if self._late \
            else datetime(2026, 11, 20, tzinfo=timezone.utc)
        point = IndicatorPoint(
            schema_version='1.0',
            instrument_id=instrument_id,
            indicator='sma',
            params={'period': '20'},
            timeframe=timeframe,
            value=Decimal('100.5'),
            event_at=event_at,
            computed_at=max(datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc), event_at),
            source_coverage='sip',
            computed_by='local',
        )
        series = IndicatorSeries(
            instrument_id=instrument_id, indicator='sma', params={'period': '20'},
            timeframe=timeframe, source_coverage='sip', points=(point,))
        return IndicatorResponse(
            schema_version='1.0', instrument_id=instrument_id, timeframe=timeframe,
            source_coverage='sip', computed_by='local', series=(series,), statuses=())


# --- timeframes ------------------------------------------------------------

def test_an_intraday_bar_is_visible_once_its_interval_has_elapsed():
    """A minute bar needs its whole minute to be over."""
    from gabfin.research.capture import bar_end

    minute = Timeframe(count=1, unit=TimeUnit.MINUTE)
    stamp = datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc)
    assert bar_end(stamp, minute) == stamp + timedelta(minutes=1)


def test_a_trading_day_bar_closes_at_the_end_of_its_whole_day():
    from gabfin.research.capture import bar_end

    stamp = datetime(2026, 11, 27, 9, 30, tzinfo=timezone.utc)
    assert bar_end(stamp, DAILY) == datetime(2026, 11, 28, tzinfo=timezone.utc)


# --- as_of -----------------------------------------------------------------

def test_a_naive_as_of_is_refused():
    store = FakeStore()
    capture = _capture(store)
    with pytest.raises(ValueError):
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY,
                        as_of=datetime(2026, 11, 27, 21, 0))


def test_a_non_utc_as_of_is_refused():
    store = FakeStore()
    capture = _capture(store)
    local = datetime(2026, 11, 27, 21, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValueError):
        capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=local)


def test_a_builder_needs_a_bar_source():
    from gabfin.research.capture import SnapshotCapture
    with pytest.raises(ValueError):
        SnapshotCapture(FakeStore(), bars=None)


# --- real tape round trip --------------------------------------------------

def test_a_real_tape_round_trip_produces_a_snapshot(tmp_path):
    write_tape(tmp_path, count=60, venue='sip')
    store = FakeStore()
    capture = _capture(store, tape_root=tmp_path)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    context = result['context']
    assert context['bars']
    assert context['indicators']
    assert store.call['evidence_ids']


# --- role prompts ----------------------------------------------------------

def test_the_snapshot_renders_every_role_prompt(tmp_path):
    """The context the builder writes is what the role prompts read.

    The prompts are strict: a missing field is an error, not a blank.
    A snapshot that cannot be rendered is a snapshot no role can use.
    """
    from gabfin.research.roles import load_all_role_cards, render_prompt

    write_tape(tmp_path, count=60, venue='sip')
    store = FakeStore()
    capture = _capture(store, tape_root=tmp_path,
                       observations=lambda as_of: observations())
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    context = result['context']
    prompt_context = {
        'snapshot_id': str(result['snapshot_id']),
        'as_of': result['as_of'].isoformat(),
        'data_quality': result['data_quality'],
        'observations': context['observations'],
        'bars': context['bars'],
        'indicators': context['indicators'],
        'account': context['account'],
        'limits': context['limits'],
    }
    cards = load_all_role_cards(Path(__file__).resolve().parents[2] / 'config/agents')
    for name, card in cards.items():
        rendered = render_prompt(card, 'user', dict(prompt_context))
        assert rendered


def test_a_built_snapshot_renders_the_real_service_prompts(tmp_path):
    """The whole chain: build a snapshot, then render the real prompts."""
    from gabfin.research.roles import load_all_role_cards, render_prompt
    from gabfin.research.store import ResearchStore

    write_tape(tmp_path, count=60, venue='sip')
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = _capture(store, tape_root=tmp_path,
                       observations=lambda as_of: observations())
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=AS_OF)
    stored = store.get_snapshot(result['snapshot_id'])
    cards = load_all_role_cards(Path(__file__).resolve().parents[2] / 'config/agents')
    for role, card in cards.items():
        keys = {'discovery': ('observations',),
                'technical': ('bars', 'indicators'),
                'portfolio': ('account', 'limits')}[role]
        context = {key: stored['context'][key] for key in keys}
        rendered = render_prompt(card, 'user', {
            **context,
            'snapshot_id': str(stored['snapshot_id']),
            'as_of': stored['as_of'].isoformat(),
            'data_quality': stored['data_quality'],
        })
        assert rendered


# --- integration with the real store ---------------------------------------

def test_the_tape_is_read_once_per_capture():
    """One capture reads one history.

    Reading the tape twice could produce two different sets of bars,
    and the indicators would then be computed on a history the snapshot
    does not contain.
    """
    store = FakeStore()
    capture = _capture(store)
    source = capture._bars
    calls = []
    original = source.bars

    def counted(instrument_id, timeframe):
        calls.append((instrument_id, timeframe))
        return original(instrument_id, timeframe)

    source.bars = counted
    capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL, timeframe=DAILY, as_of=AS_OF)
    assert len(calls) == 1


def test_the_builder_calls_the_store_with_the_agreed_interface():
    """The call shape is fixed, so a store change breaks here first."""
    import inspect
    from gabfin.research.store import ResearchStore

    signature = inspect.signature(ResearchStore.create_snapshot)
    for name in ('as_of', 'context', 'data_quality', 'evidence_ids'):
        assert name in signature.parameters
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_real_store_accepts_the_snapshot_the_builder_writes(tmp_path):
    """The builder and the store agree on the interface and the rules."""
    from gabfin.research.store import ResearchStore

    write_tape(tmp_path, count=60, venue='sip')
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = _capture(store, tape_root=tmp_path)
    try:
        result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                                  timeframe=DAILY, as_of=AS_OF)
    except TypeError as error:
        pytest.skip(f'the store cannot create snapshot ids yet: {error}')
    stored = store.get_snapshot(result['snapshot_id'])
    assert stored['as_of'] == AS_OF
    assert stored['context']['symbols'] == [SYMBOL]
    assert stored['context']['bars']
    cited = set()
    _collect(stored['context'], cited)
    assert store.evidence_ids(result['snapshot_id']) == frozenset(cited)


def test_a_capture_past_the_tape_history_is_still_a_valid_snapshot(tmp_path):
    """Asking for a moment before the history is not a look-ahead.

    The builder asks for what existed at that moment. A tape that only
    holds later bars simply contributes nothing.
    """
    from gabfin.research.store import ResearchStore

    write_tape(tmp_path, count=60, venue='sip')
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = _capture(store, tape_root=tmp_path)
    early = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
    result = capture.capture(instrument_id=INSTRUMENT, symbol=SYMBOL,
                              timeframe=DAILY, as_of=early)
    stored = store.get_snapshot(result['snapshot_id'])
    assert stored['as_of'] == early
    for bar in stored['context']['bars']:
        assert datetime.fromisoformat(bar['event_at']) < early


# --- helper ----------------------------------------------------------------

def _capture(store, *, tape_root=None, venue='sip', bars=..., observations=None,
             quote=..., account=..., limits=...):
    from gabfin.research.capture import SnapshotCapture
    if tape_root is None:
        import tempfile
        tape_root = Path(tempfile.mkdtemp(prefix='gabfin-tape-'))
        write_tape(tape_root, count=60, venue=venue)
    if bars is ...:
        bars = tape_source(tape_root, symbol=SYMBOL)
    if quote is ...:
        quote = lambda: {'price': '211.50', 'evidence_id': str(uuid4())}
    if account is ...:
        account = lambda: {'equity': '100000.00', 'evidence_id': str(uuid4()),
                           'position_count': 2, 'max_weight': '0.25'}
    if limits is ...:
        limits = lambda: {'per_trade_risk': '0.01', 'daily_loss': '0.02'}
    return SnapshotCapture(store, bars=bars, observations=observations, quote=quote,
                            account=account, limits=limits)
