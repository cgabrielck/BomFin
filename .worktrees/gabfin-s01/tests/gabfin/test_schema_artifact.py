def test_schema_generated_from_python():
 import json
 from pathlib import Path
 from gabfin.contracts.schema import generate_schema
 from jsonschema import Draft202012Validator
 schema=generate_schema();Draft202012Validator.check_schema(schema)
 assert json.loads(Path('schemas/gabfin-1.0.json').read_text())==schema
 assert {'ModelRequest','ModelResult','Principal','JobLease','HarnessProposal'}<=schema['$defs'].keys()
