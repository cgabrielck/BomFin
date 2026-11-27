"""The concrete sources the analysis planes read from.

A plane describes what it needs; this module supplies what this build
actually has. Three sources, three honesty rules:

- The bar source reads the tape and says which venue the history came
  from. It never guesses a coverage it did not read.
- The macro source reads FRED and keeps its release dates. It never
  invents a release date for an observation that lacks one.
- The capability source reports the feeds that were actually probed. It
  never reports a feed it did not measure.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence
from uuid import UUID

from gabfin.analysis.plane import BarSource, MacroSource
from gabfin.contracts.indicator import SourceCoverage
from gabfin.contracts.market import Timeframe
from gabfin.contracts.subscriptions import FeedCapabilities
from gabfin.indicators.inputs import PriceBar

#: The coverages the indicator contract accepts. A tape series written
#: with anything else cannot be used to compute an indicator, because an
#: indicator that does not name its venue is not comparable with anything.
KNOWN_COVERAGES: frozenset[str] = frozenset({
    'iex', 'sip', 'futu_nasdaq_totalview', 'futu_arca',
})


class TapeBarSource(BarSource):
    """Stored bars for one instrument, read from the tape.

    The tape is the only history this build has that is tied to a named
    venue, so the coverage reported with a series is the coverage the
    manifest recorded at write time. A series that was never written
    raises, and the caller answers 404 rather than drawing an empty
    chart that looks like a market with no history.
    """

    def __init__(self, root: Path, *, symbol: str, source: str | None = None):
        self._root = Path(root)
        self._symbol = symbol
        self._source = source

    def _series(self, timeframe: Timeframe):
        from gabfin.storage.tape import new_series

        return new_series(
            self._symbol,
            {'count': timeframe.count, 'unit': timeframe.unit.value},
            source=self._source or 'unknown',
            venue_coverage='unknown',
            adjustment='unadjusted',
            retention='rolling_2y',
        )

    def _manifest(self, timeframe: Timeframe):
        from gabfin.storage.manifest import read_manifest
        from gabfin.storage.tape import manifest_path

        return read_manifest(manifest_path(self._root, self._series(timeframe)))

    def bars(self, instrument_id: UUID, timeframe: Timeframe) -> Sequence[PriceBar]:
        from gabfin.storage.tape import read_rows

        rows = read_rows(self._root, self._series(timeframe))
        return tuple(
            PriceBar(
                event_at=row['event_at'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row.get('volume'),
            )
            for row in rows
        )

    def coverage_of(self, timeframe: Timeframe) -> SourceCoverage:
        """The venue coverage the stored series was written with.

        A series written with a coverage the contract does not accept
        yields `unknown`, and the indicator plane then refuses to
        compute rather than labelling the result with a wrong venue.
        """
        try:
            manifest = self._manifest(timeframe)
        except (FileNotFoundError, ValueError):
            return 'unknown'
        recorded = manifest.series.venue_coverage
        return recorded if recorded in KNOWN_COVERAGES else 'unknown'


class FredMacroSource(MacroSource):
    """FRED observations, with the release date left exactly as FRED said."""

    def __init__(self, client, *, clock: Callable[[], datetime] | None = None):
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def observations(self, series_id: str) -> list[dict]:
        return list(self._client.observations(series_id))


class MeasuredCapabilities:
    """The feeds this build measured, and nothing else.

    The callable returns the current capability snapshots. A feed that
    was never probed is absent, which is honest: "we do not know" and
    "we know it is fine" must not look the same.
    """

    def __init__(self, probes: Callable[[], Iterable[FeedCapabilities]]):
        self._probes = probes

    def __call__(self) -> tuple[FeedCapabilities, ...]:
        return tuple(self._probes())
