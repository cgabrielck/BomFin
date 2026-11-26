"""The built-in macro series and their metadata.

The set is fixed on purpose. A macro panel that offers a free-text
series id lets a user compare a release that has not happened yet, or
a series with a different unit, and then believe the comparison.
"""
from gabfin.contracts.macro import MacroCategory, MacroFrequency, MacroSeries

#: The series the dashboard knows about, keyed by their FRED id.
BUILTIN: dict[str, MacroSeries] = {}


def _add(
    series_id: str,
    title: str,
    category: MacroCategory,
    frequency: MacroFrequency,
    units: str,
    seasonal_adjustment: str | None = None,
) -> None:
    BUILTIN[series_id] = MacroSeries(
        schema_version='1.0',
        series_id=series_id,
        title=title,
        category=category,
        frequency=frequency,
        units=units,
        seasonal_adjustment=seasonal_adjustment,
    )


# Rates.
_add('DGS2', '2-Year Treasury Constant Maturity Rate', 'rates', 'daily', 'Percent')
_add('DGS10', '10-Year Treasury Constant Maturity Rate', 'rates', 'daily', 'Percent')
_add('T10Y2Y', '10-Year Treasury Minus 2-Year Treasury Yield', 'rates', 'daily', 'Percent')
_add('DFEDTARU', 'Federal Funds Target Range Upper Limit', 'rates', 'daily', 'Percent')
_add('DFEDTARL', 'Federal Funds Target Range Lower Limit', 'rates', 'daily', 'Percent')
_add('SOFR', 'Secured Overnight Financing Rate', 'rates', 'daily', 'Percent')
_add('RRPONTSYD', 'Effective Rate of Overnight Repo', 'rates', 'daily', 'Percent')

# Inflation.
_add('CPIAUCSL', 'Consumer Price Index for All Urban Consumers', 'inflation', 'monthly', 'Index 1982-1984=100', 'Seasonally Adjusted')
_add('PCEPILFE', 'Core PCE Price Index', 'inflation', 'monthly', 'Index 2017=100', 'Seasonally Adjusted')
_add('CPIREL', 'CPI All Items Relative to 2015', 'inflation', 'monthly', 'Ratio')

# Employment.
_add('UNRATE', 'Unemployment Rate', 'employment', 'monthly', 'Percent', 'Seasonally Adjusted')
_add('PAYEMS', 'All Employees, Total Nonfarm', 'employment', 'monthly', 'Thousands of Persons', 'Seasonally Adjusted')
_add('JTSJOL', 'Job Openings: Total Nonfarm', 'employment', 'monthly', 'Thousands of Persons', 'Seasonally Adjusted')
_add('CIVPART', 'Civilian Labor Force Participation Rate', 'employment', 'monthly', 'Percent', 'Seasonally Adjusted')

# Risk.
_add('NFCI', 'Chicago Fed National Financial Conditions Index', 'risk', 'weekly', 'Index')
_add('BAMLH0A0HYM2', 'ICE BofA US High Yield Index Option-Adjusted Spread', 'risk', 'daily', 'Percent')
_add('STLFSI4', 'St. Louis Fed Financial Stress Index', 'risk', 'daily', 'Index')


def describe(series_id: str) -> MacroSeries:
    """The metadata of a built-in series."""
    try:
        return BUILTIN[series_id]
    except KeyError:
        raise KeyError(f'{series_id} is not a built-in macro series') from None


def known(series_id: str) -> bool:
    return series_id in BUILTIN


def ids() -> tuple[str, ...]:
    """The ids of the built-in series."""
    return tuple(BUILTIN)


def by_category(category: MacroCategory) -> tuple[str, ...]:
    """The ids of the built-in series in one category."""
    return tuple(
        key for key, series in BUILTIN.items() if series.category == category
    )
