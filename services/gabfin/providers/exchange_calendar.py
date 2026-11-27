"""Optional exchange-calendars exporter; the market host consumes plain snapshots.

Only regular sessions are exported. This does not certify PRE/POST or instrument
entitlement, and a reference exchange calendar is not listing-exchange metadata.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from gabfin.contracts.feed import CalendarSnapshot, SessionWindow


def exchange_calendar_snapshot(exchange, *, version, start: date, end: date):
    if type(start) is not date or type(end) is not date or not 0 <= (end - start).days <= 366:
        raise ValueError('Calendar export requires an ordered range of at most 367 dates')
    if exchange.name != 'XNYS':
        raise ValueError('Only the XNYS regular-session exporter is validated')
    zone = ZoneInfo('America/New_York')
    windows = []
    for label in exchange.sessions_in_range(start.isoformat(), end.isoformat()):
        windows.append(SessionWindow(schema_version='1.0', session='regular',
                                      start=exchange.session_open(label).to_pydatetime(),
                                      end=exchange.session_close(label).to_pydatetime()))
    return CalendarSnapshot(schema_version='1.0', calendar_id=exchange.name, version=version,
        coverage_start=datetime.combine(start, time(), tzinfo=zone),
        coverage_end=datetime.combine(end + timedelta(days=1), time(), tzinfo=zone), windows=windows)


def main():
    import argparse
    from importlib.metadata import version
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Export a finite XNYS regular-session calendar; requires gabfin[calendar]')
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        import exchange_calendars
        installed = version('exchange-calendars')
        if installed != '4.13.3':
            raise ValueError('Unvalidated calendar library version')
        # The public range API rejects a boundary before first_session (for
        # example Jan 1). Pad construction, then ask for the exact requested
        # coverage; holidays are still determined by the exchange library.
        exchange = exchange_calendars.get_calendar('XNYS',
            start=(args.start - timedelta(days=14)).isoformat(),
            end=(args.end + timedelta(days=14)).isoformat())
        snapshot = exchange_calendar_snapshot(exchange, version='exchange-calendars:' + installed,
                                               start=args.start, end=args.end)
        args.output.write_text(snapshot.model_dump_json(indent=2) + '\n', encoding='utf-8')
    except Exception:
        print('calendar_export_failed')
        return 2
    print('calendar_exported')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
