"""Macro points, their release dates and the point-in-time filter."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from gabfin.contracts.macro import MacroPoint, MacroSeries
from gabfin.providers.fred.client import MacroError
from gabfin.providers.fred.fetch import (
    as_of,
    latest,
    release_date_of,
    to_point,
    to_points,
)
from gabfin.providers.fred.series import BUILTIN, by_category, describe, ids, known


def observation(value='1.5', date_stamp='2026-01-15', release='2026-01-16'):
    return {
        'realtime_start': release,
        'realtime_end': release,
        'date': date_stamp,
        'value': value,
    }


def test_a_release_date_is_taken_from_the_realtime_stamp():
    assert release_date_of(observation()) == date(2026, 1, 16)


def test_a_point_keeps_its_release_date():
    point = to_point(observation(), series_id='UNRATE')
    assert point.release_date == date(2026, 1, 16)
    assert point.observation_date == date(2026, 1, 15)
    assert point.value == Decimal('1.5')


def test_a_point_without_a_release_date_is_refused():
    raw = observation()
    raw.pop('realtime_start')
    with pytest.raises(MacroError) as error:
        to_point(raw, series_id='UNRATE')
    assert 'release date' in str(error.value)


def test_a_point_released_before_its_period_is_refused():
    with pytest.raises(MacroError):
        to_point(observation(release='2026-01-01'), series_id='UNRATE')


def test_a_observation_without_a_value_produces_no_point():
    assert to_point(observation(value='.'), series_id='UNRATE') is None
    assert to_point(observation(value=''), series_id='UNRATE') is None


def test_a_run_of_observations_drops_the_empty_ones():
    points = to_points(
        [observation('1.0'), observation('.'), observation('3.0')],
        series_id='UNRATE',
    )
    assert len(points) == 2
    assert points[0].value == Decimal('1.0')
    assert points[1].value == Decimal('3.0')


def test_a_point_inherits_the_units_of_a_built_in_series():
    point = to_point(observation(), series_id='UNRATE')
    assert point.units == 'Percent'
    assert point.frequency == 'monthly'


def test_the_latest_point_is_the_most_recently_released():
    points = to_points(
        [
            observation('1.0', '2026-01-15', '2026-01-16'),
            observation('2.0', '2025-12-15', '2026-02-01'),
        ],
        series_id='UNRATE',
    )
    assert latest(points).release_date == date(2026, 2, 1)


def test_the_point_in_time_filter_excludes_unreleased_observations():
    points = to_points(
        [
            observation('1.0', '2026-01-15', '2026-01-16'),
            observation('2.0', '2026-02-15', '2026-03-01'),
        ],
        series_id='UNRATE',
    )
    # On the sixteenth of February, the March release is not yet knowable.
    known = as_of(points, date(2026, 2, 16))
    assert len(known) == 1
    assert known[0].value == Decimal('1.0')


def test_the_contract_refuses_a_release_before_the_period():
    with pytest.raises(ValidationError):
        MacroPoint(
            schema_version='1.0',
            series_id='UNRATE',
            observation_date=date(2026, 1, 15),
            release_date=date(2026, 1, 1),
            value=Decimal('1'),
            units='Percent',
            frequency='monthly',
        )


def test_the_built_in_series_cover_the_expected_families():
    for series_id in (
        'DGS2',
        'DGS10',
        'T10Y2Y',
        'DFEDTARU',
        'DFEDTARL',
        'SOFR',
        'RRPONTSYD',
        'CPIAUCSL',
        'PCEPILFE',
        'CPIREL',
        'UNRATE',
        'PAYEMS',
        'JTSJOL',
        'CIVPART',
        'NFCI',
        'BAMLH0A0HYM2',
        'STLFSI4',
    ):
        assert known(series_id), series_id


def test_the_series_can_be_grouped_by_category():
    assert 'UNRATE' in by_category('employment')
    assert 'DGS10' in by_category('rates')
    assert 'NFCI' in by_category('risk')
    assert 'CPIAUCSL' in by_category('inflation')


def test_an_unknown_series_is_refused():
    with pytest.raises(KeyError):
        describe('NOT_A_SERIES')


def test_every_built_in_series_is_described():
    for series_id in ids():
        assert isinstance(describe(series_id), MacroSeries)
    assert len(BUILTIN) == len(ids())
