"""New GabFin contracts: exact wire values and explicit intent boundaries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError


def test_money_roundtrip_exact():
    from gabfin.contracts.common import Money

    original = Money(amount=Decimal("0.10"), currency="USD")
    wire = original.model_dump_json()
    assert json.loads(wire) == {"amount": "0.10", "currency": "USD"}
    restored = Money.model_validate_json(wire)
    assert restored.amount == Decimal("0.10")
    assert restored.amount.as_tuple().exponent == -2


@pytest.mark.parametrize("amount", ["0", "-23.50", "1000000000000000.000001", "0.10000000000000000000001"])
def test_money_preserves_signed_values_and_precision(amount):
    from gabfin.contracts.common import Money

    wire = Money(amount=amount, currency="HKD").model_dump_json()
    assert json.loads(wire)["amount"] == amount
    assert Money.model_validate_json(wire).amount == Decimal(amount)


def test_exact_integer_python_input_is_supported():
    from gabfin.contracts.common import Money

    assert Money(amount=10, currency="USD").amount == Decimal("10")


@pytest.mark.parametrize("amount", [0.1, True, False, None, "NaN", "Infinity", "-Infinity", Decimal("NaN")])
def test_money_rejects_inexact_or_nonfinite_values(amount):
    from gabfin.contracts.common import Money

    with pytest.raises(ValidationError):
        Money(amount=amount, currency="USD")


@pytest.mark.parametrize("amount", [0.1, 10, True, None])
def test_decimal_json_input_must_be_a_string(amount):
    from gabfin.contracts.common import Money

    with pytest.raises(ValidationError):
        Money.model_validate_json(json.dumps({"amount": amount, "currency": "USD"}))


@pytest.mark.parametrize("currency", ["", "usd", "US", "USDD", "US1"])
def test_money_rejects_malformed_currency_codes(currency):
    from gabfin.contracts.common import Money

    with pytest.raises(ValidationError):
        Money(amount="0.10", currency=currency)


def test_money_rejects_unknown_fields_and_mutation():
    from gabfin.contracts.common import Money

    with pytest.raises(ValidationError):
        Money(amount="0.10", currency="USD", quantity="1")
    money = Money(amount="0.10", currency="USD")
    with pytest.raises(ValidationError):
        money.amount = Decimal("1")


@pytest.mark.parametrize("ratio", ["0", "0.4", "1"])
def test_ratio_accepts_closed_unit_interval(ratio):
    from gabfin.contracts.common import Ratio

    adapter = TypeAdapter(Ratio)
    value = adapter.validate_python(ratio)
    assert value == Decimal(ratio)
    assert json.loads(adapter.dump_json(value)) == ratio


@pytest.mark.parametrize("ratio", ["-0.0001", "1.0001", 0.4, True, "NaN"])
def test_ratio_rejects_out_of_range_or_inexact_values(ratio):
    from gabfin.contracts.common import Ratio

    with pytest.raises(ValidationError):
        TypeAdapter(Ratio).validate_python(ratio)


@pytest.mark.parametrize("value", [datetime(2026, 11, 25, 9, 30), "2026-11-25T09:30:00", "2026-11-25", 0, 1795599000, True, "0", "1795599000", "1795599000.25"])
def test_timezone_required(value):
    from gabfin.contracts.common import UtcTimestamp

    with pytest.raises(ValidationError):
        TypeAdapter(UtcTimestamp).validate_python(value)


@pytest.mark.parametrize("value", ["2026-11-25T09:30:00-05:00", datetime(2026, 11, 25, 22, 30, tzinfo=timezone(timedelta(hours=8)))])
def test_timestamp_normalizes_to_utc(value):
    from gabfin.contracts.common import UtcTimestamp

    adapter = TypeAdapter(UtcTimestamp)
    timestamp = adapter.validate_python(value)
    assert timestamp == datetime(2026, 11, 25, 14, 30, tzinfo=timezone.utc)
    assert timestamp.tzinfo is timezone.utc
    assert json.loads(adapter.dump_json(timestamp)) == "2026-11-25T14:30:00Z"


def test_json_schema_describes_money_as_decimal_string():
    from gabfin.contracts.common import Money

    schema = Money.model_json_schema(mode="serialization")
    assert schema["properties"]["amount"]["type"] == "string"
    assert schema["additionalProperties"] is False


def _trade_plan_payload():
    return {
        "schema_version": "1.0",
        "kind": "trade_plan",
        "advisory": True,
        "instrument": "11111111-1111-4111-8111-111111111111",
        "side": "short",
        "entry_scenarios": ["Failure to hold the prior session high"],
        "exit_scenarios": ["Close the short if invalidation is reached"],
        "evidence": ["22222222-2222-4222-8222-222222222222"],
        "as_of": "2026-11-25T09:30:00-05:00",
    }


def _strategy_intent_payload():
    return {
        "schema_version": "1.0",
        "kind": "strategy_intent",
        "intent_id": "33333333-3333-4333-8333-333333333333",
        "strategy_version": "breakout-v1",
        "policy_version": "policy-v1",
        "instrument": "11111111-1111-4111-8111-111111111111",
        "side": "short",
        "position_effect": "close",
        "setup": "Close the strategy's short allocation",
        "invalidation": "Do not increase the short position",
        "expires_at": "2026-11-25T16:00:00-05:00",
        "snapshot_id": "44444444-4444-4444-8444-444444444444",
        "producer_scope": "strategy:emit",
    }


def test_trade_plan_never_executable():
    from gabfin.contracts.intent import StrategyIntent, TradePlan

    plan = TradePlan.model_validate(_trade_plan_payload())
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(plan)
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(plan.model_dump())
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate_json(plan.model_dump_json())


def test_intent_union_preserves_advisory_type():
    from gabfin.contracts.intent import IntentDocument, StrategyIntent, TradePlan

    adapter = TypeAdapter(IntentDocument)
    restored = adapter.validate_json(json.dumps(_trade_plan_payload()))
    assert isinstance(restored, TradePlan)
    assert not isinstance(restored, StrategyIntent)
    assert restored.advisory is True
    assert json.loads(adapter.dump_json(restored))["kind"] == "trade_plan"


@pytest.mark.parametrize("kind", [None, "order_command"])
def test_intent_union_requires_a_known_explicit_tag(kind):
    from gabfin.contracts.intent import IntentDocument

    payload = _trade_plan_payload()
    if kind is None:
        payload.pop("kind")
    else:
        payload["kind"] = kind
    with pytest.raises(ValidationError):
        TypeAdapter(IntentDocument).validate_json(json.dumps(payload))


@pytest.mark.parametrize("version", [None, "2.0", 1])
@pytest.mark.parametrize("model_name", ["TradePlan", "StrategyIntent"])
def test_contract_requires_supported_explicit_schema_version(model_name, version):
    from gabfin.contracts import intent

    payload = _trade_plan_payload() if model_name == "TradePlan" else _strategy_intent_payload()
    if version is None:
        payload.pop("schema_version")
    else:
        payload["schema_version"] = version
    with pytest.raises(ValidationError):
        getattr(intent, model_name).model_validate(payload)


@pytest.mark.parametrize("advisory", [None, False, "true", 1])
def test_trade_plan_advisory_is_explicit_boolean_true(advisory):
    from gabfin.contracts.intent import TradePlan

    payload = _trade_plan_payload()
    if advisory is None:
        payload.pop("advisory")
    else:
        payload["advisory"] = advisory
    with pytest.raises(ValidationError):
        TradePlan.model_validate(payload)


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("effect", ["open", "reduce", "close"])
def test_direction_and_position_effect_survive_wire_roundtrip(side, effect):
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload.update(side=side, position_effect=effect)
    original = StrategyIntent.model_validate(payload)
    wire = original.model_dump_json()
    assert json.loads(wire)["side"] == side
    assert json.loads(wire)["position_effect"] == effect
    restored = StrategyIntent.model_validate_json(wire)
    assert restored.side == side
    assert restored.position_effect == effect
    assert restored.instrument == UUID("11111111-1111-4111-8111-111111111111")
    assert restored.expires_at == datetime(2026, 11, 25, 21, 0, tzinfo=timezone.utc)


def test_position_effect_cannot_silently_default_to_open():
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload.pop("position_effect")
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_strategy_direction_does_not_accept_broker_sides(side):
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload["side"] = side
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


@pytest.mark.parametrize("effect", ["reverse", "sell"])
def test_position_effect_rejects_unknown_actions(effect):
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload["position_effect"] = effect
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


@pytest.mark.parametrize("field", ["strategy_version", "policy_version", "setup", "invalidation"])
def test_intent_requires_nonblank_provenance_and_rationale(field):
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload[field] = "  "
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


@pytest.mark.parametrize("field", ["instrument", "intent_id", "snapshot_id"])
def test_intent_ids_must_be_uuids(field):
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload[field] = "AAPL"
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


@pytest.mark.parametrize("field", ["quantity", "approved", "client_order_id"])
@pytest.mark.parametrize("model_name", ["TradePlan", "StrategyIntent"])
def test_broker_or_risk_fields_cannot_be_injected(model_name, field):
    from gabfin.contracts import intent

    payload = _trade_plan_payload() if model_name == "TradePlan" else _strategy_intent_payload()
    payload[field] = "1"
    with pytest.raises(ValidationError):
        getattr(intent, model_name).model_validate(payload)


def test_chat_scope_is_not_an_intent_producer_marker():
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload["producer_scope"] = "chat:research"
    with pytest.raises(ValidationError):
        StrategyIntent.model_validate(payload)


def test_expired_intent_can_be_deserialized_for_audit():
    from gabfin.contracts.intent import StrategyIntent

    payload = _strategy_intent_payload()
    payload["expires_at"] = "2000-01-01T00:00:00Z"
    restored = StrategyIntent.model_validate_json(json.dumps(payload))
    assert restored.expires_at == datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_advisory_scenarios_and_evidence_are_validated():
    from gabfin.contracts.intent import TradePlan

    payload = _trade_plan_payload()
    payload["entry_scenarios"] = ["  "]
    with pytest.raises(ValidationError):
        TradePlan.model_validate(payload)
    payload = _trade_plan_payload()
    payload["evidence"] = ["not-an-evidence-id"]
    with pytest.raises(ValidationError):
        TradePlan.model_validate(payload)


def test_wire_schema_exposes_intent_discriminator_and_advisory_constraint():
    from gabfin.contracts.intent import IntentDocument, TradePlan

    schema = TypeAdapter(IntentDocument).json_schema(mode="serialization")
    assert schema["discriminator"]["propertyName"] == "kind"
    assert set(schema["discriminator"]["mapping"]) == {"trade_plan", "strategy_intent"}
    plan_schema = TradePlan.model_json_schema(mode="serialization")
    assert plan_schema["properties"]["advisory"]["const"] is True
    assert plan_schema["properties"]["as_of"]["format"] == "date-time"
    assert plan_schema["properties"]["instrument"]["format"] == "uuid"
