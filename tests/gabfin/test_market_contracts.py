"""Market identities, honest missing values and temporal consistency."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest
from pydantic import ValidationError


def test_instrument_preserves_fractional_lot_and_vendor_identity(instrument_payload):
    from gabfin.contracts.market import Instrument

    model = Instrument.model_validate_json(json.dumps(instrument_payload))
    assert model.lot_size == Decimal("0.001")
    assert model.vendor_symbols == {"feed": "TEST", "other": "US.TEST"}
    wire = json.loads(model.model_dump_json())
    assert wire["tick_size"] == "0.01"
    assert wire["lot_size"] == "0.001"
    assert wire["option"] is None


def test_option_requires_contract_terms_and_preserves_multiplier(option_payload):
    from gabfin.contracts.market import Instrument

    model = Instrument.model_validate_json(json.dumps(option_payload))
    assert model.option.expiry == date(2026, 12, 18)
    assert model.option.multiplier == Decimal("10")
    assert json.loads(model.model_dump_json())["option"]["strike"] == "100.00"


@pytest.mark.parametrize("field", ["underlying_id", "expiry", "right", "strike", "multiplier"])
def test_option_does_not_invent_missing_terms(option_payload, field):
    from gabfin.contracts.market import Instrument

    option_payload["option"].pop(field)
    with pytest.raises(ValidationError):
        Instrument.model_validate(option_payload)


def test_option_requires_terms_and_equity_cannot_have_them(option_payload, instrument_payload):
    from gabfin.contracts.market import Instrument

    instrument_payload["option"] = option_payload["option"]
    with pytest.raises(ValidationError):
        Instrument.model_validate(instrument_payload)
    option_payload.pop("option")
    with pytest.raises(ValidationError):
        Instrument.model_validate(option_payload)


def test_option_cannot_reference_itself(option_payload):
    from gabfin.contracts.market import Instrument

    option_payload["option"]["underlying_id"] = option_payload["instrument_id"]
    with pytest.raises(ValidationError):
        Instrument.model_validate(option_payload)


@pytest.mark.parametrize("field", ["strike", "multiplier"])
@pytest.mark.parametrize("value", ["0", "-1", 10.0, True])
def test_option_numbers_are_exact_positive_values(option_payload, field, value):
    from gabfin.contracts.market import Instrument

    option_payload["option"][field] = value
    with pytest.raises(ValidationError):
        Instrument.model_validate(option_payload)


@pytest.mark.parametrize("expiry", ["2026-12-18T00:00:00Z", datetime(2026, 12, 18, tzinfo=timezone.utc), 1797552000, True, "2026-02-30"])
def test_option_expiry_is_a_date_not_an_instant(option_payload, expiry):
    from gabfin.contracts.market import Instrument

    option_payload["option"]["expiry"] = expiry
    with pytest.raises(ValidationError):
        Instrument.model_validate(option_payload)


def test_historical_option_expiry_remains_a_calendar_date(option_payload):
    from gabfin.contracts.market import Instrument

    option_payload["option"]["expiry"] = date(2000, 1, 1)
    assert Instrument.model_validate(option_payload).option.expiry == date(2000, 1, 1)


@pytest.mark.parametrize("field", ["tick_size", "lot_size"])
@pytest.mark.parametrize("value", ["0", "-0.01", 0.01, True])
def test_instrument_units_require_exact_positive_decimals(instrument_payload, field, value):
    from gabfin.contracts.market import Instrument

    instrument_payload[field] = value
    with pytest.raises(ValidationError):
        Instrument.model_validate(instrument_payload)


@pytest.mark.parametrize("symbols", [{}, {"feed": ""}, {"feed": "TEST", " feed": "OTHER"}, {"feed": "TEST\n"}])
def test_vendor_symbols_do_not_silently_normalize_or_collide(instrument_payload, symbols):
    from gabfin.contracts.market import Instrument

    instrument_payload["vendor_symbols"] = symbols
    with pytest.raises(ValidationError):
        Instrument.model_validate(instrument_payload)


def test_quote_keeps_each_price_time_age_and_missing_last(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    model = QuoteSnapshot.model_validate_json(json.dumps(quote_payload))
    assert model.bid.price == Decimal("100.10")
    assert model.bid.age_ms == 1000
    assert model.ask.age_ms == 500
    assert model.last is None
    wire = model.model_dump_json()
    assert json.loads(wire)["last"] is None
    assert QuoteSnapshot.model_validate_json(wire) == model


def test_zero_bid_is_not_replaced_by_missing(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"]["price"] = "0"
    wire = QuoteSnapshot.model_validate(quote_payload).model_dump_json()
    assert json.loads(wire)["bid"]["price"] == "0"
    assert json.loads(wire)["last"] is None


@pytest.mark.parametrize("age", [0, None, -1, True, 1000.0, 9007199254740992])
def test_quote_rejects_fabricated_or_unsafe_age(quote_payload, age):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"]["age_ms"] = age
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)


def test_unknown_quote_time_requires_null_age_and_incomplete_flag(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"].update(event_at=None, age_ms=None)
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["quality"] = ["incomplete"]
    assert QuoteSnapshot.model_validate(quote_payload).bid.age_ms is None
    quote_payload["bid"]["age_ms"] = 0
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)


def test_future_source_time_is_recorded_as_skew_not_fresh(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"].update(event_at="2026-11-25T14:30:02Z", age_ms=None)
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["quality"] = ["clock_skew"]
    assert QuoteSnapshot.model_validate(quote_payload).bid.age_ms is None


def test_quote_cannot_use_information_available_after_capture(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["ask"]["available_at"] = "2026-11-25T14:30:02Z"
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)


def test_quote_local_availability_cannot_precede_receipt(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"]["available_at"] = "2026-11-25T14:30:00Z"
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)


def test_empty_quote_is_explicitly_unavailable(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload.update(bid=None, ask=None, last=None)
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["quality"] = ["unavailable"]
    assert QuoteSnapshot.model_validate(quote_payload).bid is None


def test_crossed_quote_is_preserved_only_with_a_flag(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["bid"]["price"] = "101"
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["quality"] = ["crossed"]
    assert QuoteSnapshot.model_validate(quote_payload).bid.price == Decimal("101")


def test_locked_quote_is_not_falsely_classified_as_crossed(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["ask"]["price"] = "100.10"
    model = QuoteSnapshot.model_validate(quote_payload)
    assert model.bid.price == model.ask.price
    assert "crossed" not in model.quality


def test_entitlement_status_is_not_assumed_without_checked_time(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["entitlements"]["checked_at"] = None
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["entitlements"]["status"] = "unknown"
    assert QuoteSnapshot.model_validate(quote_payload).entitlements.status == "unknown"


def test_permission_denial_is_visible_in_quality(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["entitlements"]["status"] = "denied"
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)
    quote_payload["quality"] = ["permission_denied"]
    assert QuoteSnapshot.model_validate(quote_payload).entitlements.status == "denied"


def test_quote_does_not_use_a_future_entitlement_check(quote_payload):
    from gabfin.contracts.market import QuoteSnapshot

    quote_payload["entitlements"]["checked_at"] = "2026-11-25T15:00:00Z"
    with pytest.raises(ValidationError):
        QuoteSnapshot.model_validate(quote_payload)


@pytest.mark.parametrize("volume", [None, "0", "12345.5"])
def test_bar_preserves_unknown_zero_and_fractional_volume(bar_payload, volume):
    from gabfin.contracts.market import Bar

    bar_payload["volume"] = volume
    model = Bar.model_validate_json(json.dumps(bar_payload))
    assert json.loads(model.model_dump_json())["volume"] == volume


@pytest.mark.parametrize("field,value", [("high", "99.5"), ("low", "100.5"), ("open", "103"), ("close", "98"), ("close", "0"), ("volume", "-1"), ("volume", 0.0)])
def test_bar_rejects_impossible_or_inexact_prices_and_volume(bar_payload, field, value):
    from gabfin.contracts.market import Bar

    bar_payload[field] = value
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


def test_zero_bar_cannot_stand_in_for_missing_prices(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload.update(open="0", high="0", low="0", close="0")
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


@pytest.mark.parametrize("count", [0, -1, True, 1.0, 9007199254740992])
def test_timeframe_count_is_a_positive_safe_integer(bar_payload, count):
    from gabfin.contracts.market import Bar

    bar_payload["timeframe"]["count"] = count
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


@pytest.mark.parametrize("revision", [0, -1, True, 1.0, "1", 9007199254740992])
def test_corrected_bar_needs_a_real_positive_revision(bar_payload, revision):
    from gabfin.contracts.market import Bar

    bar_payload.update(status="corrected", revision=revision)
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


def test_corrected_bar_roundtrip_preserves_provenance(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload.update(status="corrected", revision=1, close="101.50")
    model = Bar.model_validate_json(json.dumps(bar_payload))
    assert model.revision == 1
    assert model.corporate_action_policy == "raw-v1"
    assert Bar.model_validate_json(model.model_dump_json()) == model


def test_bar_requires_corporate_action_policy(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload.pop("corporate_action_policy")
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


def test_bar_has_a_positive_interval(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload["end"] = bar_payload["start"]
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


def test_bar_availability_cannot_precede_local_receipt(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload["available_at"] = "2026-11-24T14:31:00Z"
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)


def test_forming_bar_can_end_in_future_but_final_bar_cannot(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload["end"] = "2026-11-24T14:32:00Z"
    with pytest.raises(ValidationError):
        Bar.model_validate(bar_payload)
    bar_payload["status"] = "forming"
    assert Bar.model_validate(bar_payload).status == "forming"


def test_trading_day_timeframe_is_not_assumed_to_be_fixed_hours(bar_payload):
    from gabfin.contracts.market import Bar

    bar_payload.update(
        timeframe={"count": 2, "unit": "trading_day"},
        start="2026-03-06T14:30:00Z", end="2026-03-09T20:00:00Z",
        event_at="2026-03-09T20:00:00Z", received_at="2026-03-09T20:00:00.100Z",
        available_at="2026-03-09T20:00:00.200Z",
    )
    assert Bar.model_validate(bar_payload).timeframe.count == 2
