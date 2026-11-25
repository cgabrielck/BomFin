"""Stdlib-only Futu US equity syntax, shared with the isolated SDK worker."""
import re

TICKER = r'[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*'


def valid_us_symbol(symbol: str) -> bool:
    return re.fullmatch(r'US\.' + TICKER, symbol) is not None


def us_equity_symbol(symbol):
    return (isinstance(symbol, str) and len(symbol) <= 100
            and valid_us_symbol(symbol)
            and re.fullmatch(r'US\..*[0-9]{6}[CP][0-9]+', symbol) is None)
