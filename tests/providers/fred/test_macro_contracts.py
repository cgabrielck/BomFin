"""The macro contract and the key's path out of the process."""
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from gabfin.contracts.macro import MacroPoint, MacroRelease, MacroSeries, MacroSnapshot
from gabfin.providers.fred.client import KEY_VARIABLE, FredClient, redact

KEY = 'super-secret-key-1234567890'


def point(**overrides) -> dict:
    payload = {
        'schema_version': '1.0',
        'series_id': 'UNRATE',
        'observation_date': '2026-01-15',
        'release_date': '2026-01-16',
        'value': '4.2',
        'units': 'Percent',
        'frequency': 'monthly',
        'vintage': None,
    }
    payload.update(overrides)
    return payload


def test_a_point_round_trips():
    parsed = MacroPoint.model_validate(point())
    assert MacroPoint.model_validate_json(parsed.model_dump_json()) == parsed


def test_a_release_before_the_period_is_refused():
    from pydantic import ValidationError

    try:
        MacroPoint.model_validate(point(release_date='2026-01-01'))
    except ValidationError:
        return
    raise AssertionError('a release before the period must be refused')


def test_a_series_definition_round_trips():
    series = MacroSeries(
        schema_version='1.0',
        series_id='UNRATE',
        title='Unemployment Rate',
        category='employment',
        frequency='monthly',
        units='Percent',
        seasonal_adjustment='Seasonally Adjusted',
    )
    assert MacroSeries.model_validate_json(series.model_dump_json()) == series


def test_a_release_carries_when_it_was_fetched():
    release = MacroRelease(
        series_id='UNRATE',
        release_date=date(2026, 1, 16),
        period=date(2026, 1, 15),
        value=Decimal('4.2'),
        units='Percent',
        frequency='monthly',
        fetched_at=datetime(2026, 1, 16, 12, 0, tzinfo=timezone.utc),
    )
    assert release.fetched_at.tzinfo is not None


def test_a_snapshot_groups_its_points():
    snapshot = MacroSnapshot(
        observed_at=datetime(2026, 1, 16, 12, 0, tzinfo=timezone.utc),
        points=(
            MacroPoint.model_validate(point()),
            MacroPoint.model_validate(point(series_id='PAYEMS', units='Thousands of Persons')),
        ),
    )
    assert set(snapshot.by_series()) == {'UNRATE', 'PAYEMS'}


def test_the_key_is_not_in_the_client_when_it_is_not_configured():
    client = FredClient(key=None)
    assert client.configured is False


def test_the_key_is_redacted_from_anything_it_might_be_logged_in():
    """The redaction is the only thing standing between the key and a log."""
    candidates = [
        f'https://api.stlouisfed.org/fred/series/observations?api_key={KEY}',
        f'api_key={KEY}',
        KEY,
    ]
    for text in candidates:
        assert KEY not in redact(text, KEY)


def test_a_log_line_that_would_carry_the_key_can_be_scrubbed():
    record = logging.LogRecord(
        name='fred',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=f'requesting with api_key={KEY}',
        args=(),
        exc_info=None,
    )
    scrubbed = redact(record.getMessage(), KEY)
    assert KEY not in scrubbed


def test_the_key_variable_name_is_the_documented_one():
    assert KEY_VARIABLE == 'FRED_API_KEY'
