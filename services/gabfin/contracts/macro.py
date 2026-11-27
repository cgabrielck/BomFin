"""Macro observations and their release provenance.

A macro series is not a time series of facts about the world. It is a
series of numbers that were published on a date, about a period, and
that may be revised afterwards. A backtest that reads the current value
of a series for a past date is using data that did not exist at the
time, and will look better in the backtest than it can ever live.

Every observation therefore records when it was released, not only the
period it describes.
"""
from datetime import date, datetime, timezone
from typing import Literal, Self

from pydantic import Field, model_validator

from gabfin.contracts.common import (
    ContractModel,
    ExactDecimal,
    OpaqueKey,
    UtcTimestamp,
    VersionedContract,
)

#: How often a series is published.
MacroFrequency = Literal[
    'daily',
    'weekly',
    'monthly',
    'quarterly',
    'annual',
]

#: The family a series belongs to, for the UI grouping.
MacroCategory = Literal[
    'rates',
    'inflation',
    'employment',
    'risk',
    'growth',
    'other',
]


class MacroSeries(VersionedContract):
    """The definition of a macro series, not its observations."""

    series_id: OpaqueKey
    title: OpaqueKey
    category: MacroCategory
    frequency: MacroFrequency
    units: OpaqueKey
    seasonal_adjustment: OpaqueKey | None = None


class MacroPoint(VersionedContract):
    """One published observation of a macro series."""

    series_id: OpaqueKey
    observation_date: date
    release_date: date
    value: ExactDecimal | None
    units: OpaqueKey
    frequency: MacroFrequency
    #: The vintage the observation came from. FRED serves revised
    #: history, so two observations of the same date can differ; the
    #: vintage says which one this is.
    vintage: UtcTimestamp | None = None

    @model_validator(mode='after')
    def _released_after_it_observed(self) -> Self:
        if self.release_date < self.observation_date:
            raise ValueError(
                'A macro observation cannot be released before the period it '
                'describes'
            )
        return self


class MacroRelease(ContractModel):
    """When a series was next published, and what it said.

    A macro dashboard that shows a number without its release date will
    show a stale number with no indication of it, which is worse than
    showing nothing.
    """

    series_id: OpaqueKey
    release_date: date
    period: date
    value: ExactDecimal | None
    units: OpaqueKey
    frequency: MacroFrequency
    fetched_at: UtcTimestamp

    @model_validator(mode='after')
    def _fetched_after_release(self) -> Self:
        fetched = self.fetched_at
        if isinstance(fetched, datetime) and fetched.tzinfo is None:
            raise ValueError('The fetch time needs an aware timestamp')
        return self


class MacroSnapshot(ContractModel):
    """The latest observation of several series at one instant."""

    observed_at: UtcTimestamp
    points: tuple[MacroPoint, ...] = Field(max_length=1000)

    def by_series(self) -> dict[str, MacroPoint]:
        return {point.series_id: point for point in self.points}


def utc_now() -> datetime:
    """The current instant, as an aware UTC timestamp."""
    return datetime.now(timezone.utc)
