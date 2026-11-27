"""Assembling the analysis planes from what this build actually has.

The planes take their sources by injection. This module is the one
place that decides which source is which, so the decision is visible
once instead of scattered across callers.

Two rules:

- A source that is not configured produces a plane that says it cannot
  answer, not a plane that answers with nothing. An absent FRED key
  must not look like a macro series with no observations.
- A feed's capabilities are reported only when they were measured. A
  capability snapshot that was never probed is absent from the list.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from uuid import UUID

from gabfin.analysis.plane import CapabilityPlane, IndicatorPlane, MacroPlane
from gabfin.analysis.sources import FredMacroSource, MeasuredCapabilities, TapeBarSource
from gabfin.contracts.indicator import SourceCoverage
from gabfin.contracts.market import Timeframe
from gabfin.contracts.subscriptions import FeedCapabilities


class InstrumentResolver:
    """The symbol a canonical instrument is stored under in the tape.

    The tape is keyed by the symbol the provider names, not by the
    canonical uuid. An instrument the resolver does not know raises,
    because guessing a symbol would read a different series.
    """

    def __init__(self, catalog, *, namespace: str = 'futu'):
        self._catalog = catalog
        self._namespace = namespace

    def symbol_of(self, instrument_id: UUID) -> str:
        instrument = self._catalog.get(instrument_id)
        if instrument is None:
            raise KeyError('Unknown instrument')
        symbol = instrument.vendor_symbols.get(self._namespace)
        if symbol is None:
            raise KeyError('The instrument has no symbol in this namespace')
        return symbol


class TapeHistory:
    """Stored bars for whichever instrument the caller names.

    The tape is keyed by symbol, so the resolver decides which series an
    instrument id means. The coverage is read from the manifest of that
    series, because the venue a series was written with is a property of
    the stored data, not of the caller.
    """

    def __init__(self, root: Path, resolver: InstrumentResolver, *, namespace: str = 'futu'):
        self._root = Path(root)
        self._resolver = resolver
        self._namespace = namespace

    def _source(self, instrument_id: UUID, timeframe: Timeframe) -> TapeBarSource:
        return TapeBarSource(
            self._root,
            symbol=self._resolver.symbol_of(instrument_id),
            source=self._namespace,
        )

    def bars(self, instrument_id: UUID, timeframe: Timeframe):
        return self._source(instrument_id, timeframe).bars(instrument_id, timeframe)

    def coverage(self, instrument_id: UUID, timeframe: Timeframe) -> SourceCoverage:
        return self._source(instrument_id, timeframe).coverage_of(timeframe)


def indicator_plane(root: Path, resolver: InstrumentResolver, *,
                    namespace: str = 'futu') -> IndicatorPlane:
    """The indicator plane over the stored tape."""
    history = TapeHistory(root, resolver, namespace=namespace)
    return IndicatorPlane(
        history,
        coverage_resolver=lambda instrument_id, timeframe: history.coverage(
            instrument_id, timeframe),
    )


def macro_plane(client, *, clock: Callable[[], datetime] | None = None) -> MacroPlane:
    """The macro plane over FRED.

    A missing key is not an empty macro series. The client raises, the
    plane reports that it cannot answer, and the route answers 503.
    """
    return MacroPlane(FredMacroSource(client, clock=clock), clock=clock)


def capability_plane(probes: Callable[[], Iterable[FeedCapabilities]]) -> CapabilityPlane:
    """The capability plane over the feeds that were measured."""
    return CapabilityPlane(MeasuredCapabilities(probes))
