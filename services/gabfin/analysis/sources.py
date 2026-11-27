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

#: The sources that are not tied to a named venue. Massive history is
#: consolidated vendor data with no venue behind it, so a Massive series
#: may not claim one of the known venues: doing so would let a series that
#: was never tied to a venue be read as one, and the indicator plane would
#: label the result with that venue. A Massive series may say `unknown`,
#: or any other label that names no venue.
UNVENUED_SOURCES: frozenset[str] = frozenset({'massive'})


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

        manifest = read_manifest(manifest_path(self._root, self._series(timeframe)))
        if self._source is not None and manifest.series.source != self._source:
            raise ValueError('Tape source does not match requested source')
        return manifest

    def _check_coverage(self, coverage: str):
        """Refuse a named venue on a series that has none.

        A Massive series has no venue behind it. If its manifest says `sip`,
        the series would be read as a named-venue series and the indicator
        plane would label the result with that venue, which is exactly the
        claim Massive data cannot support. A label that names no venue,
        `unknown` included, is honest and is allowed.
        """
        if self._source in UNVENUED_SOURCES and coverage in KNOWN_COVERAGES:
            raise ValueError(
                f'Tape source {self._source} may not claim the venue {coverage}')

    def _refuse_inconsistent_partitions(self, manifest, timeframe: Timeframe):
        """Refuse a tape whose files and index disagree.

        The manifest is the index of the tape. If the files on disk and the
        index name different partitions, the tape has two stories about
        what it holds. Reading around the difference would silently drop a
        month of history, and a later import could re-bless the values
        that were never committed to the index. The reader refuses instead.
        """
        from gabfin.storage.tape import manifest_partition_paths, stored_partition_paths

        on_disk = stored_partition_paths(self._root, self._series(timeframe))
        if on_disk != manifest_partition_paths(manifest):
            raise ValueError('Tape partitions do not match the manifest')

    def bars(self, instrument_id: UUID, timeframe: Timeframe) -> Sequence[PriceBar]:
        from gabfin.storage.tape import read_rows

        manifest = self._manifest(timeframe)
        from hashlib import sha256
        for partition in manifest.partitions:
            if sha256((self._root / partition.path).read_bytes()).hexdigest() != partition.sha256:
                raise ValueError('Tape partition checksum mismatch')
        self._refuse_inconsistent_partitions(manifest, timeframe)
        self._check_coverage(manifest.series.venue_coverage)
        rows = read_rows(self._root, self._series(timeframe), manifest=manifest)
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
            self._check_coverage(manifest.series.venue_coverage)
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
