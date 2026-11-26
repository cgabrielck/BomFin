"""Alpaca entitlement probing; reports what the account can actually do.

A capability check is a measurement, not a promise. Each probe returns
what was observed, and the observed result is mapped onto the existing
`FeedCapabilities` contract. Nothing here infers an entitlement that was
not seen, and a failed probe is reported as unknown rather than denied.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from gabfin.contracts.subscriptions import FeedCapabilities, HistoryLimit
from gabfin.contracts.market import MarketSession, Timeframe, TimeUnit
from gabfin.providers.alpaca.feed_guard import (
    SIP,
    classify_status,
    sip_history_window,
)
from gabfin.providers.alpaca.history import (
    DATA_URL,
    MAX_PAGE_ROWS,
    OPTION_URL,
    Request,
    Response,
    Transport,
)

SOURCE = 'alpaca'


@dataclass
class ProbeResult:
    """The outcome of one probe."""

    name: str
    status: int
    available: bool | None
    detail: str = ''

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'status': self.status,
            'available': self.available,
            'detail': self.detail,
        }


@dataclass
class CapabilityReport:
    """Everything the probes observed."""

    checked_at: datetime
    probes: list[ProbeResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def probe(self, name: str) -> ProbeResult | None:
        for result in self.probes:
            if result.name == name:
                return result
        return None

    def as_dict(self) -> dict:
        return {
            'checked_at': self.checked_at.isoformat().replace('+00:00', 'Z'),
            'probes': [result.as_dict() for result in self.probes],
            'errors': list(self.errors),
        }


def probe_realtime_trades(transport: Transport, symbol: str = 'AAPL') -> ProbeResult:
    """Check whether recent IEX trades are readable."""
    request = Request(
        f'{DATA_URL}/v2/stocks/trades/latest',
        {'symbols': symbol, 'feed': 'iex'},
    )
    response = transport(request)
    if response.status == 200:
        payload = response.payload or {}
        trades = payload.get('trades') or {}
        available = bool(trades.get(symbol))
        return ProbeResult('iex_realtime_trades', response.status, available)
    reason = classify_status(response.status, response.message)
    return ProbeResult(
        'iex_realtime_trades',
        response.status,
        False if reason == 'entitlement' else None,
        response.message or reason,
    )


def probe_sip_history(
    transport: Transport,
    symbol: str = 'AAPL',
    *,
    now: datetime | None = None,
) -> ProbeResult:
    """Check whether SIP history is readable at the free tier's window."""
    moment = now or datetime.now(timezone.utc)
    safe = sip_history_window(moment)
    request = Request(
        f'{DATA_URL}/v2/stocks/{symbol}/bars',
        {
            'timeframe': '1Day',
            'start': (safe - timedelta(days=5)).isoformat().replace('+00:00', 'Z'),
            'end': safe.isoformat().replace('+00:00', 'Z'),
            'feed': SIP,
            'limit': 10,
        },
    )
    response = transport(request)
    if response.status == 200:
        payload = response.payload or {}
        bars = payload.get('bars') or {}
        available = bool(bars.get(symbol))
        return ProbeResult('sip_history', response.status, available)
    reason = classify_status(response.status, response.message)
    return ProbeResult(
        'sip_history',
        response.status,
        False if reason == 'entitlement' else None,
        response.message or reason,
    )


def probe_option_contracts(
    transport: Transport, underlying: str = 'SPY'
) -> ProbeResult:
    """Check whether option contract structure is readable.

    Structure only. A price probe would test an entitlement that the
    free tier does not offer, and would report a market as unavailable
    for the wrong reason.
    """
    request = Request(
        f'{OPTION_URL}/v1beta1/options/contracts',
        {'underlying_symbols': underlying, 'limit': 10},
    )
    response = transport(request)
    if response.status == 200:
        payload = response.payload or {}
        contracts = (
            payload.get('option_contracts') or payload.get('contracts') or []
        )
        return ProbeResult(
            'option_structure', response.status, bool(contracts), 'structure only'
        )
    reason = classify_status(response.status, response.message)
    return ProbeResult(
        'option_structure',
        response.status,
        False if reason == 'entitlement' else None,
        response.message or reason,
    )


def inspect_capabilities(
    transport: Transport,
    *,
    checked_at: datetime | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CapabilityReport:
    """Run every probe and report what was observed."""
    moment = checked_at or (clock() if clock else datetime.now(timezone.utc))
    report = CapabilityReport(checked_at=moment)
    probes = (
        ('iex_realtime_trades', lambda: probe_realtime_trades(transport)),
        ('sip_history', lambda: probe_sip_history(transport, now=now or moment)),
        ('option_structure', lambda: probe_option_contracts(transport)),
    )
    for name, run in probes:
        try:
            report.probes.append(run())
        except Exception as error:
            report.errors.append(f'{name}_probe_failed')
            report.probes.append(
                ProbeResult(name, 0, None, type(error).__name__)
            )
    return report


def to_feed_capabilities(report: CapabilityReport) -> FeedCapabilities:
    """Map the probe results onto the shared capability contract."""
    realtime = report.probe('iex_realtime_trades')
    history = report.probe('sip_history')
    options = report.probe('option_structure')

    if realtime is None or realtime.available is None:
        latency = 'unknown'
    elif realtime.available:
        latency = 'realtime'
    else:
        latency = 'unknown'

    permissions: list[str] = []
    for probe in (realtime, history, options):
        if probe is not None and probe.available is False:
            permissions.append(f'{probe.name}_unavailable')

    limits = []
    if history is not None and history.available:
        # The contract requires a timeframe on a bar limit. Alpaca serves
        # both daily and minute bars from SIP history.
        limits.append(
            HistoryLimit(
                channel='bar',
                timeframe=Timeframe(count=1, unit=TimeUnit.TRADING_DAY),
                max_records=MAX_PAGE_ROWS,
            )
        )
        limits.append(
            HistoryLimit(
                channel='bar',
                timeframe=Timeframe(count=1, unit=TimeUnit.MINUTE),
                max_records=MAX_PAGE_ROWS,
            )
        )

    return FeedCapabilities(
        schema_version='1.0',
        source=SOURCE,
        asset_classes=('equity',),
        sessions=(
            MarketSession.PRE_MARKET,
            MarketSession.REGULAR,
            MarketSession.POST_MARKET,
        ),
        latency_label=latency,
        max_subscriptions=None,
        history_limits=tuple(limits),
        checked_at=report.checked_at,
        permission_errors=tuple(permissions),
        sequence_rules=(),
    )
