from datetime import date, datetime, timezone
from types import SimpleNamespace

from gabfin.providers.exchange_calendar import exchange_calendar_snapshot


class Exchange:
    name = 'XNYS'
    def sessions_in_range(self, start, end):
        return ['2026-11-27']  # Nov 26 is closed in this external calendar.
    def session_open(self, label):
        return SimpleNamespace(to_pydatetime=lambda: datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc))
    def session_close(self, label):
        return SimpleNamespace(to_pydatetime=lambda: datetime(2026, 11, 27, 18, tzinfo=timezone.utc))


def test_exchange_snapshot_preserves_holiday_and_early_close_without_weekday_fallback():
    result = exchange_calendar_snapshot(Exchange(), version='external-fixture',
                                         start=date(2026, 11, 26), end=date(2026, 11, 27))
    assert result.calendar_id == 'XNYS'
    assert len(result.windows) == 1
    assert result.windows[0].start.hour == 14 and result.windows[0].start.minute == 30
    assert result.windows[0].end.hour == 18
    assert result.windows[0].session == 'regular'
