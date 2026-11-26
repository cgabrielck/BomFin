"""Observed feed metadata and subscription declarations, without allocation or auth."""
from typing import Literal, Self
from uuid import UUID
from pydantic import Field, StrictBool, model_validator
from gabfin.contracts.common import ContractModel, VersionedContract, OpaqueKey, UtcTimestamp
from gabfin.contracts.indicator import SourceCoverage
from gabfin.contracts.market import AssetClass, MarketSession, Timeframe, NonNegativeCounter, PositiveCounter

Channel = Literal['quote','trade','bar']

#: What a feed charges for. A free tier and an exchange fee are not the
#: same product, and the difference is what makes a plan sustainable.
FeeClass = Literal['none', 'exchange', 'per_quote', 'subscription']


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

    # --- What the feed actually covers, in the words a user needs. ---

    #: The venue whose prices this feed reports. `sip` is the
    #: consolidated tape, `iex` a single exchange, `futu_nasdaq_totalview`
    #: Nasdaq's own book. These are not interchangeable: an OBV computed
    #: on one and compared against another is a comparison of nothing.
    venue_coverage: SourceCoverage = 'unknown'
    #: Whether the feed reports in real time. False means delayed.
    realtime: StrictBool = False
    #: The measured delay in minutes. None means not measured.
    delay_minutes: NonNegativeCounter | None = None
    #: Whether a price from this feed may be used as an entry basis.
    #: An indicative or delayed price may not, whatever else is true.
    tradable_for_entry: StrictBool = False
    #: How many depth levels the feed carries. None means unknown.
    depth_levels: PositiveCounter | None = None
    #: What the feed costs.
    fee_class: FeeClass = 'none'
    #: Why the feed cannot be used, when it cannot.
    unavailable_reason: OpaqueKey | None = None

    @model_validator(mode='after')
    def distinct_capabilities(self) -> Self:
        for values in (self.asset_classes, self.sessions, self.permission_errors):
            _unique(values)
        _unique(tuple(limit.channel_identity for limit in self.history_limits))
        _unique(tuple(rule.channel_identity for rule in self.sequence_rules))
        return self

    @model_validator(mode='after')
    def honest_entry_basis(self) -> Self:
        """A feed cannot claim to be tradable and be delayed at once.

        The rule exists because "tradable" is the field a UI turns
        into an entry button. If it can be true while the price is
        fifteen minutes old, the button is a lie the user pays for.
        """
        if self.tradable_for_entry:
            if not self.realtime:
                raise ValueError('A delayed or non-realtime feed cannot be an entry basis')
            if self.latency_label in ('delayed', 'indicative'):
                raise ValueError('A delayed or indicative feed cannot be an entry basis')
        if self.realtime and self.delay_minutes not in (None, 0):
            raise ValueError('A real-time feed cannot carry a measured delay')
        if self.delay_minutes is not None and not self.realtime and self.delay_minutes == 0:
            raise ValueError('A feed with no measured delay is not a delayed feed')
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
