"""Build one frozen research snapshot out of local sources.

A research conclusion may only cite a snapshot, so everything the
conclusion sees has to exist before the moment it was taken. This
module is the boundary that guarantees that. It reads the local tape,
the local macro rows, the local account facts, and it hands the store
one immutable context.

The rules are deliberately conservative:

- **Bars come from local storage.** The tape is the only history with a
  named venue. A series that was never written is refused, because the
  caller asked about history that does not exist. A series written
  without a venue the contract accepts is still read: research may look
  at history it cannot name, and it says so in the snapshot's coverage.
  What it may not do is pretend the bars were SIP.
- **A bar is only visible once it has closed.** A bar stamped after
  `as_of` is not in the snapshot. A trading-day bar needs its whole
  UTC day to be over, because the day it names is the day the market
  was still trading.
- **Indicators are computed from the frozen bars.** The plane is
  rebuilt over exactly the bars that made it into the snapshot, and
  every point is stamped with `as_of` rather than the wall clock. An
  indicator stamped "now" on a historical snapshot reads as a
  look-ahead even when the values are right.
- **A macro observation must say when it was released.** A row with no
  release date is refused, and one released after `as_of` is left out.
  The series date describes the period, not the publication, so it is
  never used in its place. A raw FRED row carries a vintage rather than
  a release date, so the conversion happens at the seam, in the
  `fred_observations` adapter, through the canonical conversion in
  `fred/fetch.py`. The builder never borrows a date to make a row fit.
- **The market snapshot is the frozen quote.** A role that asks what the
  market looked like gets the quote's own evidence, so the two can never
  disagree about what was seen. Without a quote there is no market
  snapshot, and the snapshot says so in its data quality.
- **Missing facts stay missing.** A snapshot with no quote says so in
  its data quality; a snapshot with no account does not invent an
  equity balance, and the portfolio role fails on it.

Nothing here reaches the network or reads the environment. The builder
is handed its sources and reads only what it was given.
"""
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from gabfin.analysis.plane import AnalysisUnavailable, IndicatorPlane
from gabfin.contracts.market import Timeframe, TimeUnit
from gabfin.indicators.inputs import PriceBar

#: The coverages the indicator contract accepts. A tape series written
#: with anything else yields `unknown`, and the indicator plane then
#: refuses to compute rather than labelling the result with a wrong
#: venue.
KNOWN_COVERAGES: frozenset[str] = frozenset({
    'iex', 'sip', 'futu_nasdaq_totalview', 'futu_arca',
})

#: How long one unit of each timeframe lasts, when the length of the
#: unit matters for deciding whether a bar has closed.
_UNIT_SECONDS = {
    TimeUnit.SECOND: 1,
    TimeUnit.MINUTE: 60,
    TimeUnit.HOUR: 3600,
    TimeUnit.TRADING_DAY: 86400,
    TimeUnit.WEEK: 604800,
    TimeUnit.MONTH: 2592000,
    TimeUnit.YEAR: 31536000,
}


class CaptureError(ValueError):
    """The requested snapshot cannot be built from the sources given.

    The message names the reason and never the payload.
    """


def _require_utc(as_of: Any) -> datetime:
    """An aware moment expressed in UTC.

    A naive timestamp is refused because it means different things in
    different places, and a timestamp with a non-zero offset is
    refused because it is not the UTC instant it claims to be.
    """
    if not isinstance(as_of, datetime):
        raise CaptureError('as_of must be a datetime')
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise CaptureError('as_of must be an aware UTC datetime')
    if as_of.utcoffset() != timedelta(0):
        raise CaptureError('as_of must be expressed in UTC')
    return as_of.astimezone(timezone.utc)


def bar_end(event_at: datetime, timeframe: Timeframe) -> datetime:
    """The moment a bar closes.

    A trading-day bar closes at the end of its whole UTC day. The day a
    daily bar names is the day the session ran, so treating midnight as
    the close would let a forming bar into a snapshot.
    """
    moment = event_at.astimezone(timezone.utc)
    if timeframe.unit is TimeUnit.TRADING_DAY:
        if timeframe.count != 1:
            raise CaptureError('Multi-day finalization requires a verified trading calendar')
        return moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    if timeframe.unit in (TimeUnit.MONTH, TimeUnit.YEAR):
        raise CaptureError('Calendar timeframe finalization is not available')
    seconds = _UNIT_SECONDS[timeframe.unit] * timeframe.count
    return moment + timedelta(seconds=seconds)


