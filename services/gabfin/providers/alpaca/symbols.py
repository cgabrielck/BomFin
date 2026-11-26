"""Symbol mapping between Alpaca tickers and Futu's US syntax.

Alpaca uses the bare ticker (`AAPL`). Futu prefixes US equities with
`US.` and formats options as `US.AAPL261218C00100000`. The mapping is
mechanical, but it is also a place where two vendors can disagree, so a
conflict is detected rather than resolved silently.
"""
import re

FUTU_US_PREFIX = 'US.'

#: The option suffix Alpaca uses, e.g. `AAPL261218C00100000`.
ALPACA_OPTION = re.compile(
    r'^(?P<root>[A-Za-z0-9.\-]+)'
    r'(?P<expiry>\d{6})'
    r'(?P<right>[CP])'
    r'(?P<strike>\d{8})$'
)

#: The option symbol Futu uses, e.g. `US.AAPL261218C00100000`.
FUTU_OPTION = re.compile(
    r'^US\.(?P<root>[A-Za-z0-9.\-]+)'
    r'(?P<expiry>\d{6})'
    r'(?P<right>[CP])'
    r'(?P<strike>\d{8})$'
)


class SymbolConflict(ValueError):
    """Two symbols map to each other in a way that cannot be resolved."""


def to_futu(symbol: str) -> str:
    """The Futu US equity symbol for an Alpaca ticker."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError('A symbol must be a nonempty string')
    value = symbol.strip()
    if value.startswith(FUTU_US_PREFIX):
        return value
    match = ALPACA_OPTION.match(value)
    if match:
        root = match.group('root')
        if not root.startswith(FUTU_US_PREFIX):
            root = FUTU_US_PREFIX + root
        return (
            f'{root}{match.group("expiry")}'
            f'{match.group("right")}{match.group("strike")}'
        )
    if '/' in value or '\\' in value:
        raise ValueError(f'Unsupported symbol shape: {symbol}')
    return FUTU_US_PREFIX + value


def to_alpaca(symbol: str) -> str:
    """The Alpaca ticker for a Futu US symbol."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError('A symbol must be a nonempty string')
    value = symbol.strip()
    if value.startswith(FUTU_US_PREFIX):
        return value[len(FUTU_US_PREFIX):]
    return value


def is_option(symbol: str) -> bool:
    """Whether a symbol names an option contract rather than an equity."""
    if not isinstance(symbol, str) or not symbol.strip():
        return False
    value = symbol.strip()
    if value.startswith(FUTU_US_PREFIX):
        return FUTU_OPTION.match(value) is not None
    return ALPACA_OPTION.match(value) is not None


def option_root(symbol: str) -> str:
    """The underlying ticker of an option symbol."""
    value = symbol.strip()
    match = FUTU_OPTION.match(value)
    if match is not None:
        return match.group('root')
    match = ALPACA_OPTION.match(value)
    if match is None:
        raise ValueError(f'Not an option symbol: {symbol}')
    return match.group('root')


def build_map(symbols: list[str]) -> dict[str, str]:
    """Build the Alpaca-to-Futu mapping, refusing conflicting pairs.

    A conflict means two different Alpaca tickers would claim the same
    Futu symbol, or one ticker would map two ways. Either way the caller
    must resolve it before the mapping is used.
    """
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    for symbol in symbols:
        futu = to_futu(symbol)
        existing = mapping.get(symbol)
        if existing is not None and existing != futu:
            raise SymbolConflict(f'{symbol} maps to both {existing} and {futu}')
        claimed = reverse.get(futu)
        if claimed is not None and claimed != symbol:
            raise SymbolConflict(
                f'{futu} is claimed by both {claimed} and {symbol}'
            )
        mapping[symbol] = futu
        reverse[futu] = symbol
    return mapping
