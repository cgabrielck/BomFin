"""Order observations, not an OMS or proof of permission to submit."""
from typing import Literal, Self
from uuid import UUID
from pydantic import model_validator
from gabfin.contracts.common import VersionedContract, OpaqueKey, PositiveDecimal, NonNegativeDecimal, UtcTimestamp
from gabfin.contracts.policy import TradeSession


class OrderCommand(VersionedContract):
    client_order_id: UUID
    intent_id: UUID
    instrument: UUID
    side: Literal['buy','sell']
    qty: PositiveDecimal
    type: Literal['market','limit']
    limit_price: PositiveDecimal | None
    tif: Literal['day','gtc','ioc','fok']
    session: TradeSession
    risk_decision_id: UUID

    @model_validator(mode='after')
    def order_shape(self) -> Self:
        if (self.type == 'limit') != (self.limit_price is not None):
            raise ValueError('Only limit orders must carry a limit price')
        if self.session != 'regular' and (self.type != 'limit' or self.tif != 'day'):
            raise ValueError('Extended-session shape requires limit/day; broker checks still required')
        return self


class OrderEvent(VersionedContract):
    event_id: UUID
    broker_id: OpaqueKey | None
    client_order_id: UUID
    status: Literal['proposed','approved','send_pending','acknowledged','partial','filled','canceled','rejected','unknown']
    cum_fill_qty: NonNegativeDecimal
    # Cumulative average execution price, never the order's limit price.
    fill_price: PositiveDecimal | None
    fill_evidence: Literal['unavailable','broker_reported']
    evidence_id: UUID | None
    event_at: UtcTimestamp
    received_at: UtcTimestamp
    available_at: UtcTimestamp
    dedup_key: OpaqueKey

    @model_validator(mode='after')
    def honest_fill(self) -> Self:
        if self.available_at < self.received_at:
            raise ValueError('Availability cannot precede local receipt')
        if self.status in ('partial','filled') and self.cum_fill_qty == 0:
            raise ValueError('Fill status requires positive cumulative quantity')
        if self.fill_evidence == 'broker_reported':
            if self.cum_fill_qty == 0 or self.evidence_id is None or self.broker_id is None:
                raise ValueError('Broker fill evidence requires quantity and provenance')
        elif self.evidence_id is not None or self.fill_price is not None:
            raise ValueError('Unavailable fill evidence cannot supply a price or evidence ID')
        return self
