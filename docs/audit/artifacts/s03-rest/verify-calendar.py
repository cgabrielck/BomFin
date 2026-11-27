"""Cross-check exported calendar against independent known exchange examples."""
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from gabfin.contracts.feed import CalendarSnapshot

folder = Path(__file__).resolve().parent
snapshot = CalendarSnapshot.model_validate_json((folder / 'calendar-XNYS-2026.json').read_bytes())
zone = ZoneInfo('America/New_York')
windows = {window.start.astimezone(zone).date().isoformat(): window for window in snapshot.windows}
assert '2026-11-26' not in windows
assert windows['2026-11-27'].end.isoformat() == '2026-11-27T18:00:00+00:00'
assert windows['2026-03-09'].start.isoformat() == '2026-03-09T13:30:00+00:00'
assert windows['2026-11-02'].start.isoformat() == '2026-11-02T14:30:00+00:00'
assert snapshot.version == 'exchange-calendars:4.13.3'
result = dict(version=snapshot.version, calendar_id=snapshot.calendar_id, sessions=len(windows),
              holiday_verified=True, early_close_verified=True, dst_examples_verified=True,
              reference='https://www.nyse.com/trade/hours-calendars')
(folder / 'calendar-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
