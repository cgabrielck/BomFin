"""Observed feed metadata and subscription declarations, without allocation or auth."""
from typing import Literal, Self
from uuid import UUID
from pydantic import Field, model_validator
from gabfin.contracts.common import ContractModel, VersionedContract, OpaqueKey, UtcTimestamp
from gabfin.contracts.market import AssetClass, MarketSession, Timeframe, NonNegativeCounter

Channel = Literal['quote','trade','bar']


def _unique(values):
    if len(set(values)) != len(values):
        raise ValueError('Duplicate declaration or subscription identity')


class _ChannelSpec(ContractModel):
    channel: Channel
    timeframe: Timeframe | None

    @model_validator(mode='after')
    def channel_shape(self) -> Self:
        if (self.channel == 'bar') != (self.timeframe is not None):
            raise ValueError('Only bar subscriptions require a timeframe')
        return self

    @property
    def channel_identity(self) -> tuple:
        return (self.channel, None if self.timeframe is None else (self.timeframe.count, self.timeframe.unit))


class SubscriptionKey(_ChannelSpec):
    instrument_id: UUID

    @property
    def identity(self) -> tuple:
        return (self.instrument_id, *self.channel_identity)


class HistoryLimit(_ChannelSpec):
    max_records: NonNegativeCounter | None


class SequenceRule(_ChannelSpec):
    """Omitted channels are opaque. Contiguous numbers must not reset mid-epoch."""
    semantics: Literal['opaque', 'contiguous']


class FeedCapabilities(VersionedContract):
    source: OpaqueKey
    asset_classes: tuple[AssetClass, ...]
    sessions: tuple[MarketSession, ...]
    latency_label: Literal['unknown','realtime','delayed','indicative']
    max_subscriptions: NonNegativeCounter | None
    history_limits: tuple[HistoryLimit, ...]
    checked_at: UtcTimestamp
    permission_errors: tuple[OpaqueKey, ...]
    sequence_rules: tuple[SequenceRule, ...] = ()

    @model_validator(mode='after')
    def distinct_capabilities(self) -> Self:
        for values in (self.asset_classes, self.sessions, self.permission_errors):
            _unique(values)
        _unique(tuple(limit.channel_identity for limit in self.history_limits))
        _unique(tuple(rule.channel_identity for rule in self.sequence_rules))
        return self


class Demand(VersionedContract):
    demand_id: UUID
    key: SubscriptionKey
    priority: Literal['holding','chart','strategy','watchlist','candidate']
    owner: UUID
    expires_at: UtcTimestamp


class SubscriptionRejection(ContractModel):
    key: SubscriptionKey
    reason_codes: tuple[OpaqueKey, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def distinct_reasons(self) -> Self:
        _unique(self.reason_codes)
        return self


class SubscriptionPlan(VersionedContract):
    source: OpaqueKey
    as_of: UtcTimestamp
    accepted: tuple[SubscriptionKey, ...]
    rejected: tuple[SubscriptionRejection, ...]

    @model_validator(mode='after')
    def disjoint_decisions(self) -> Self:
        accepted = tuple(key.identity for key in self.accepted)
        rejected = tuple(item.key.identity for item in self.rejected)
        _unique(accepted)
        _unique(rejected)
        if set(accepted) & set(rejected):
            raise ValueError('A subscription cannot be both accepted and rejected')
        return self
