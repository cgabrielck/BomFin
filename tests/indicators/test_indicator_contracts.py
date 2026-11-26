"""The indicator contract; provenance and honesty rules."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from gabfin.contracts.indicator import (
    IndicatorPoint,
    IndicatorSeries,
    IndicatorStatus,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
INSTRUMENT = '11111111-1111-4111-8111-111111111111'
TIMEFRAME = {'count': 1, 'unit': 'trading_day'}


def point(**overrides) -> dict:
    payload = {
        'schema_version': '1.0',
        'instrument_id': INSTRUMENT,
        'indicator': 'rsi',
        'params': {'period': '14'},
        'timeframe': TIMEFRAME,
        'value': '55.5',
        'event_at': NOW.isoformat().replace('+00:00', 'Z'),
        'computed_at': NOW.isoformat().replace('+00:00', 'Z'),
        'source_coverage': 'sip',
        'computed_by': 'local',
        'realtime': False,
    }
    payload.update(overrides)
    return payload


def test_a_point_round_trips():
    parsed = IndicatorPoint.model_validate(point())
    assert IndicatorPoint.model_validate_json(parsed.model_dump_json()) == parsed


def test_the_source_coverage_is_required():
    with pytest.raises(ValidationError):
        IndicatorPoint.model_validate(point(source_coverage='unknown'))


def test_an_unknown_source_coverage_cannot_be_declared():
    """The point of requiring coverage is that 'unknown' is not an answer."""
    with pytest.raises(ValidationError) as error:
        IndicatorPoint.model_validate(point(source_coverage='unknown'))
    assert 'source coverage' in str(error.value)


def test_a_point_cannot_be_computed_before_its_bar():
    with pytest.raises(ValidationError):
        IndicatorPoint.model_validate(
            point(computed_at=(NOW - timedelta(seconds=1)).isoformat())
        )


def test_iex_and_sip_are_different_coverage_values():
    iex = IndicatorPoint.model_validate(point(source_coverage='iex'))
    sip = IndicatorPoint.model_validate(point(source_coverage='sip'))
    assert iex.source_coverage != sip.source_coverage


def test_a_series_cannot_mix_coverage():
    later = (NOW + timedelta(minutes=1)).isoformat().replace('+00:00', 'Z')
    first = IndicatorPoint.model_validate(point(source_coverage='iex'))
    second = IndicatorPoint.model_validate(
        point(source_coverage='sip', event_at=later, computed_at=later)
    )
    with pytest.raises(ValidationError):
        IndicatorSeries.model_validate(
            {
                'instrument_id': INSTRUMENT,
                'indicator': 'rsi',
                'params': {'period': '14'},
                'timeframe': TIMEFRAME,
                'source_coverage': 'iex',
                'points': [
                    first.model_dump(mode='json'),
                    second.model_dump(mode='json'),
                ],
            }
        )


def test_a_series_must_be_ordered_in_time():
    first = IndicatorPoint.model_validate(point()).model_dump(mode='json')
    second = IndicatorPoint.model_validate(
        point(event_at=(NOW - timedelta(minutes=1)).isoformat())
    ).model_dump(mode='json')
    with pytest.raises(ValidationError):
        IndicatorSeries.model_validate(
            {
                'instrument_id': INSTRUMENT,
                'indicator': 'rsi',
                'params': {'period': '14'},
                'timeframe': TIMEFRAME,
                'source_coverage': 'sip',
                'points': [first, second],
            }
        )


def test_a_status_reports_why_an_indicator_has_no_value():
    status = IndicatorStatus(
        indicator='rsi',
        params={'period': '14'},
        ready=False,
        reason='insufficient_history',
        required_bars=14,
        observed_bars=3,
    )
    assert status.reason == 'insufficient_history'
    assert status.observed_bars == 3
