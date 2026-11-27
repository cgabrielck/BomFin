from uuid import UUID
import pytest
from decimal import Decimal, localcontext

from gabfin.contracts.market import Instrument

AAPL = UUID('11111111-1111-4111-8111-111111111111')
MSFT = UUID('22222222-2222-4222-8222-222222222222')
CALL = UUID('33333333-3333-4333-8333-333333333333')
PUT = UUID('44444444-4444-4444-8444-444444444444')


def equity(identifier=AAPL, symbol='US.AAPL'):
    return Instrument(schema_version='1.0', instrument_id=identifier, asset_class='equity',
                      vendor_symbols={'futu': symbol}, currency='USD', tick_size='0.01', lot_size='1')


def option(identifier=CALL, right='call', expiry='2026-12-18'):
    letter = 'C' if right == 'call' else 'P'
    return Instrument(schema_version='1.0', instrument_id=identifier, asset_class='option',
                      vendor_symbols={'futu': 'US.AAPL' + expiry[2:].replace('-', '') + letter + '350000'},
                      currency='USD', tick_size='0.01', lot_size='1',
                      option=dict(underlying_id=AAPL, expiry=expiry, right=right, strike='350', multiplier='100'))


def test_namespaced_symbol_resolution_preserves_equity_option_identity():
    from gabfin.providers.futu.symbols import InstrumentCatalog

    catalog = InstrumentCatalog([option(), equity()])
    assert catalog.resolve('futu', 'US.AAPL').instrument_id == AAPL
    assert catalog.resolve('futu', 'US.AAPL261218C350000').instrument_id == CALL
    assert catalog.get(CALL).option.underlying_id == AAPL
    assert catalog.get(MSFT) is None


def test_catalog_snapshots_cannot_be_mutated_by_producer_or_consumer():
    from gabfin.providers.futu.symbols import InstrumentCatalog

    original = equity()
    catalog = InstrumentCatalog([original])
    original.vendor_symbols['futu'] = 'US.MSFT'
    returned = catalog.get(AAPL)
    returned.vendor_symbols['futu'] = 'US.TSLA'
    assert catalog.resolve('futu', 'US.AAPL').vendor_symbols == {'futu': 'US.AAPL'}
    with pytest.raises(KeyError):
        catalog.resolve('futu', 'US.MSFT')


@pytest.mark.parametrize('case', ['id', 'symbol', 'underlying_missing', 'underlying_option', 'economic_option', 'wrong_option_symbol'])
def test_catalog_rejects_ambiguous_or_incomplete_identities(case):
    from gabfin.providers.futu.symbols import InstrumentCatalog

    if case == 'id':
        records = [equity(), equity()]
    elif case == 'symbol':
        records = [equity(), equity(MSFT)]
    elif case == 'underlying_missing':
        records = [option()]
    elif case == 'underlying_option':
        records = [equity(), option(), option(PUT, 'put').model_copy(update={
            'option': option(PUT, 'put').option.model_copy(update={'underlying_id': CALL})})]
    elif case == 'economic_option':
        records = [equity(), option(), option(PUT).model_copy(update={'vendor_symbols': {'other': 'alias'}})]
    else:
        records = [equity(), option().model_copy(update={'vendor_symbols': {'futu': 'US.MSFT261218C350000'}})]
    with pytest.raises(ValueError):
        InstrumentCatalog(records)


def test_source_namespaces_and_exact_symbols_are_distinct():
    from gabfin.providers.futu.symbols import InstrumentCatalog

    first = equity().model_copy(update={'vendor_symbols': {'futu': 'US.AAPL', 'other': 'AAPL'}})
    catalog = InstrumentCatalog([first, equity(MSFT, 'US.MSFT')])
    assert catalog.resolve('other', 'AAPL').instrument_id == AAPL
    with pytest.raises(KeyError):
        catalog.resolve('futu', 'AAPL')
    with pytest.raises(KeyError):
        catalog.resolve('futu', 'us.aapl')


@pytest.mark.parametrize('root', ['AAPL', 'BRK.B', 'A-B'])
def test_equity_cannot_claim_a_recognizable_futu_option_symbol(root):
    from gabfin.providers.futu.symbols import InstrumentCatalog
    with pytest.raises(ValueError):
        InstrumentCatalog([equity(symbol='US.' + root + '261218C350000')])


@pytest.mark.parametrize('precision', [2, 28])
@pytest.mark.parametrize('matching', [True, False])
def test_option_strike_identity_is_independent_of_decimal_context(precision, matching):
    from gabfin.providers.futu.symbols import InstrumentCatalog
    value = option().model_copy(update={
        'vendor_symbols': {'futu': 'US.AAPL261218C350123'},
        'option': option().option.model_copy(update={'strike': Decimal('350.123' if matching else '350')})})
    with localcontext() as context:
        context.prec = precision
        if matching:
            assert InstrumentCatalog([equity(), value]).get(CALL).option.strike == Decimal('350.123')
        else:
            with pytest.raises(ValueError):
                InstrumentCatalog([equity(), value])
