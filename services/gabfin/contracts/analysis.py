"""Read-only analysis responses for the browser.

These are the shapes the desk UI reads. They exist so that the
browser's view of an indicator, a macro observation, or a feed's
capabilities is a contract rather than a guess.

Three rules shape every response here:

- A decimal is a string. The wire carries exact decimals, and the
  browser must not round them into a float before it decides what to
  show.
- A missing value is missing. A series with no observation is an empty
  series with a stated reason, never a zero.
- Provenance travels with the value. An indicator says what it was
  computed from; a macro observation says when it was released; a feed
  says whether its price may be used to enter.
"""
from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from gabfin.contracts.common import ContractModel, OpaqueKey, UtcTimestamp, VersionedContract
from gabfin.contracts.indicator import (
    ComputedBy,
    IndicatorName,
    IndicatorSeries,
    IndicatorStatus,
    SourceCoverage,
)
from gabfin.contracts.macro import MacroPoint
from gabfin.contracts.market import Timeframe
from gabfin.contracts.subscriptions import FeedCapabilities


class IndicatorResponse(VersionedContract):
    """The indicator series of one instrument and timeframe."""

    instrument_id: UUID
    timeframe: Timeframe
    source_coverage: SourceCoverage
    computed_by: ComputedBy
    series: tuple[IndicatorSeries, ...] = Field(max_length=64)
    #: Why a requested indicator has no value. Present so that a chart
    #: can say "not enough history" instead of drawing nothing.
    statuses: tuple[IndicatorStatus, ...] = Field(default=(), max_length=64)

    @model_validator(mode='after')
    def consistent_series(self) -> Self:
        for item in self.series:
            if item.instrument_id != self.instrument_id:
                raise ValueError('An indicator response cannot mix instruments')
            if item.timeframe != self.timeframe:
                raise ValueError('An indicator response cannot mix timeframes')
            if item.source_coverage != self.source_coverage:
                raise ValueError('An indicator response cannot mix source coverage')
        return self


class MacroResponse(VersionedContract):
    """The macro observations visible at one instant.

    `as_of` is the date the caller asked about. Only observations that
    had been released by then are present, so a caller cannot read a
    number that did not exist yet.
    """

    observed_at: UtcTimestamp
    as_of: date
    points: tuple[MacroPoint, ...] = Field(max_length=1000)

    @model_validator(mode='after')
    def released_before_as_of(self) -> Self:
        for point in self.points:
            if point.release_date > self.as_of:
                raise ValueError('A macro observation was released after the requested date')
        return self


class CapabilitiesResponse(VersionedContract):
    """What each registered feed can do, as measured."""

    checked_at: UtcTimestamp
    sources: tuple[FeedCapabilities, ...] = Field(max_length=32)

    @model_validator(mode='after')
    def distinct_sources(self) -> Self:
        names = [source.source for source in self.sources]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate feed capability source')
        return self


class AnalysisUnavailable(ContractModel):
    """Why an analysis plane cannot answer right now."""

    reason: OpaqueKey
    detail: OpaqueKey | None = None
