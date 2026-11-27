"""Tape-plane declarations: stored history and its index, not a market event.

The tape is append-only derived history. A manifest indexes a tape series;
it is never the authority for what the tape contains, and a tape directory
can be deleted and rebuilt from the provider.
"""
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from gabfin.contracts.common import (
    ContractModel,
    OpaqueKey,
    UtcTimestamp,
    VersionedContract,
)
from gabfin.contracts.market import AssetClass, NonNegativeCounter, Timeframe

Retention = Literal['full_history', 'rolling_2y']


class TapeSeries(VersionedContract):
    """Identity and retention of one stored series; not a data payload."""

    series_id: UUID
    asset_class: AssetClass
    symbol: OpaqueKey
    timeframe: Timeframe
    source: OpaqueKey
    venue_coverage: OpaqueKey
    adjustment: OpaqueKey
    retention: Retention
    coverage_start: UtcTimestamp | None
    coverage_end: UtcTimestamp | None
    row_count: NonNegativeCounter
    complete: bool

    @model_validator(mode='after')
    def ordered_coverage(self) -> Self:
        if (
            self.coverage_start is not None
            and self.coverage_end is not None
            and self.coverage_start > self.coverage_end
        ):
            raise ValueError('Tape coverage must not end before it starts')
        return self


class TapePartition(ContractModel):
    """One stored file; the checksum binds a dataset to exact stored bytes."""

    path: OpaqueKey
    rows: NonNegativeCounter
    min_event_at: UtcTimestamp | None
    max_event_at: UtcTimestamp | None
    sha256: OpaqueKey

    @model_validator(mode='after')
    def ordered_bounds(self) -> Self:
        if (
            self.min_event_at is not None
            and self.max_event_at is not None
            and self.min_event_at > self.max_event_at
        ):
            raise ValueError('Partition bounds must not end before they start')
        return self


class TapeManifest(VersionedContract):
    """Index of a tape series. `complete=false` means the series is not readable."""

    series: TapeSeries
    partitions: tuple[TapePartition, ...]
    written_at: UtcTimestamp
    complete: bool
    precision_policy: OpaqueKey = 'float64-storage-decimal-on-read'

    @model_validator(mode='after')
    def unique_partitions(self) -> Self:
        paths = [partition.path for partition in self.partitions]
        if len(set(paths)) != len(paths):
            raise ValueError('Duplicate tape partition path')
        return self

    @model_validator(mode='after')
    def coverage_matches_partitions(self) -> Self:
        """The declared coverage must be what the stored files actually hold."""
        rows = sum(partition.rows for partition in self.partitions)
        if self.series.row_count != rows:
            raise ValueError('Tape row count must match its partitions')
        if self.series.coverage_start is not None:
            starts = [
                partition.min_event_at
                for partition in self.partitions
                if partition.min_event_at is not None
            ]
            if starts and min(starts) != self.series.coverage_start:
                raise ValueError('Tape coverage start must match its partitions')
        if self.series.coverage_end is not None:
            ends = [
                partition.max_event_at
                for partition in self.partitions
                if partition.max_event_at is not None
            ]
            if ends and max(ends) != self.series.coverage_end:
                raise ValueError('Tape coverage end must match its partitions')
        return self


class TapeReadResult(ContractModel):
    """Rows read back, plus what the reader must be told about their limits.

    `rows_outside_retention` counts stored rows that fall outside the
    retention window. It is reported rather than silently dropped, so a
    caller never mistakes a clipped read for complete history.
    """

    series: TapeSeries
    rows: NonNegativeCounter
    min_event_at: UtcTimestamp | None
    max_event_at: UtcTimestamp | None
    rows_outside_retention: NonNegativeCounter = 0


class TapeWriteResult(ContractModel):
    """What a write produced; the manifest is the durable record."""

    series: TapeSeries
    partitions: tuple[TapePartition, ...]
    dropped_outside_retention: NonNegativeCounter
