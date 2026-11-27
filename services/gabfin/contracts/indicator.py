"""Indicator observations and their provenance; no strategy or policy authority.

An indicator value is only meaningful together with the data it was
computed from. The IEX and SIP volume bases differ, so an OBV or MFI
computed on one and compared against the other is meaningless. Every
point therefore records its source coverage, and the field is required.
"""
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from gabfin.contracts.common import (
    ContractModel,
    ExactDecimal,
    OpaqueKey,
    UtcTimestamp,
    VersionedContract,
)
from gabfin.contracts.market import Timeframe

#: The data basis an indicator was computed from. These are not
#: interchangeable: IEX and SIP report different volumes.
SourceCoverage = Literal[
    'iex',
    'sip',
    'futu_nasdaq_totalview',
    'futu_arca',
    'unknown',
]

#: Whether the value was computed locally or fetched from a provider.
ComputedBy = Literal['local', 'futu_api']

IndicatorName = Literal[
    'sma',
    'ema',
    'wma',
    'macd',
    'macd_signal',
    'macd_histogram',
    'rsi',
    'stochastic_k',
    'stochastic_d',
    'stochastic_j',
    'roc',
    'momentum',
    'atr',
    'bollinger_upper',
    'bollinger_middle',
    'bollinger_lower',
    'bollinger_percent_b',
    'bollinger_bandwidth',
    'donchian_upper',
    'donchian_lower',
    'historical_volatility',
    'obv',
    'volume_sma',
    'mfi',
    'vwap',
]


class IndicatorPoint(VersionedContract):
    """One computed indicator value at one instant."""

    instrument_id: UUID
    indicator: IndicatorName
    params: dict[str, str]
    timeframe: Timeframe
    value: ExactDecimal | None
    event_at: UtcTimestamp
    computed_at: UtcTimestamp
    source_coverage: SourceCoverage
    computed_by: ComputedBy
    realtime: bool = False

    @model_validator(mode='after')
    def _honest_provenance(self) -> Self:
        if self.source_coverage == 'unknown':
            raise ValueError(
                'An indicator point must name its source coverage; IEX and SIP '
                'volumes are not interchangeable'
            )
        if self.computed_at < self.event_at:
            raise ValueError('An indicator cannot be computed before its bar')
        return self


class IndicatorSeries(ContractModel):
    """A run of indicator points for one indicator and one parameter set."""

    instrument_id: UUID
    indicator: IndicatorName
    params: dict[str, str]
    timeframe: Timeframe
    source_coverage: SourceCoverage
    points: tuple[IndicatorPoint, ...] = Field(max_length=100000)

    @model_validator(mode='after')
    def _consistent_points(self) -> Self:
        for point in self.points:
            if point.instrument_id != self.instrument_id:
                raise ValueError('An indicator series cannot mix instruments')
            if point.indicator != self.indicator:
                raise ValueError('An indicator series cannot mix indicators')
            if point.params != self.params:
                raise ValueError('An indicator series cannot mix parameter sets')
            if point.source_coverage != self.source_coverage:
                raise ValueError('An indicator series cannot mix source coverage')
        stamps = [point.event_at for point in self.points]
        if stamps != sorted(stamps):
            raise ValueError('Indicator points must be ordered in time')
        return self


class IndicatorStatus(ContractModel):
    """Why an indicator has no value, or that it has one."""

    indicator: IndicatorName
    params: dict[str, str]
    ready: bool
    reason: OpaqueKey | None = None
    required_bars: int | None = None
    observed_bars: int | None = None
