"""The FRED macro provider; a separate plane from the quote path.

Macro data never enters the quote channel. A macro series is published
on its own schedule, and mixing it into the quote path would make the
quote path wait on a release calendar.
"""
from gabfin.providers.fred.client import (
    FredClient,
    MacroError,
    MacroKeyMissing,
    parse_value,
    read_key,
    redact,
)
from gabfin.providers.fred.fetch import (
    as_of,
    latest,
    release_date_of,
    to_point,
    to_points,
)
from gabfin.providers.fred.series import BUILTIN, by_category, describe, ids, known

__all__ = [
    'BUILTIN',
    'FredClient',
    'MacroError',
    'MacroKeyMissing',
    'as_of',
    'by_category',
    'describe',
    'ids',
    'known',
    'latest',
    'parse_value',
    'read_key',
    'redact',
    'release_date_of',
    'to_point',
    'to_points',
]
