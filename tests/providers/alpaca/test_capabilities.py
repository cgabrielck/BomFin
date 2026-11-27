"""Alpaca capability probes map observations onto the shared contract."""
from datetime import datetime, timezone

import pytest

from gabfin.providers.alpaca import capabilities
from gabfin.providers.alpaca.history import Request, Response

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def transport_for(responses: list[Response]):
    seen: list[Request] = []

    def transport(request: Request) -> Response:
        seen.append(request)
        index = len(seen) - 1
        if index >= len(responses):
            return Response(200, {})
        return responses[index]

    transport.requests = seen
    return transport


def test_a_realtime_probe_reports_trades_as_available():
    transport = transport_for(
        [Response(200, {'trades': {'AAPL': [{'p': '100.00'}]}})]
    )
    result = capabilities.probe_realtime_trades(transport)
    assert result.available is True
    assert result.status == 200


def test_a_realtime_probe_with_no_trades_is_available_but_empty():
    transport = transport_for([Response(200, {'trades': {}})])
    result = capabilities.probe_realtime_trades(transport)
    assert result.available is False


def test_an_entitlement_failure_is_reported_as_denied_not_unknown():
    transport = transport_for(
        [
            Response(
                403,
                {},
                message='subscription does not permit querying recent SIP data',
            )
        ]
    )
    result = capabilities.probe_realtime_trades(transport)
    assert result.available is False
    assert result.status == 403


def test_a_sip_probe_queries_outside_the_delayed_window():
    transport = transport_for([Response(200, {'bars': {'AAPL': [{'c': '1'}]}})])
    capabilities.probe_sip_history(transport, now=NOW)
    request = transport.requests[0]
    assert request.params['feed'] == 'sip'
    assert request.params['end'] == '2026-11-27T11:45:00Z'


def test_a_sip_probe_with_no_bars_is_available_but_empty():
    transport = transport_for([Response(200, {'bars': {}})])
    result = capabilities.probe_sip_history(transport, now=NOW)
    assert result.available is False
    assert result.status == 200


def test_the_option_probe_reads_structure_not_prices():
    transport = transport_for(
        [
            Response(
                200,
                {
                    'option_contracts': [
                        {
                            'symbol': 'AAPL261218C00100000',
                            'expiration_date': '2026-12-18',
                            'strike_price': '100',
                            'type': 'call',
                        }
                    ]
                },
            )
        ]
    )
    result = capabilities.probe_option_contracts(transport)
    assert result.available is True
    assert 'structure only' in result.detail


def test_a_failing_probe_is_unknown_rather_than_denied():
    def broken(request: Request) -> Response:
        raise RuntimeError('network down')

    report = capabilities.inspect_capabilities(broken, checked_at=NOW)
    assert report.errors
    assert all(probe.available is None for probe in report.probes)


def test_a_report_maps_onto_the_shared_capability_contract():
    transport = transport_for(
        [
            Response(200, {'trades': {'AAPL': [{'p': '100.00'}]}}),
            Response(200, {'bars': {'AAPL': [{'c': '1'}]}}),
            Response(200, {'option_contracts': [{'symbol': 'X'}]}),
        ]
    )
    report = capabilities.inspect_capabilities(transport, checked_at=NOW, now=NOW)
    contract = capabilities.to_feed_capabilities(report)
    assert contract.source == 'alpaca'
    assert contract.latency_label == 'realtime'
    assert contract.permission_errors == ()
    assert contract.checked_at == NOW


def test_a_denied_probe_appears_in_the_permission_errors():
    transport = transport_for(
        [
            Response(200, {'trades': {'AAPL': [{'p': '100.00'}]}}),
            Response(
                403,
                {},
                message='subscription does not permit querying recent SIP data',
            ),
            Response(200, {'option_contracts': [{'symbol': 'X'}]}),
        ]
    )
    report = capabilities.inspect_capabilities(transport, checked_at=NOW, now=NOW)
    contract = capabilities.to_feed_capabilities(report)
    assert 'sip_history_unavailable' in contract.permission_errors


def test_an_unknown_probe_yields_an_unknown_latency():
    transport = transport_for(
        [
            Response(500, {}, message='server error'),
            Response(200, {'bars': {'AAPL': [{'c': '1'}]}}),
            Response(200, {'option_contracts': [{'symbol': 'X'}]}),
        ]
    )
    report = capabilities.inspect_capabilities(transport, checked_at=NOW, now=NOW)
    contract = capabilities.to_feed_capabilities(report)
    assert contract.latency_label == 'unknown'
