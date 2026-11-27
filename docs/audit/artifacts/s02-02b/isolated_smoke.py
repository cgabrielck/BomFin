"""Consumer smoke from outside checkout, with isolated interpreter imports."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

import gabfin
from gabfin.contracts.events import MarketEvent
from gabfin.contracts.market import Bar, Instrument, QuoteSnapshot, TradeTick

schemas = [model.model_json_schema(mode="serialization") for model in (Instrument, QuoteSnapshot, Bar)]
adapter = TypeAdapter(MarketEvent)
schemas.append(adapter.json_schema(mode="serialization"))
for schema in schemas:
    Draft202012Validator.check_schema(schema)

payload = TradeTick(
    schema_version="1.0", instrument_id="11111111-1111-4111-8111-111111111111",
    price="100.15", quantity="0.1", trade_id=None,
)
event = adapter.validate_python({
    "schema_version": "1.0", "event_id": "33333333-3333-4333-8333-333333333333",
    "instrument_id": payload.instrument_id,
    "event_at": "2026-11-25T14:30:00Z", "received_at": "2026-11-25T14:30:00.100Z",
    "available_at": "2026-11-25T14:30:00.200Z", "source": "smoke-feed",
    "source_seq": "900719925474099300001", "dedup_key": "smoke:trade:1", "kind": "trade", "payload": payload,
})
wire = adapter.dump_json(event)
Draft202012Validator(schemas[-1]).validate(json.loads(wire))
assert adapter.validate_json(wire) == event
assert not any(name == "backend" or name.startswith("backend.") for name in sys.modules)
result = {"isolated_import": str(Path(gabfin.__file__).resolve()), "schemas_checked": len(schemas), "market_event_roundtrip": True, "backend_imported": False}
Path(__file__).with_name('isolated-smoke.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
print(json.dumps(result))
