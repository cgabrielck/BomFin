from uuid import UUID, uuid4

import pytest


def test_verified_symbols_persist_and_keep_seed_identity(tmp_path):
    from gabfin.universe.directory import InstrumentDirectory
    seed = uuid4()
    calls = []
    def lookup(symbol):
        calls.append(symbol)
        return {'ticker': symbol, 'market': 'stocks', 'locale': 'us', 'active': True, 'currency_name': 'usd', 'name': 'Microsoft'}
    directory = InstrumentDirectory(tmp_path / 'symbols.sqlite', lookup=lookup)
    directory.seed('AAPL', seed)
    assert directory.resolve('AAPL')['instrument_id'] == str(seed)
    row = directory.resolve('MSFT')
    assert UUID(row['instrument_id'])
    assert row['name'] == 'Microsoft'
    assert calls == ['MSFT']
    reopened = InstrumentDirectory(tmp_path / 'symbols.sqlite')
    assert reopened.resolve('MSFT') == row
    assert reopened.by_id(UUID(row['instrument_id'])) == row
    assert row['instrument_id'] in reopened.instrument_ids


@pytest.mark.parametrize('change', [{'ticker': 'WRONG'}, {'locale': 'gb'}, {'market': 'crypto'}, {'active': False}, {'currency_name': 'gbp'}])
def test_provider_identity_must_match_supported_us_equity(tmp_path, change):
    from gabfin.universe.directory import InstrumentDirectory
    directory = InstrumentDirectory(tmp_path / 's.sqlite', lookup=lambda symbol: {
        'ticker': symbol, 'market': 'stocks', 'locale': 'us', 'active': True, 'currency_name': 'usd', **change})
    assert directory.resolve('MSFT') is None
    assert directory.instrument_ids == ()


def test_massive_reference_distinguishes_unknown_from_unavailable():
    from gabfin.providers.massive.reference import MassiveReference
    from gabfin.providers.massive.rest import MassiveRestError
    class Client:
        def get(self, path):
            if 'MISSING' in path:
                raise MassiveRestError('http_error', status=404)
            if 'DENIED' in path:
                raise MassiveRestError('http_error', status=403)
            assert path == '/v3/reference/tickers/MSFT'
            return {'results': {'ticker': 'MSFT'}}
    reference = MassiveReference(Client())
    assert reference.lookup('MSFT') == {'ticker': 'MSFT'}
    assert reference.lookup('MISSING') is None
    with pytest.raises(MassiveRestError):
        reference.lookup('DENIED')


def test_batch_provider_error_does_not_erase_other_results():
    from gabfin.universe.resolve import resolve_batch
    from gabfin.providers.massive.rest import MassiveRestError
    def lookup(symbol):
        if symbol == 'DENIED':
            raise MassiveRestError('http_error', status=403)
        return {'instrument_id': str(uuid4()), 'name': 'Verified'}
    rows = resolve_batch('MSFT DENIED AAPL', lookup)
    assert [row['status'] for row in rows] == ['resolved', 'unavailable', 'resolved']
    assert rows[1]['reason'] == 'provider_unavailable'
