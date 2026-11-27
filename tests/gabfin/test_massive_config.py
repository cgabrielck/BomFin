"""Massive configuration must fail closed without exposing provider secrets."""
import importlib
import logging

import pytest
from pydantic import ValidationError


KEY = 'synthetic-s1-secret-12345678'


def config_module():
    return importlib.import_module('gabfin.providers.massive.config')


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ('BASE_URL', 'API_KEY', 'WS_PATH', 'MAX_SUBSCRIPTIONS', 'REST_QPM'):
        monkeypatch.delenv(f'MASSIVE_{name}', raising=False)


def test_load_config_reads_environment_and_derives_credential_free_ws_url(monkeypatch):
    monkeypatch.setenv('MASSIVE_BASE_URL', 'https://feed.example.test/proxy/')
    monkeypatch.setenv('MASSIVE_API_KEY', KEY)
    cfg = config_module().load_config()
    assert cfg.ws_url == 'wss://feed.example.test/proxy/ws'
    assert cfg.api_key.get_secret_value() == KEY
    assert cfg.max_subscriptions == 100
    assert cfg.rest_qpm == 1000


@pytest.mark.parametrize('missing', ['BASE_URL', 'API_KEY'])
def test_missing_environment_is_a_safe_validation_error(monkeypatch, missing):
    monkeypatch.setenv('MASSIVE_BASE_URL', 'https://feed.example.test')
    monkeypatch.setenv('MASSIVE_API_KEY', KEY)
    monkeypatch.delenv(f'MASSIVE_{missing}')
    with pytest.raises(ValidationError) as caught:
        config_module().load_config()
    assert f'MASSIVE_{missing}' in str(caught.value)
    assert KEY not in str(caught.value)


def test_repr_serialization_and_logging_hide_key_and_endpoint(caplog):
    cfg = config_module().MassiveConfig(base_url='https://feed.example.test', api_key=KEY)
    with caplog.at_level(logging.INFO):
        logging.getLogger('massive-config-test').info('%s %r', cfg, cfg)
    for output in (str(cfg), repr(cfg), cfg.model_dump_json(), repr(cfg.model_dump()), caplog.text):
        assert KEY not in output
        assert 'https://feed.example.test' not in output


@pytest.mark.parametrize('url', [
    'http://feed.example.test', 'ftp://feed.example.test', 'https://user:password@feed.example.test',
    f'https://feed.example.test?key={KEY}', 'https://feed.example.test/#fragment',
    'not-a-url',
])
def test_unsafe_base_url_rejected_without_echoing_input(url):
    with pytest.raises(ValidationError) as caught:
        config_module().MassiveConfig(base_url=url, api_key=KEY)
    assert KEY not in str(caught.value)
    assert url not in str(caught.value)


@pytest.mark.parametrize('field,value', [('max_subscriptions', 0), ('max_subscriptions', 101),
                                         ('rest_qpm', 0), ('rest_qpm', 1001),
                                         ('api_key', ''), ('ws_path', '//other.test/ws'),
                                         ('ws_path', '/ws?key=secret')])
def test_invalid_credentials_paths_and_plan_limits_rejected(field, value):
    args = dict(base_url='https://feed.example.test', api_key=KEY)
    args[field] = value
    with pytest.raises(ValidationError):
        config_module().MassiveConfig(**args)


def test_redaction_never_exposes_even_short_keys():
    redact = config_module().redact_key
    for value in ('', 'a', 'abcd', KEY):
        assert redact(value) == '****'