def canonical(value: Any) -> Any:
    """One JSON-like form for a value.

    A decimal travels as its exact string, a datetime as its ISO
    instant, and a UUID as its text. Nothing is rounded on the way, and
    nothing is left as a Python object the store cannot serialise.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        moment = value.astimezone(timezone.utc) if value.tzinfo is not None else value
        return moment.isoformat().replace('+00:00', 'Z')
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise CaptureError('Snapshot content must be JSON serialisable')


def _evidence() -> str:
    """A fresh evidence id for one fact."""
    return str(uuid4())


def _release_date_of(row: Mapping[str, Any]) -> str | None:
    """The date an observation was published, or None if it has none.

    Only an explicit `release_date` is a release date. FRED's
    `realtime_start` and `realtime_end` are vintages: they say the
    period a value was published for, not the day it was published. A
    January number published in March carries a March vintage, and
    reading that vintage as a release date would make the March number
    look knowable in January. The series date describes the period
    covered, which is a third thing again.

    So a row with no explicit release date has no release date, and the
    builder refuses it rather than borrowing one.
    """
    stamp = row.get('release_date')
    if stamp in (None, ''):
        return None
    try:
        return date.fromisoformat(str(stamp).strip()).isoformat()
    except ValueError:
        raise CaptureError('Invalid explicit release_date') from None


def _observation_date_of(row: Mapping[str, Any]) -> str | None:
    """The period an observation describes."""
    stamp = row.get('date') or row.get('observation_date')
    if stamp in (None, ''):
        return None
    return str(stamp).strip()[:10]


def _observation_text(record: Mapping[str, Any]) -> str:
    """One readable line for an observation.

    The discovery role reads observations as text, so a row that does
    not carry its own text gets one built from the facts it does
    carry. Nothing is invented: a row without a value says so.
    """
    series = record.get('series_id') or record.get('series')
    period = record.get('observation_date') or record.get('date')
    value = record.get('value')
    release = record.get('release_date')
    parts = []
    if series:
        parts.append(str(series))
    if period:
        parts.append(f'period {period}')
    if value in (None, ''):
        parts.append('no published value')
    else:
        parts.append(f'value {value}')
    if release:
        parts.append(f'released {release}')
    return ', '.join(parts)


def fred_observations(source: Any, series_id: str) -> Callable[[datetime], list[dict]]:
    """A read-only observation source over one FRED series.

    The source hands back the raw rows exactly as FRED wrote them, and
    those rows carry a vintage rather than a release date. A vintage
    says which revision of a value was served; it is not the day the
    value was published. The builder refuses an observation without an
    explicit release date, so the conversion has to happen here, at the
    seam, and it happens through the canonical conversion in
    `fred/fetch.py` rather than through a guess made inside the
    builder.

    The returned callable takes the moment of the snapshot and gives
    back the rows that were already released by then. A row released
    afterwards is left out, not clamped, and a row with no release
    stamp is refused rather than given a borrowed one. The builder
    receives rows that already carry an explicit `release_date`, and it
    never has to reinterpret them.

    Nothing here reaches the network: the source is handed in, and the
    builder is handed the callable.
    """
    def read(as_of: datetime) -> list[dict]:
        from gabfin.providers.fred.fetch import as_of as released_by
        from gabfin.providers.fred.fetch import to_point

        moment = _require_utc(as_of)
        raw = source.observations(series_id)
        points = []
        for row in raw:
            point = to_point(row, series_id=series_id)
            if point is None:
                # FRED published the period without a number. That is
                # information, not a value, and it carries no fact to
                # freeze.
                continue
            points.append(point)
        known = released_by(tuple(points), moment.date())
        return [
            {
                'series_id': point.series_id,
                'observation_date': point.observation_date.isoformat(),
                'release_date': point.release_date.isoformat(),
                'value': str(point.value) if point.value is not None else None,
                'units': point.units,
                'frequency': point.frequency,
            }
            for point in known
        ]

    return read


class SnapshotCapture:
    """Builds one frozen snapshot from local sources.

    The sources are injected, so the builder never reaches the network
    and never reads the environment. A source that is not configured is
    absent from the snapshot and named in its data quality, which is
    different from a source that answered with nothing.

    The `indicators` parameter is accepted to keep the declared
    interface, but it is never read. A historical snapshot is built
    from the frozen bar read, and a live plane is a moving object that
    may carry bars outside the cutoff, so reading it would put
    look-ahead into the evidence.
    """

    def __init__(self, store, *, bars, indicators=None, observations=None,
                 quote=None, account=None, limits=None):
        if bars is None:
            raise CaptureError('A snapshot needs a bar source')
        self._store = store
        self._bars = bars
        self._indicators = indicators
        self._observations = observations
        self._quote = quote
        self._account = account
        self._limits = limits

    # --- public -----------------------------------------------------------

    def capture(self, *, instrument_id: UUID, symbol: str, timeframe: Timeframe,
                as_of: datetime) -> dict:
        """Build and register one snapshot, and return it.

        The returned dictionary is the common research input shape: the
        snapshot id, the moment it was taken, its data quality, and the
        context the roles read.
        """
        moment = _require_utc(as_of)
        if not isinstance(instrument_id, UUID):
            raise CaptureError('instrument_id must be a UUID')
        if not isinstance(symbol, str) or not symbol.strip():
            raise CaptureError('symbol must be a nonempty string')
        if not isinstance(timeframe, Timeframe):
            raise CaptureError('timeframe must be a Timeframe')

        quality: list[str] = []
        context: dict[str, Any] = {'symbols': [symbol]}

        rows = self._read_rows(instrument_id, timeframe)
        coverage = self._coverage_of(timeframe)
        context['bars'] = self._visible_bars(rows, symbol, timeframe, moment, coverage)
        context['source_coverage'] = coverage
        if coverage == 'unknown':
            quality.append('source_coverage_unknown')

        indicators = self._read_indicators(instrument_id, timeframe, moment, coverage, rows)
        context['indicators'] = indicators
        if not indicators:
            quality.append('indicators_unavailable')

        observations, observation_quality = self._read_observations(moment)
        context['observations'] = observations
        quality.extend(observation_quality)

        quote, quote_quality = self._read_quote()
        context['quote'] = quote
        quality.extend(quote_quality)

        # The market snapshot is the frozen quote, not a second reading
        # of the market. A role that asks what the market looked like
        # gets the same evidence the quote carries, so the two can
        # never disagree. Without a quote there is no market snapshot,
        # and the snapshot says so rather than leaving the field empty.
        context['massive_snapshot'] = quote
        if quote is None:
            quality.append('massive_snapshot_unavailable')

        account, account_quality = self._read_account()
        context['account'] = account
        quality.extend(account_quality)

        limits = self._read_limits()
        context['limits'] = limits
        if limits is None:
            quality.append('limits_unavailable')

        payload = canonical(context)
        evidence = _collect_evidence(payload)
        snapshot_id = self._store.create_snapshot(
            as_of=moment,
            context=payload,
            data_quality=sorted(set(quality)),
            evidence_ids=frozenset(evidence),
        )
        return {
            'snapshot_id': snapshot_id,
            'as_of': moment,
            'data_quality': sorted(set(quality)),
            'context': payload,
        }

    # --- bars -------------------------------------------------------------

    def _coverage_of(self, timeframe: Timeframe) -> str:
        """The venue coverage the stored series was written with.

        A source that cannot say yields `unknown`. A source that is
        missing entirely yields `unknown` as well, because a missing
        series and an unnamed series are equally unusable as evidence.
        """
        resolver = getattr(self._bars, 'coverage_of', None)
        if resolver is None:
            return 'unknown'
        try:
            coverage = resolver(timeframe)
        except (FileNotFoundError, ValueError, KeyError):
            return 'unknown'
        return coverage if coverage in KNOWN_COVERAGES else 'unknown'

    def _read_rows(self, instrument_id: UUID, timeframe: Timeframe) -> tuple[Any, ...]:
        """The stored bars for this instrument and timeframe.

        A series that was never written is an error: the caller asked
        about history that does not exist, and an empty series would
        look like a market with no bars.
        """
        try:
            return tuple(self._bars.bars(instrument_id, timeframe))
        except FileNotFoundError as exc:
            raise CaptureError(
                'The bar source has no stored series for this instrument'
            ) from exc
        except (ValueError, KeyError) as exc:
            raise CaptureError('The bar source could not be read') from exc

    def _visible_bars(self, rows: Sequence[Any], symbol: str, timeframe: Timeframe,
                      as_of: datetime, coverage: str) -> list[dict]:
        """The bars that had already closed at `as_of`.

        A bar is visible only when its close is at or before `as_of`.
        The coverage is read from the stored series, because the venue
        a series was written with is a property of the data, not of the
        caller. Every bar carries the timeframe and the coverage it was
        read under, so a reader never has to guess which series a bar
        came from.
        """
        visible: list[dict] = []
        for row in rows:
            event_at = getattr(row, 'event_at', None)
            if not isinstance(event_at, datetime):
                raise CaptureError('A bar needs an aware timestamp')
            if event_at.tzinfo is None:
                raise CaptureError('A bar needs an aware timestamp')
            if bar_end(event_at, timeframe) > as_of:
                continue
            visible.append({
                'evidence_id': _evidence(),
                'symbol': symbol,
                'timeframe': timeframe.model_dump(mode='json'),
                'event_at': event_at,
                'open': getattr(row, 'open', None),
                'high': getattr(row, 'high', None),
                'low': getattr(row, 'low', None),
                'close': getattr(row, 'close', None),
                'volume': getattr(row, 'volume', None),
                'coverage': coverage,
            })
        visible.sort(key=lambda bar: bar['event_at'])
        return canonical(visible)

    # --- indicators -------------------------------------------------------

    def _read_indicators(self, instrument_id: UUID, timeframe: Timeframe,
                         as_of: datetime, coverage: str,
                         rows: Sequence[Any]) -> list[dict]:
        """The indicators computed from the frozen bars.

        The plane is rebuilt over exactly the bars that made it into
        the snapshot, so an indicator cannot see a bar the snapshot
        does not contain. Only a known venue counts: an indicator
        without a venue is not comparable with anything, and is
        reported as unavailable rather than computed under a guess.
        """
        if coverage == 'unknown':
            return []
        # Indicator values always come from the frozen local rebuild:
        # it is computed from exactly the bars the snapshot contains,
        # with the clock pinned to `as_of`. An injected plane is a live
        # object and may carry bars outside this cutoff, so it is never
        # read for a historical snapshot. The parameter stays in the
        # constructor because the interface declares it, and because a
        # future caller may supply a plane that is itself frozen.
        return self._local_indicators(instrument_id, timeframe, as_of, coverage, rows)

    def _local_indicators(self, instrument_id: UUID, timeframe: Timeframe,
                          as_of: datetime, coverage: str,
                          rows: Sequence[Any]) -> list[dict]:
        """Rebuild the indicator plane over the frozen bars."""
        visible = tuple(
            bar for bar in rows
            if isinstance(getattr(bar, 'event_at', None), datetime)
            and bar.event_at.tzinfo is not None
            and bar_end(bar.event_at, timeframe) <= as_of
        )
        if not visible:
            return []
        plane = IndicatorPlane(
            _FrozenBars(visible),
            source_coverage=coverage,
            clock=lambda: as_of,
        )
        try:
            response = plane.series(instrument_id, timeframe)
        except AnalysisUnavailable:
            return []
        return self._indicator_records(response, as_of)

    @staticmethod
    def _indicator_records(response, as_of: datetime) -> list[dict]:
        """The indicator series as records, stamped no later than `as_of`.

        The engine stamps a point with the moment it was computed, which
        is the wall clock. On a historical snapshot that moment reads as
        a look-ahead: the value claims to have been computed at a time
        the snapshot does not cover, and a wall clock is not
        reproducible either. The stamp is therefore pinned to `as_of`,
        the moment the snapshot was taken, which is both bounded and
        the same on every run.
        """
        records: list[dict] = []
        for series in getattr(response, 'series', ()) or ():
            points = []
            latest = None
            for point in series.points:
                event_at = getattr(point, 'event_at', None)
                if not isinstance(event_at, datetime) or event_at > as_of:
                    continue
                points.append({
                    'event_at': event_at,
                    'computed_at': as_of,
                    'value': point.value,
                })
                latest = point.value
            if not points:
                continue
            records.append({
                'evidence_id': _evidence(),
                'name': series.indicator,
                'value': latest,
                'indicator': series.indicator,
                'params': dict(series.params),
                'timeframe': series.timeframe.model_dump(mode='json'),
                'source_coverage': series.source_coverage,
                'points': points,
            })
        records.sort(key=lambda record: record['name'])
        return canonical(records)

    # --- observations -----------------------------------------------------

    def _read_observations(self, as_of: datetime) -> tuple[list[dict], list[str]]:
        """The macro observations that had been released by `as_of`.

        A row without a release date is refused. Defaulting it to the
        series date would turn a look-ahead bug into a silent one, so
        the builder stops instead.
        """
        if self._observations is None:
            return [], ['observations_unavailable']
        rows = self._observations(as_of)
        if rows is None:
            return [], ['observations_unavailable']
        visible: list[dict] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise CaptureError('An observation must be a mapping')
            release = _release_date_of(row)
            if release is None:
                raise CaptureError(
                    'An observation has no release date; a macro point without '
                    'one cannot be used in a backtest'
                )
            if release > as_of.date().isoformat():
                continue
            record = {str(key): item for key, item in row.items()}
            record['release_date'] = release
            observation_date = _observation_date_of(row)
            if observation_date is not None:
                record['observation_date'] = observation_date
            record.setdefault('text', _observation_text(record))
            record['evidence_id'] = _evidence()
            visible.append(record)
        visible.sort(key=lambda record: (record.get('release_date', ''),
                                         record.get('observation_date', '')))
        return canonical(visible), []

    # --- quote, account, limits -------------------------------------------

    def _read_quote(self) -> tuple[dict | None, list[str]]:
        """The quote at capture time, or an honest absence."""
        if self._quote is None:
            return None, ['quote_unavailable']
        try:
            quote = self._quote()
        except Exception as exc:  # noqa: BLE001 - a source failure is a fact
            raise CaptureError('The quote source could not be read') from exc
        if not quote:
            return None, ['quote_unavailable']
        if not isinstance(quote, Mapping):
            raise CaptureError('A quote must be a mapping')
        record = {str(key): item for key, item in quote.items()}
        record.setdefault('evidence_id', _evidence())
        return canonical(record), []

    def _read_account(self) -> tuple[dict | None, list[str]]:
        """The account at capture time, or an honest absence.

        An account with no equity balance is not an account. The
        portfolio role reads equity, so a snapshot without one must say
        so rather than carry a balance nobody measured.
        """
        if self._account is None:
            return None, ['account_unavailable']
        try:
            account = self._account()
        except Exception as exc:  # noqa: BLE001 - a source failure is a fact
            raise CaptureError('The account source could not be read') from exc
        if not account:
            return None, ['account_unavailable']
        if not isinstance(account, Mapping):
            raise CaptureError('An account must be a mapping')
        record = {str(key): item for key, item in account.items()}
        if record.get('equity') in (None, ''):
            raise CaptureError(
                'An account without an equity balance cannot be read by the '
                'portfolio role'
            )
        record.setdefault('evidence_id', _evidence())
        return canonical(record), []

    def _read_limits(self) -> dict | None:
        """The risk limits at capture time."""
        if self._limits is None:
            return None
        try:
            limits = self._limits()
        except Exception as exc:  # noqa: BLE001 - a source failure is a fact
            raise CaptureError('The limits source could not be read') from exc
        if not limits:
            return None
        if not isinstance(limits, Mapping):
            raise CaptureError('Risk limits must be a mapping')
        return canonical({str(key): item for key, item in limits.items()})

class _FrozenBars:
    """A bar source that holds exactly the bars a snapshot contains."""

    def __init__(self, bars: Sequence[PriceBar]):
        self._bars = tuple(bars)

    def bars(self, instrument_id: UUID, timeframe: Timeframe) -> Sequence[PriceBar]:
        return self._bars


def _collect_evidence(node: Any) -> set[str]:
    """Every `evidence_id` value anywhere in a context tree.

    The evidence a snapshot has is the evidence its context mentions.
    Nothing else counts, and nothing is added from outside.
    """
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == 'evidence_id' and isinstance(value, str):
                found.add(value)
            else:
                found |= _collect_evidence(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            found |= _collect_evidence(item)
    return found
