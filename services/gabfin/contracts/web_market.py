"""Public browser subscription input; credentials never belong in this body."""
from typing import Self
from uuid import UUID

from pydantic import Field, StrictInt, model_validator

from gabfin.contracts.common import ContractModel
from gabfin.contracts.market import NonNegativeCounter
from gabfin.contracts.subscriptions import SubscriptionKey


class MarketRequest(ContractModel):
    version: StrictInt = Field(ge=1, le=1)
    keys: tuple[SubscriptionKey, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_keys(self) -> Self:
        if len({key.identity for key in self.keys}) != len(self.keys):
            raise ValueError('Duplicate market key')
        return self


class MarketStreamRequest(MarketRequest):
    epoch: UUID | None = None
    cursor: NonNegativeCounter | None = None

    @model_validator(mode='after')
    def paired_cursor(self) -> Self:
        if (self.epoch is None) != (self.cursor is None):
            raise ValueError('Resume requires epoch and cursor')
        return self
