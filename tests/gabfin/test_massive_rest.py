"""REST pagination stays on the configured proxy and accounts for every call."""
import importlib

import pytest

from gabfin.providers.massive.config import MassiveConfig


def module():
    return importlib.import_module('gabfin.providers.massive.rest')


def config(**kwargs):
    return MassiveConfig(base_url='https://proxy.example.test', api_key='fixture-client-secret', **kwargs)


def test_pagination_strips_upstream_credentials_and_keeps_proxy_origin():
    rest = module()
    requests = []
    def transport(request):
        requests.append(request)
        if len(requests) == 1:
            return rest.Response(200, {'results': [{'id': 1}], 'next_url':
                'https://upstream.example.test/v3/snapshot/options/SPY?cursor=abc&apiKey=upstream-secret'})
        return rest.Response(200, {'results': [{'id': 2}]})
    client = rest.MassiveRestClient(config(), transport=transport)
    assert list(client.results('/v3/snapshot/options/SPY')) == [{'id': 1}, {'id': 2}]
    assert requests[1].url == 'https://proxy.example.test/v3/snapshot/options/SPY?cursor=abc'
    assert requests[1].headers['X-Proxy-Key'] == 'fixture-client-secret'
    assert 'fixture-client-secret' not in repr(requests[1])
    assert 'proxy.example.test' not in repr(requests[1])
    assert client.stats['requests'] == 2


def test_local_limit_blocks_transport_until_window_expires():
    rest = module()
    now = [0.0]
    calls = []
    def transport(request):
        calls.append(request)
        return rest.Response(200, {'results': []})
    client = rest.MassiveRestClient(config(rest_qpm=2), transport=transport, clock=lambda: now[0])
    client.get('/v3/snapshot/options/SPY')
    client.get('/v3/snapshot/options/SPY')
    with pytest.raises(rest.MassiveRestError, match='rate_limited'):
        client.get('/v3/snapshot/options/SPY')
    assert len(calls) == 2
    assert client.stats['rate_limited'] == 1
    now[0] = 60.0
    client.get('/v3/snapshot/options/SPY')
    assert len(calls) == 3


@pytest.mark.parametrize('status', [401, 403, 429, 503])
def test_http_errors_are_explicit_and_do_not_echo_provider_payload(status):
    rest = module()
    client = rest.MassiveRestClient(config(), transport=lambda request:
        rest.Response(status, {'message': 'fixture-client-secret'}))
    with pytest.raises(rest.MassiveRestError) as caught:
        client.get('/v3/snapshot/options/SPY')
    assert caught.value.status == status
    assert 'fixture-client-secret' not in str(caught.value)


def test_transport_exceptions_are_sanitized():
    rest = module()
    def transport(request):
        raise RuntimeError('fixture-client-secret https://proxy.example.test')
    client = rest.MassiveRestClient(config(), transport=transport)
    with pytest.raises(rest.MassiveRestError, match='transport_failed') as caught:
        client.get('/v3/snapshot/options/SPY')
    assert caught.value.__cause__ is None
    assert 'fixture-client-secret' not in str(caught.value)


def test_cyclic_pagination_fails_instead_of_returning_incomplete_success():
    rest = module()
    client = rest.MassiveRestClient(config(), transport=lambda request:
        rest.Response(200, {'results': [], 'next_url': '/v3/snapshot/options/SPY'}))
    with pytest.raises(rest.MassiveRestError, match='pagination_cycle'):
        list(client.results('/v3/snapshot/options/SPY'))


@pytest.mark.parametrize('payload', [{'results': {}}, {'results': ['bad']}, {'next_url': 42}])
def test_malformed_pages_are_explicit_failures(payload):
    rest = module()
    client = rest.MassiveRestClient(config(), transport=lambda request: rest.Response(200, payload))
    with pytest.raises(rest.MassiveRestError):
        list(client.results('/v3/snapshot/options/SPY'))


def test_initial_absolute_urls_are_rejected_before_transport():
    rest = module()
    client = rest.MassiveRestClient(config(), transport=lambda request: pytest.fail('transport called'))
    with pytest.raises(rest.MassiveRestError, match='invalid_path'):
        client.get('https://elsewhere.example.test/data')
