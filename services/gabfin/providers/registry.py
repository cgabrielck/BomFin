"""Source-agnostic provider registry.

The planner used to hard-code `source == 'futu'`. That made every new
source a fork of the planner instead of a registration, and it put a
Futu import inside the market layer, which is supposed to know nothing
about any vendor.

The registry inverts that. A source declares the namespace it names
instruments under, the markets it covers, the shapes it accepts, and
the quota pools it draws from. The planner then asks the registry
about the source it is planning for, and stays silent about which
vendor that is.

Two rules keep this honest:

- A profile describes what a source *accepts*, never what it is
  entitled to. Entitlement is measured elsewhere and arrives as a
  capability snapshot.
- A symbol that no registered source accepts is rejected with an
  explicit reason. It is never silently reinterpreted as another
  vendor's symbol.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Callable, Mapping

from gabfin.contracts.market import AssetClass
from gabfin.providers.alpaca.symbols import is_option as alpaca_is_option
from gabfin.providers.futu.symbols_wire import us_equity_symbol


@dataclass(frozen=True)
class SourceProfile:
    """How one source names and charges for what it serves."""

    source: str
    #: The key under which this source's symbols live in
    #: `Instrument.vendor_symbols`.
    namespace: str
    #: The markets this source serves.
    markets: tuple[str, ...]
    #: The market prefixes this source's syntax can express. A symbol
    #: whose prefix is known but not served is `market_unsupported`;
    #: one whose prefix is unknown is `vendor_symbol_invalid`.
    known_market_prefixes: tuple[str, ...]
    #: Whether the source's symbols carry the market themselves. Futu's
    #: `US.AAPL` does; Alpaca's bare `AAPL` does not, and a dotted
    #: Alpaca ticker (`BRK.B`) is a ticker, not a market.
    symbol_carries_market: bool
    #: Whether an equity symbol is acceptable to this source.
    accepts_equity: Callable[[str], bool]
    #: Whether an option symbol is acceptable to this source.
    accepts_option: Callable[[str], bool]
    #: Which quota pool each asset class draws from.
    pools: Mapping[AssetClass, str]
    #: Pools whose capacity is also bounded by the capability's
    #: `max_subscriptions`.
    maximum_pools: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.source or not self.namespace:
            raise ValueError('A source profile needs a source and a namespace')
        if not self.markets:
            raise ValueError('A source profile must cover at least one market')
        if not self.pools:
            raise ValueError('A source profile must map at least one asset class')
        for asset_class, pool in self.pools.items():
            if not isinstance(asset_class, AssetClass) or not pool:
                raise ValueError('Quota pools are named per asset class')
        if len(set(self.pools.values())) != len(self.pools):
            raise ValueError('Each asset class needs its own quota pool')
        for pool in self.maximum_pools:
            if pool not in self.pools.values():
                raise ValueError('A maximum pool must be a used pool')
        object.__setattr__(self, 'pools', MappingProxyType(dict(self.pools)))

    def market_of(self, symbol: str) -> str | None:
        """The market a symbol names, or None when it names none.

        A source that writes the market into its symbols (`US.AAPL`)
        names it in the leading token. A source that does not (`AAPL`,
        or the dotted ticker `BRK.B`) serves exactly one market.
        """
        if not isinstance(symbol, str) or not symbol:
            return None
        if not self.symbol_carries_market:
            return self.markets[0]
        for prefix in self.known_market_prefixes:
            if symbol.startswith(prefix):
                return prefix.rstrip('.')
        return None

    def validate(self, instrument) -> str | None:
        """The reason this instrument cannot be served, or None if it can.

        The reason codes are the ones the planner already speaks:
        `vendor_symbol_missing`, `market_unsupported`,
        `vendor_symbol_invalid`.
        """
        symbol = instrument.vendor_symbols.get(self.namespace)
        if symbol is None:
            return 'vendor_symbol_missing'
        market = self.market_of(symbol)
        if market is None:
            return 'vendor_symbol_invalid'
        if market not in self.markets:
            return 'market_unsupported'
        accepts = (self.accepts_option if instrument.asset_class == AssetClass.OPTION
                   else self.accepts_equity)
        if not accepts(symbol):
            return 'vendor_symbol_invalid'
        return None

    def pool_of(self, asset_class: AssetClass) -> str | None:
        return self.pools.get(asset_class)


class UnknownSource(ValueError):
    """No registered profile describes this source."""


class ProviderRegistry:
    """The set of known sources, and the routing between them."""

    def __init__(self, profiles=()):
        self._profiles: dict[str, SourceProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: SourceProfile) -> SourceProfile:
        if profile.source in self._profiles:
            raise ValueError(f'Duplicate source profile: {profile.source}')
        self._profiles[profile.source] = profile
        return profile

    def profile(self, source: str) -> SourceProfile:
        try:
            return self._profiles[source]
        except KeyError:
            raise UnknownSource(source) from None

    def sources(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def routes(self, instrument) -> tuple[SourceProfile, ...]:
        """Every registered source that can serve this instrument."""
        return tuple(
            profile for profile in
            (self._profiles[name] for name in self.sources())
            if profile.validate(instrument) is None
        )

    def route(self, instrument):
        """The source that serves this instrument, or None."""
        found = self.routes(instrument)
        return found[0] if found else None


#: Futu names US equities with an explicit `US.` prefix, and its syntax
#: can express Hong Kong and mainland symbols that this build does not
#: serve.
_FUTU_OPTION = re.compile(r'US\.[A-Za-z0-9]+[0-9]{6}[CP][0-9]+')

#: Alpaca names US equities with the bare ticker.
_ALPACA_EQUITY = re.compile(r'[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*')


FUTU_PROFILE = SourceProfile(
    source='futu',
    namespace='futu',
    markets=('US',),
    known_market_prefixes=('US.', 'HK.', 'SH.', 'SZ.'),
    symbol_carries_market=True,
    accepts_equity=us_equity_symbol,
    accepts_option=lambda symbol: bool(_FUTU_OPTION.fullmatch(symbol)),
    pools={AssetClass.EQUITY: 'equity', AssetClass.OPTION: 'option'},
    maximum_pools=('equity',),
)

ALPACA_PROFILE = SourceProfile(
    source='alpaca',
    namespace='alpaca',
    markets=('US',),
    known_market_prefixes=(),
    symbol_carries_market=False,
    accepts_equity=lambda symbol: bool(_ALPACA_EQUITY.fullmatch(symbol)),
    accepts_option=alpaca_is_option,
    pools={AssetClass.EQUITY: 'equity'},
)


def default_registry() -> ProviderRegistry:
    """The registry of the sources this build knows about."""
    return ProviderRegistry([FUTU_PROFILE, ALPACA_PROFILE])
