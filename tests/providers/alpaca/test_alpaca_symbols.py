"""Symbol mapping between Alpaca tickers and Futu's US syntax."""
import pytest

from gabfin.providers.alpaca import symbols


def test_an_equity_ticker_gets_the_us_prefix():
    assert symbols.to_futu('AAPL') == 'US.AAPL'
    assert symbols.to_futu('BRK.B') == 'US.BRK.B'


def test_an_already_prefixed_symbol_is_unchanged():
    assert symbols.to_futu('US.AAPL') == 'US.AAPL'


def test_the_reverse_mapping_drops_the_prefix():
    assert symbols.to_alpaca('US.AAPL') == 'AAPL'
    assert symbols.to_alpaca('AAPL') == 'AAPL'


def test_the_round_trip_is_stable():
    assert symbols.to_alpaca(symbols.to_futu('AAPL')) == 'AAPL'
    assert symbols.to_futu(symbols.to_alpaca('US.AAPL')) == 'US.AAPL'


def test_an_option_symbol_keeps_its_economic_terms():
    assert symbols.to_futu('AAPL261218C00100000') == 'US.AAPL261218C00100000'


def test_option_symbols_are_recognised():
    assert symbols.is_option('AAPL261218C00100000') is True
    assert symbols.is_option('US.AAPL261218C00100000') is True
    assert symbols.is_option('AAPL') is False


def test_the_option_root_is_recovered():
    assert symbols.option_root('US.AAPL261218C00100000') == 'AAPL'
    assert symbols.option_root('AAPL261218C00100000') == 'AAPL'


def test_a_non_option_symbol_has_no_root():
    with pytest.raises(ValueError):
        symbols.option_root('AAPL')


def test_a_map_detects_a_conflict():
    with pytest.raises(symbols.SymbolConflict):
        symbols.build_map(['AAPL', 'US.AAPL'])


def test_a_map_accepts_distinct_symbols():
    mapping = symbols.build_map(['AAPL', 'MSFT', 'NVDA'])
    assert mapping == {
        'AAPL': 'US.AAPL',
        'MSFT': 'US.MSFT',
        'NVDA': 'US.NVDA',
    }


def test_an_empty_symbol_is_refused():
    with pytest.raises(ValueError):
        symbols.to_futu('  ')
    with pytest.raises(ValueError):
        symbols.to_alpaca('')
