"""Fetching macro observations into contracts.

FRED's raw observation carries a `realtime_start` and `realtime_end`,
which is when the observation was published. That is the release date,
and it is what makes a point-in-time backtest possible: an observation
of January that was published in March must not be used by a backtest
that trades in February.

The release date is therefore required. An observation without one is
refused rather than defaulted, because a defaulted release date turns a
look-ahead bug into a silent one.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from gabfin.contracts.macro import MacroFrequency, MacroPoint
from gabfin.providers.fred.client import MacroError, parse_value
from gabfin.providers.fred.series import BUILTIN, describe


def release_date_of(observation: dict) -> date | None:
    """The date an observation was published, or None if FRED omitted it."""
    stamp = observation.get('realtime_start')
    if not stamp:
        return None
    return _parse_date(str(stamp))


def observation_date_of(observation: dict) -> date:
    """The period an observation describes."""
    stamp = observation.get('date')
    if not stamp:
        raise MacroError('A macro observation has no date')
    return _parse_date(str(stamp))


def _parse_date(text: str) -> date:
    # FRED writes dates as YYYY-MM-DD.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise MacroError(f'Unreadable date: {text[:10]}') from None


def to_point(
    observation: dict,
    *,
    series_id: str | None = None,
    units: str | None = None,
    frequency: MacroFrequency | None = None,
    vintage: datetime | None = None,
) -> MacroPoint | None:
    """Convert one raw observation into a contract point.

    Returns None for an observation with no value, which is not an error:
    FRED publishes the period before the number, and a missing number is
    information rather than a failure.
    """
    identifier = series_id or str(observation.get('series_id') or '')
    if identifier in BUILTIN:
        defined = describe(identifier)
        default_units = defined.units
        default_frequency = defined.frequency
    else:
        default_units = units or ''
        default_frequency = frequency or 'monthly'

    value = parse_value(observation.get('value'))
    if value is None:
        return None

    release = release_date_of(observation)
    if release is None:
        raise MacroError(
            f'{identifier}: the observation has no release date; a macro '
            'point without one cannot be used in a backtest'
        )
    observed = observation_date_of(observation)
    # A release date before the observation period would be wrong, and
    # the contract refuses it. Clamping here would hide a real defect.
    if release < observed:
        raise MacroError(
            f'{identifier}: the release date {release} precedes the '
            f'observation period {observed}'
        )

    return MacroPoint(
        schema_version='1.0',
        series_id=identifier,
        observation_date=observed,
        release_date=release,
        value=value,
        units=units if units is not None else default_units,
        frequency=frequency if frequency is not None else default_frequency,
        vintage=vintage,
    )


def to_points(observations: list[dict], *, series_id: str | None = None) -> tuple[MacroPoint, ...]:
    """Convert a run of raw observations, dropping the ones with no value."""
    points = []
    for observation in observations:
        point = to_point(observation, series_id=series_id)
        if point is not None:
            points.append(point)
    return tuple(points)


def latest(points: tuple[MacroPoint, ...]) -> MacroPoint | None:
    """The most recently released point of a series."""
    if not points:
        return None
    return max(points, key=lambda point: (point.release_date, point.observation_date))


def as_of(points: tuple[MacroPoint, ...], when: date) -> tuple[MacroPoint, ...]:
    """The points that were already released on a given date.

    This is the point-in-time filter a backtest needs: an observation
    released after the date being traded is not yet knowable.
    """
    return tuple(
        point for point in points if point.release_date <= when
    )
