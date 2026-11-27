"""The FRED client, with no network and no key."""
import json
from datetime import date

import pytest

from gabfin.providers.fred.client import (
    KEY_VARIABLE,
    FredClient,
    MacroError,
    MacroKeyMissing,
    Request,
    Response,
    build_url,
    parse_value,
    read_key,
    redact,
)

KEY = 'super-secret-key-1234567890'


class RecordingTransport:
    """Records the requests it was given and returns a fixed response."""

    def __init__(self, response: Response | None = None):
        self.requests: list[Request] = []
        self._response = response or Response(
            status=200,
            body=json.dumps({'observations': []}),
        )

    def __call__(self, request: Request) -> Response:
        self.requests.append(request)
        return self._response


def payload(observations) -> str:
    return json.dumps({'observations': observations})


def observation(value='1.5', date_stamp='2026-01-15', release='2026-01-16'):
    return {
        'realtime_start': release,
        'realtime_end': release,
        'date': date_stamp,
        'value': value,
    }


def test_the_key_is_read_from_the_environment():
    assert read_key({KEY_VARIABLE: KEY}) == KEY
    assert read_key({}) is None
    assert read_key({KEY_VARIABLE: '  '}) is None


def test_a_missing_key_is_reported_clearly():
    client = FredClient(key=None, transport=RecordingTransport())
    client._key = None
    with pytest.raises(MacroKeyMissing) as error:
        client.observations('UNRATE')
    assert KEY_VARIABLE in str(error.value)


def test_the_key_never_appears_in_an_error_message():
    transport = RecordingTransport(Response(status=403, body='forbidden'))
    client = FredClient(key=KEY, transport=transport)
    with pytest.raises(MacroError) as error:
        client.observations('UNRATE')
    message = str(error.value)
    assert KEY not in message
    assert '403' in message
    assert 'UNRATE' in message


def test_the_key_never_appears_when_the_response_is_not_json():
    transport = RecordingTransport(Response(status=200, body='not json at all'))
    client = FredClient(key=KEY, transport=transport)
    with pytest.raises(MacroError) as error:
        client.observations('UNRATE')
    assert KEY not in str(error.value)


def test_the_key_never_appears_when_the_observations_are_missing():
    transport = RecordingTransport(Response(status=200, body=json.dumps({})))
    client = FredClient(key=KEY, transport=transport)
    with pytest.raises(MacroError) as error:
        client.observations('UNRATE')
    assert KEY not in str(error.value)


def test_the_key_never_appears_in_a_transport_error():
    class ExplodingTransport:
        def __call__(self, request):
            raise RuntimeError(f'failed to reach {request.url}')

    client = FredClient(key=KEY, transport=ExplodingTransport())
    with pytest.raises(MacroError) as error:
        client.observations('UNRATE')
    message = str(error.value)
    assert KEY not in message
    assert 'UNRATE' in message


def test_redaction_removes_the_key():
    assert KEY not in redact(f'url?api_key={KEY}', KEY)
    assert KEY not in redact(f'url?api_key={KEY}&x=1', KEY)
    assert 'REDACTED' in redact(f'url?api_key={KEY}', KEY)


def test_redaction_leaves_ordinary_text_alone():
    assert redact('nothing to hide', KEY) == 'nothing to hide'
    assert redact('nothing to hide', None) == 'nothing to hide'


def test_the_request_carries_the_key_in_the_query_string():
    transport = RecordingTransport()
    client = FredClient(key=KEY, transport=transport)
    client.observations('UNRATE')
    request = transport.requests[0]
    assert request.params['api_key'] == KEY
    assert 'api_key=' in request.url


def test_the_key_is_redacted_out_of_a_url_before_it_is_logged():
    url = build_url({'series_id': 'UNRATE', 'api_key': KEY})
    assert KEY in url
    assert KEY not in redact(url, KEY)


def test_a_date_range_is_passed_through():
    transport = RecordingTransport()
    client = FredClient(key=KEY, transport=transport)
    client.observations('UNRATE', start=date(2020, 1, 1), end=date(2026, 1, 1))
    params = transport.requests[0].params
    assert params['observation_start'] == '2020-01-01'
    assert params['observation_end'] == '2026-01-01'


def test_a_missing_value_is_none_and_not_zero():
    assert parse_value('.') is None
    assert parse_value('') is None
    assert parse_value(None) is None
    assert parse_value('not a number') is None


def test_a_present_value_is_a_decimal():
    assert parse_value('1.25') == __import__('decimal').Decimal('1.25')
    assert parse_value(3) == __import__('decimal').Decimal('3')


def test_the_rate_limiter_is_called_before_each_request():
    class CountingLimiter:
        def __init__(self):
            self.calls = 0

        def acquire(self):
            self.calls += 1
            return 0.0

    limiter = CountingLimiter()
    transport = RecordingTransport()
    client = FredClient(key=KEY, transport=transport, rate_limiter=limiter)
    client.observations('UNRATE')
    client.observations('PAYEMS')
    assert limiter.calls == 2


def test_the_release_returns_the_latest_observation():
    transport = RecordingTransport(
        Response(
            status=200,
            body=payload([observation('1.0'), observation('2.0', '2026-02-15')]),
        )
    )
    client = FredClient(key=KEY, transport=transport)
    latest = client.release('UNRATE')
    assert latest['value'] == '2.0'


def test_the_release_returns_none_when_there_is_nothing():
    transport = RecordingTransport()
    client = FredClient(key=KEY, transport=transport)
    assert client.release('UNRATE') is None
