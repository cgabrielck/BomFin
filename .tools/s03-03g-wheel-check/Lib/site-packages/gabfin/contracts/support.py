"""Support documents for bounded research, replay and broker reconciliation."""
from typing import Literal,Self
from uuid import UUID
from pydantic import Field,JsonValue,StrictBool,model_validator
from gabfin.contracts.common import VersionedContract,ContractModel,NonEmptyText,OpaqueKey,UtcTimestamp,Money,ExactDecimal
from gabfin.contracts.market import Bar,QuoteSnapshot,NonNegativeCounter
from gabfin.contracts.research import ResearchHorizon,ResearchUsage
from gabfin.contracts.order import OrderEvent,OrderCommand

class ModelMessage(ContractModel):
    role: Literal['system','user','assistant']
    content: NonEmptyText

class ModelRequest(VersionedContract):
    request_id: UUID
    model: OpaqueKey
    output_schema: dict[str,JsonValue]
    messages: tuple[ModelMessage,...] = Field(min_length=1)
    evidence_refs: tuple[UUID,...]
    deadline: UtcTimestamp

class ModelResult(VersionedContract):
    request_id: UUID
    model: OpaqueKey
    output: dict[str,JsonValue] | None
    error: NonEmptyText | None
    usage: ResearchUsage
    @model_validator(mode='after')
    def outcome(self)->Self:
        if (self.output is None)==(self.error is None):
            raise ValueError('Exactly one output or error is required')
        return self

class CandidateObservation(VersionedContract):
    observation_id: UUID
    instrument: UUID
    reason: NonEmptyText
    evidence: tuple[UUID,...] = Field(min_length=1)
    horizon: ResearchHorizon
    observed_at: UtcTimestamp
    expires_at: UtcTimestamp
    action: Literal['include','exclude']
    @model_validator(mode='after')
    def interval(self)->Self:
        if self.expires_at<=self.observed_at or len(set(self.evidence))!=len(self.evidence):
            raise ValueError('Invalid candidate interval/evidence')
        return self

class StrategyContext(VersionedContract):
    as_of: UtcTimestamp
    finalized_bars: tuple[Bar,...]
    features: dict[OpaqueKey,ExactDecimal]
    account_snapshot_id: UUID
    strategy_version: OpaqueKey
    policy_version: OpaqueKey
    @model_validator(mode='after')
    def point_in_time(self)->Self:
        if any(b.status=='forming' or b.end>self.as_of or b.available_at>self.as_of for b in self.finalized_bars):
            raise ValueError('Strategy context requires available finalized bars')
        return self

class AccountSnapshot(VersionedContract):
    snapshot_id: UUID
    equity: Money
    buying_power: Money
    as_of: UtcTimestamp

class Position(ContractModel):
    instrument_id: UUID
    quantity: ExactDecimal

class BrokerSnapshot(VersionedContract):
    snapshot_id: UUID
    account: AccountSnapshot
    positions: tuple[Position,...]
    open_orders: tuple[OrderCommand,...]
    recent_fills: tuple[OrderEvent,...]
    as_of: UtcTimestamp
    complete: StrictBool
    @model_validator(mode='after')
    def consistency(self)->Self:
        if self.account.as_of>self.as_of or len({p.instrument_id for p in self.positions})!=len(self.positions):
            raise ValueError('Invalid account time or duplicate positions')
        if any(e.cum_fill_qty<=0 or e.fill_evidence!='broker_reported' or e.available_at>self.as_of for e in self.recent_fills):
            raise ValueError('Recent fills require available broker evidence')
        return self

class ReconciliationResult(VersionedContract):
    matched: StrictBool
    mismatches: tuple[NonEmptyText,...]
    entry_allowed: StrictBool
    @model_validator(mode='after')
    def consistency(self)->Self:
        if self.matched==bool(self.mismatches) or (self.entry_allowed and not self.matched):
            raise ValueError('Mismatches cannot permit entries')
        return self

class RiskContext(VersionedContract):
    account: AccountSnapshot
    reserved_risk: Money
    pending_orders: tuple[OrderCommand,...]
    borrow_available: StrictBool | None
    quotes: tuple[QuoteSnapshot,...]
    session: Literal['pre_market','regular','post_market']
    policy_version: OpaqueKey
    snapshot_id: UUID

class SubmitResult(VersionedContract):
    status: Literal['ACKNOWLEDGED','REJECTED','UNKNOWN']
    client_order_id: UUID
    broker_id: OpaqueKey | None
    reason: NonEmptyText | None
    @model_validator(mode='after')
    def acknowledgement(self)->Self:
        if self.status=='ACKNOWLEDGED' and self.broker_id is None:
            raise ValueError('Acknowledgement requires broker identity')
        return self

class OrderSnapshot(VersionedContract):
    command: OrderCommand
    latest_event: OrderEvent
    as_of: UtcTimestamp
    @model_validator(mode='after')
    def coherence(self)->Self:
        if self.command.client_order_id!=self.latest_event.client_order_id or self.latest_event.cum_fill_qty>self.command.qty or self.latest_event.available_at>self.as_of:
            raise ValueError('Order snapshot identity/quantity/time mismatch')
        return self

class ExperimentSpec(VersionedContract):
    experiment_id: UUID
    strategy_version: OpaqueKey
    dataset_manifest: OpaqueKey
    start: UtcTimestamp
    end: UtcTimestamp
    session_policy: tuple[OpaqueKey,...]
    execution_assumptions: tuple[NonEmptyText,...]
    @model_validator(mode='after')
    def interval(self)->Self:
        if self.start>=self.end:raise ValueError('Invalid experiment range')
        return self

class ExperimentResult(VersionedContract):
    experiment_id: UUID
    events: tuple[UUID,...]
    fills: tuple[OrderEvent,...]
    equity: tuple[Money,...]
    fees: Money
    warnings: tuple[NonEmptyText,...]

class HarnessProposal(VersionedContract):
    proposal_id: UUID
    artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_version: OpaqueKey
    deploy_version: OpaqueKey
    diff: NonEmptyText
    experiment_ids: tuple[UUID,...] = Field(min_length=1)
    metrics: dict[OpaqueKey,ExactDecimal]
    rollback_version: OpaqueKey
    approval: UUID | None

class HealthReport(VersionedContract):
    component: OpaqueKey
    heartbeat_at: UtcTimestamp
    state: Literal['healthy','degraded','unavailable','unknown']
    last_error_code: OpaqueKey | None
    lag_ms: NonNegativeCounter | None
    dependency_health: dict[OpaqueKey,Literal['healthy','degraded','unavailable','unknown']]
