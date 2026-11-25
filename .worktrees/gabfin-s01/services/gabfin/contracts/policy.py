"""Policy declarations and risk results; registry authorization is a service duty."""
from typing import Annotated, Literal, Self
from uuid import UUID
from pydantic import Field, StrictBool, StringConstraints, model_validator
from gabfin.contracts.common import ContractModel, VersionedContract, OpaqueKey, Ratio, PositiveDecimal, Money, UtcTimestamp

Digest = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
TradeSession = Literal['pre_market','regular','post_market']


class RiskBounds(ContractModel):
    per_trade_risk: Ratio | None
    daily_loss: Ratio | None
    runtime_drawdown: Ratio | None
    gross_exposure_leverage: PositiveDecimal | None
    missing_data_policy: Literal['halt_entries'] | None


class PolicyVersion(VersionedContract):
    version: OpaqueKey
    allowed_strategies: tuple[OpaqueKey, ...]
    allowed_sessions: tuple[TradeSession, ...]
    allowed_assets: tuple[Literal['equity'], ...]
    risk_bounds: RiskBounds
    approval_hash: Digest | None
    approved_at: UtcTimestamp | None
    status: Literal['draft','approved','retired']

    @model_validator(mode='after')
    def declaration_consistency(self) -> Self:
        lists = (self.allowed_strategies, self.allowed_sessions, self.allowed_assets)
        if any(len(set(values)) != len(values) for values in lists):
            raise ValueError('Policy allowlists cannot contain duplicates')
        if self.status == 'draft':
            if self.approval_hash is not None or self.approved_at is not None:
                raise ValueError('Draft policy cannot claim approval metadata')
        elif (any(not values for values in lists)
              or any(value is None for value in self.risk_bounds.model_dump().values())
              or self.approval_hash is None or self.approved_at is None):
            raise ValueError('Approved/retired policy requires complete bounds and approval metadata')
        return self


class RiskCheck(ContractModel):
    code: OpaqueKey
    passed: StrictBool


class RiskDecision(VersionedContract):
    decision_id: UUID
    intent_id: UUID
    approved: StrictBool
    reason_codes: Annotated[tuple[OpaqueKey, ...], Field(min_length=1)]
    quantity: PositiveDecimal | None
    risk_amount: Money | None
    checks: Annotated[tuple[RiskCheck, ...], Field(min_length=1)]
    policy_version: OpaqueKey
    expires_at: UtcTimestamp

    @model_validator(mode='after')
    def sizing_consistency(self) -> Self:
        if len(set(self.reason_codes)) != len(self.reason_codes) or len({c.code for c in self.checks}) != len(self.checks):
            raise ValueError('Duplicate reason/check codes')
        if self.approved:
            if self.quantity is None or self.risk_amount is None or self.risk_amount.amount <= 0 or not all(c.passed for c in self.checks):
                raise ValueError('Approval requires positive sizing and passing checks')
        elif self.quantity is not None or self.risk_amount is not None:
            raise ValueError('Denied result cannot provide approved sizing')
        return self
