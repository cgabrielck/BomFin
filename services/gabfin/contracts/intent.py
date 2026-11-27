"""Advisory plans and strategy intents are distinct, versioned documents.

These models validate data shape. A producer-scope string is not proof of an
actor's authority; principal/capability checks belong at the service boundary.
Likewise, expiry is checked against execution context, not the parsing clock,
so historical documents remain readable for audit and replay.
"""
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from gabfin.contracts.common import NonEmptyText, UtcTimestamp, VersionedContract


class PositionSide(StrEnum):
    """Position direction, independent of the broker's buy/sell order side."""

    LONG = "long"
    SHORT = "short"


class PositionEffect(StrEnum):
    OPEN = "open"
    REDUCE = "reduce"
    CLOSE = "close"


class TradePlan(VersionedContract):
    """Research/chat output for display; never a strategy/executor input."""

    kind: Literal["trade_plan"]
    advisory: Literal[True]
    instrument: UUID
    side: PositionSide
    entry_scenarios: tuple[NonEmptyText, ...]
    exit_scenarios: tuple[NonEmptyText, ...]
    evidence: tuple[UUID, ...]
    as_of: UtcTimestamp

    @field_validator("advisory", mode="before")
    @classmethod
    def _explicit_advisory(cls, value: object) -> object:
        if value is not True:
            raise ValueError("TradePlan requires the explicit boolean advisory=true")
        return value


class StrategyIntent(VersionedContract):
    """Strategy output to risk evaluation; not a broker order or approval."""

    kind: Literal["strategy_intent"]
    intent_id: UUID
    strategy_version: NonEmptyText
    policy_version: NonEmptyText
    instrument: UUID
    side: PositionSide
    position_effect: PositionEffect
    setup: NonEmptyText
    invalidation: NonEmptyText
    expires_at: UtcTimestamp
    snapshot_id: UUID
    producer_scope: Literal["strategy:emit"]


IntentDocument = Annotated[TradePlan | StrategyIntent, Field(discriminator="kind")]
