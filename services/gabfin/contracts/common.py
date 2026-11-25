"""Exact wire primitives shared by GabFin domain contracts."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationInfo,
    WithJsonSchema,
)


def _exact_decimal_input(value: object, info: ValidationInfo) -> object:
    if info.mode == "json" and not isinstance(value, str):
        raise ValueError("Decimal JSON values must be strings")
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("Use Decimal, an integer, or a decimal string; never float")
    return value


def _decimal_wire(value: Decimal) -> str:
    return str(value)


ExactDecimal = Annotated[
    Decimal,
    BeforeValidator(_exact_decimal_input),
    Field(allow_inf_nan=False),
    PlainSerializer(_decimal_wire, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "decimal"}),
]

Ratio = Annotated[
    ExactDecimal,
    Field(ge=Decimal("0"), le=Decimal("1")),
    WithJsonSchema({"type": "string", "format": "decimal", "x-minimum": "0", "x-maximum": "1"}),
]


def _timestamp_input(value: object) -> object:
    if not isinstance(value, (datetime, str)):
        raise ValueError("Use an aware datetime or an ISO8601 string with offset")
    if isinstance(value, str):
        # Pydantic otherwise accepts numeric strings as Unix timestamps.
        return datetime.fromisoformat(value)
    return value


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _timestamp_wire(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


UtcTimestamp = Annotated[
    AwareDatetime,
    BeforeValidator(_timestamp_input),
    AfterValidator(_to_utc),
    PlainSerializer(_timestamp_wire, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]

NonEmptyText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
CurrencyCode = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{3}$")]


class ContractModel(BaseModel):
    """Reject unknown fields and accidental reassignment, not an auth boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class VersionedContract(ContractModel):
    schema_version: Literal["1.0"]


class Money(ContractModel):
    """A signed amount and code shape; no rounding, currency lookup or FX."""

    amount: ExactDecimal
    currency: CurrencyCode
