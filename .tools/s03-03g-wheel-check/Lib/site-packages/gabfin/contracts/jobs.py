"""Job lease and spend reservation observations, not a scheduler or budget ledger."""
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID
from pydantic import Field, StrictInt, model_validator
from gabfin.contracts.common import VersionedContract, UtcTimestamp, NonNegativeDecimal, CurrencyCode

Attempt = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]


class JobLease(VersionedContract):
    job_id: UUID
    worker_id: UUID
    lease_token: UUID = Field(repr=False)
    acquired_at: UtcTimestamp
    expires_at: UtcTimestamp
    attempt: Attempt

    @model_validator(mode='after')
    def lease_interval(self) -> Self:
        if self.expires_at <= self.acquired_at:
            raise ValueError('Lease expiry must follow acquisition')
        return self


class ReservationStatus(StrEnum):
    RESERVED = 'reserved'
    SETTLED = 'settled'
    RELEASED = 'released'
    UNKNOWN = 'unknown'


class Reservation(VersionedContract):
    reservation_id: UUID
    budget_id: UUID
    job_id: UUID
    amount: NonNegativeDecimal
    currency: CurrencyCode
    status: ReservationStatus
    actual_amount: NonNegativeDecimal | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @model_validator(mode='after')
    def cost_observation(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError('Reservation update cannot precede creation')
        if (self.status == ReservationStatus.SETTLED) != (self.actual_amount is not None):
            raise ValueError('Only settled reservations require a known actual cost')
        # Actual spend can exceed the estimate; preserve it for reconciliation.
        # Unknown status never automatically releases the original reservation.
        return self
