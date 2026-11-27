"""The input an indicator consumes: one finalized bar, and nothing else.

Indicators read price and volume only. They never see a forming bar, a
quote, or a provider event, because an indicator computed on a bar that
can still change is not an observation, it is a guess.

The type is deliberately small. An indicator that needs more than open,
high, low, close, volume and a timestamp is not an indicator.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class PriceBar:
    """One finalized bar."""

    event_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    session_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_at, datetime) or self.event_at.tzinfo is None:
            raise ValueError('An indicator bar needs an aware timestamp')
        if not (self.low <= self.open <= self.high):
            raise ValueError('The open must lie within the high and low')
        if not (self.low <= self.close <= self.high):
            raise ValueError('The close must lie within the high and low')
        if self.volume is not None and self.volume < 0:
            raise ValueError('Volume cannot be negative')

    @property
    def session(self) -> str:
        """The bucket a session-scoped indicator accumulates within."""
        if self.session_key is not None:
            return self.session_key
        return self.event_at.astimezone(timezone.utc).date().isoformat()

    @property
    def typical_price(self) -> Decimal:
        """The average of high, low and close."""
        return (self.high + self.low + self.close) / Decimal(3)


def from_contract(bar) -> PriceBar:
    """Build a `PriceBar` from a `gabfin.contracts.market.Bar`.

    A forming bar is refused. Its close can still move, so an indicator
    computed on it would report a value the market has not settled on.
    """
    from gabfin.contracts.market import Bar, BarStatus

    if not isinstance(bar, Bar):
        raise TypeError('A contract Bar is required')
    if bar.status == BarStatus.FORMING:
        raise ValueError('An indicator only consumes finalized bars')
    return PriceBar(
        event_at=bar.end,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )


def finalized(bars) -> list[PriceBar]:
    """Convert a sequence of contract bars, dropping the forming ones."""
    from gabfin.contracts.market import BarStatus

    result = []
    for bar in bars:
        if isinstance(bar, PriceBar):
            result.append(bar)
            continue
        if bar.status == BarStatus.FORMING:
            continue
        result.append(from_contract(bar))
    return result
