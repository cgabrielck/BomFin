"""Verify scope, old declarations, wheel and recorded test evidence."""
import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT / '.worktrees/gabfin-s01'
HERE = Path(__file__).resolve().parent
before = json.loads((HERE / 'before.json').read_text(encoding='utf-8'))
common = 'services/gabfin/contracts/common.py'
expected = {
    common, 'services/gabfin/contracts/market.py', 'services/gabfin/contracts/events.py',
    'tests/gabfin/conftest.py', 'tests/gabfin/test_market_contracts.py', 'tests/gabfin/test_market_events.py',
}
for name, digest in before['tracked_sha256'].items():
    if name != common:
        assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest, name

def declarations(text):
    result = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = ast.dump(node, include_attributes=False)
    return result

old_common = subprocess.check_output(['git', 'show', before['head'] + ':' + common], cwd=REPO).decode('utf-8')
old_declarations = declarations(old_common)
new_declarations = declarations((REPO / common).read_text(encoding='utf-8'))
assert all(new_declarations.get(key) == value for key, value in old_declarations.items())
assert hashlib.sha256((REPO / 'web/package-lock.json').read_bytes()).hexdigest() == before['lock_sha256']
assert not (REPO / 'backend/data/trade_journal.json').exists()
assert (HERE / 'legacy-test-generated-journal.json').exists()
assert not (REPO / 'backend/data/worker.pid').exists()

baseline_dir = ROOT / 'docs/audit/artifacts/s01-01b'
baseline = json.loads((baseline_dir / 'results.json').read_text(encoding='utf-8'))
for name, digest in baseline['artifacts_sha256'].items():
    assert hashlib.sha256((baseline_dir / name).read_bytes()).hexdigest() == digest, name
previous_dir = ROOT / 'docs/audit/artifacts/s02-02a'
previous = json.loads((previous_dir / 'verification.json').read_text(encoding='utf-8'))
assert hashlib.sha256(next((previous_dir / 'wheels').glob('*.whl')).read_bytes()).hexdigest() == previous['wheel_sha256']

results = {}
for name in ('market-red-final', 'market-green', 'market-final', 'events-red', 'events-source-red', 'events-green', 'contracts-green', 'contracts-final', 'full-regression', 'full-final'):
    suite = ET.parse(HERE / (name + '.xml')).getroot().find('testsuite')
    counts = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    counts['seconds'] = float(suite.attrib['time'])
    results[name] = counts
assert results['market-red-final']['failures'] == 77
assert results['market-green']['passed'] == 76 and results['market-green']['failures'] == 1
assert results['market-final']['passed'] == 77
assert results['events-red']['failures'] == 33 and results['events-source-red']['failures'] == 2
assert results['events-green']['passed'] == 35
assert results['contracts-final']['passed'] == 204 and results['contracts-final']['failures'] == 0
assert results['full-final']['passed'] == 1412 and results['full-final']['skipped'] == 4
assert results['full-final']['failures'] == results['full-final']['errors'] == 0
smoke = json.loads((HERE / 'isolated-smoke.json').read_text(encoding='utf-8'))
assert smoke['schemas_checked'] == 4 and smoke['market_event_roundtrip'] and not smoke['backend_imported']
wheel = next((HERE / 'wheels').glob('*.whl'))
with zipfile.ZipFile(wheel) as package:
    names = package.namelist()
    assert all(name.startswith(('gabfin/', 'gabfin-0.1.0.dist-info/')) for name in names)
    for path in (REPO / 'services/gabfin').rglob('*.py'):
        name = path.relative_to(REPO / 'services').as_posix()
        assert package.read(name) == path.read_bytes(), name
changed = set(subprocess.check_output(['git', '-c', 'core.safecrlf=false', 'diff', '--name-only', before['head']], cwd=REPO, text=True).splitlines())
untracked = set(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=REPO, text=True).splitlines())
assert changed | (untracked - {'web/package-lock.json'}) == expected, (changed, untracked)
subprocess.run(['git', '-c', 'core.safecrlf=false', 'diff', '--check'], cwd=REPO, check=True)
final_log = (HERE / 'full-final.log').read_text(encoding='utf-8')
report = {
    'base_head': before['head'],
    'current_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
    'source_paths': sorted(expected), 'unchanged_original_files': len(before['tracked_sha256']) - 1,
    'old_common_declarations_preserved': len(old_declarations), 'lockfile_preserved': True,
    'baseline_evidence_preserved': True, 'new_cases': 118, 'contract_cases': 204,
    'results': results, 'final_console_seconds': float(re.findall(r'in ([0-9.]+)s', final_log)[-1]),
    'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'wheel_matches_source': True,
    'schema_smoke': smoke, 'legacy_journal_archived': True, 'worker_pid_present': False,
    'known_skips': '4 optional Postgres cases, missing psycopg',
    'known_warning': 'Pandas4Warning: backend/research/comps.py:26',
}
(HERE / 'verification.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps({key: value for key, value in report.items() if key not in ('source_paths', 'results', 'schema_smoke')}, ensure_ascii=False))
print(json.dumps(results['full-final']))
