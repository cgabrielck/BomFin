"""Read-only internal market protocol; credentials are masked and never replayed."""
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, SecretStr, StrictInt, model_validator

from gabfin.contracts.common import ContractModel
from gabfin.contracts.feed import MarketSnapshot, MarketUpdate
from gabfin.contracts.market import NonNegativeCounter


class StreamHello(ContractModel):
    version: StrictInt = Field(ge=1, le=1)
    token: SecretStr = Field(min_length=16, max_length=256)
    instrument_ids: tuple[UUID, ...] = Field(min_length=1, max_length=1000)
    epoch: UUID | None = None
    cursor: NonNegativeCounter | None = None

    @model_validator(mode='after')
    def paired_cursor(self) -> Self:
        if (self.epoch is None) != (self.cursor is None):
            raise ValueError('Resume requires epoch and cursor')
        if len(set(self.instrument_ids)) != len(self.instrument_ids):
            raise ValueError('Duplicate requested instrument')
        return self


class SnapshotFrame(ContractModel):
    version: Literal[1]
    kind: Literal['snapshot']
    payload: MarketSnapshot


class UpdateFrame(ContractModel):
    version: Literal[1]
    kind: Literal['update']
    payload: MarketUpdate


class ResumeFrame(ContractModel):
    version: Literal[1]
    kind: Literal['resumed']
    epoch: UUID
    cursor: NonNegativeCounter


class ErrorFrame(ContractModel):
    version: Literal[1]
    kind: Literal['error']
    code: Literal['unauthorized', 'invalid_request', 'snapshot_required', 'slow_consumer']


InternalFrame = Annotated[SnapshotFrame | UpdateFrame | ResumeFrame | ErrorFrame, Field(discriminator='kind')]
