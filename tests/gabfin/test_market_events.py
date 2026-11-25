"""Typed source events retain identity, precision and capture provenance."""
from copy import deepcopy
import json

import pytest
from pydantic import TypeAdapter, ValidationError


def _envelope(kind, payload):
    if kind == "bar":
        times = {key: payload[key] for key in ("event_at", "received_at", "available_at")}
    else:
        times = {
            "event_at": "2026-11-25T14:30:00.500Z",
            "received_at": "2026-11-25T14:30:00.900Z",
            "available_at": "2026-11-25T14:30:01.100Z",
        }
    return {
        "schema_version": "1.0", "event_id": "33333333-3333-4333-8333-333333333333",
        "instrument_id": "11111111-1111-4111-8111-111111111111", **times,
        "source": "test-feed", "source_seq": None, "dedup_key": "test-feed:event:opaque-1",
        "kind": kind, "payload": deepcopy(payload),
    }


@pytest.mark.parametrize("kind", ["quote", "trade", "bar"])
def test_market_event_has_typed_roundtrip_payload(kind, quote_payload, trade_payload, bar_payload):
    from gabfin.contracts.events import MarketEvent

    payload = {"quote": quote_payload, "trade": trade_payload, "bar": bar_payload}[kind]
    adapter = TypeAdapter(MarketEvent)
    event = adapter.validate_json(json.dumps(_envelope(kind, payload)))
    assert event.kind == kind
    assert event.payload.instrument_id == event.instrument_id
    assert adapter.validate_json(adapter.dump_json(event)) == event


@pytest.mark.parametrize("key", [None, "", " ", " event", "event ", "event\n", "event\tpart", "event\x00part"])
def test_event_requires_an_opaque_nonempty_dedup_key(trade_payload, key):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    if key is None:
        data.pop("dedup_key")
    else:
        data["dedup_key"] = key
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_json(json.dumps(data))


def test_nullable_sequence_still_requires_dedup_key(trade_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    adapter = TypeAdapter(MarketEvent)
    assert adapter.validate_python(data).source_seq is None
    data.pop("dedup_key")
    with pytest.raises(ValidationError):
        adapter.validate_python(data)


def test_large_sequence_and_case_sensitive_key_survive_wire(trade_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data.update(source_seq="900719925474099300001", dedup_key="Feed:Trade:AbC-001")
    adapter = TypeAdapter(MarketEvent)
    event = adapter.validate_json(json.dumps(data))
    wire = json.loads(adapter.dump_json(event))
    assert wire["source_seq"] == "900719925474099300001"
    assert wire["dedup_key"] == "Feed:Trade:AbC-001"
    assert wire["payload"]["price"] == "100.15"
    assert wire["payload"]["quantity"] == "0.1"


@pytest.mark.parametrize("sequence", [1, 9007199254740993, True, ""])
def test_sequence_cannot_be_a_lossy_json_number(trade_payload, sequence):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data["source_seq"] = sequence
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_json(json.dumps(data))


def test_event_instrument_must_match_payload(trade_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data["instrument_id"] = "55555555-5555-4555-8555-555555555555"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


def test_wrong_kind_cannot_reinterpret_payload(quote_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("quote", quote_payload)
    data["kind"] = "bar"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_json(json.dumps(data))


@pytest.mark.parametrize("kind", ["quote", "bar"])
def test_event_cannot_relabel_payload_as_a_different_feed(kind, quote_payload, bar_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope(kind, quote_payload if kind == "quote" else bar_payload)
    data["source"] = "different-feed"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


@pytest.mark.parametrize("kind", [None, "broker_fill"])
def test_event_requires_known_explicit_kind(trade_payload, kind):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    if kind is None:
        data.pop("kind")
    else:
        data["kind"] = kind
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


@pytest.mark.parametrize("event_at", ["2000-01-01T00:00:00Z", "2027-01-01T00:00:00Z"])
def test_source_clock_skew_and_late_events_are_not_discarded(trade_payload, event_at):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data["event_at"] = event_at
    event = TypeAdapter(MarketEvent).validate_python(data)
    assert event.event_at.isoformat().startswith(event_at[:10])


def test_local_event_availability_cannot_precede_receipt(trade_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data["available_at"] = "2026-11-25T14:30:00Z"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


@pytest.mark.parametrize("field", ["event_at", "received_at", "available_at"])
def test_bar_event_must_preserve_payload_timestamps(bar_payload, field):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("bar", bar_payload)
    data[field] = "2026-11-24T14:31:00.150Z"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


def test_quote_event_cannot_publish_before_capture(quote_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("quote", quote_payload)
    data["available_at"] = "2026-11-25T14:30:00.950Z"
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


@pytest.mark.parametrize("field,value", [("price", "0"), ("quantity", "0"), ("quantity", "-1"), ("price", 100.15)])
def test_nested_trade_prices_and_quantity_keep_decimal_constraints(trade_payload, field, value):
    from gabfin.contracts.events import MarketEvent

    trade_payload[field] = value
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_json(json.dumps(_envelope("trade", trade_payload)))


def test_nested_quote_does_not_accept_a_float_price(quote_payload):
    from gabfin.contracts.events import MarketEvent

    quote_payload["bid"]["price"] = 100.1
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_json(json.dumps(_envelope("quote", quote_payload)))


def test_market_events_cannot_receive_order_approval_fields(trade_payload):
    from gabfin.contracts.events import MarketEvent

    data = _envelope("trade", trade_payload)
    data["approved"] = True
    with pytest.raises(ValidationError):
        TypeAdapter(MarketEvent).validate_python(data)


def test_market_event_schema_preserves_kind_specific_payloads():
    from gabfin.contracts.events import MarketEvent

    schema = TypeAdapter(MarketEvent).json_schema(mode="serialization")
    assert schema["discriminator"]["propertyName"] == "kind"
    assert set(schema["discriminator"]["mapping"]) == {"quote", "trade", "bar"}
    for name in ("QuoteMarketEvent", "TradeMarketEvent", "BarMarketEvent"):
        assert "$ref" in schema["$defs"][name]["properties"]["payload"]
