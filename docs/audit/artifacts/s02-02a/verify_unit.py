"""Verify the new slice and preservation of legacy source/evidence."""
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
expected = {
    'pyproject.toml', 'services/gabfin/__init__.py', 'services/gabfin/contracts/__init__.py',
    'services/gabfin/contracts/common.py', 'services/gabfin/contracts/intent.py', 'tests/gabfin/test_contracts.py',
}
for name, digest in before['tracked_sha256'].items():
    assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256((REPO / 'web/package-lock.json').read_bytes()).hexdigest() == before['lock_sha256']
assert not (REPO / 'backend/data/trade_journal.json').exists()
assert (HERE / 'legacy-test-generated-journal.json').exists()
assert not (REPO / 'backend/data/worker.pid').exists()
baseline_dir = ROOT / 'docs/audit/artifacts/s01-01b'
baseline = json.loads((baseline_dir / 'results.json').read_text(encoding='utf-8'))
for name, digest in baseline['artifacts_sha256'].items():
    assert hashlib.sha256((baseline_dir / name).read_bytes()).hexdigest() == digest, name

results = {}
for name in ('common-red', 'common-green', 'intent-red', 'contracts-green', 'full-regression', 'epoch-string-red', 'contracts-final', 'full-final'):
    suite = ET.parse(HERE / (name + '.xml')).getroot().find('testsuite')
    counts = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
    counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    counts['seconds'] = float(suite.attrib['time'])
    results[name] = counts
assert results['common-red']['failures'] == 41
assert results['common-green']['passed'] == 41
assert results['intent-red']['failures'] == 42 and results['intent-red']['passed'] == 41
assert results['contracts-green']['passed'] == 83 and results['contracts-green']['failures'] == 0
assert results['full-regression']['passed'] == 1291 and results['full-regression']['skipped'] == 4
assert results['full-regression']['failures'] == results['full-regression']['errors'] == 0
assert results['epoch-string-red']['failures'] == 3 and results['epoch-string-red']['passed'] == 6
assert results['contracts-final']['passed'] == 86 and results['contracts-final']['failures'] == 0
assert results['full-final']['passed'] == 1294 and results['full-final']['skipped'] == 4
assert results['full-final']['failures'] == results['full-final']['errors'] == 0
assert 'isolated_import_and_serialization=passed' in (HERE / 'isolated-import.log').read_text(encoding='utf-8')
wheel = next((HERE / 'wheels').glob('gabfin-*.whl'))
with zipfile.ZipFile(wheel) as package:
    wheel_files = package.namelist()
    assert all(name.startswith(('gabfin/', 'gabfin-0.1.0.dist-info/')) for name in wheel_files)
    for name in expected:
        if name.startswith('services/') and name.endswith('.py'):
            assert package.read(name.removeprefix('services/')) == (REPO / name).read_bytes(), name
final_log = (HERE / 'full-final.log').read_text(encoding='utf-8')
console_seconds = float(re.findall(r'in ([0-9.]+)s', final_log)[-1])

changed = set(subprocess.check_output(['git', 'diff', '--name-only', before['head']], cwd=REPO, text=True).splitlines())
untracked = set(subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=REPO, text=True).splitlines())
assert (changed | (untracked - {'web/package-lock.json'})) == expected, (changed, untracked)
assert changed <= expected
subprocess.run(['git', '-c', 'core.safecrlf=false', 'diff', '--check'], cwd=REPO, check=True)
report = {
    'base_head': before['head'],
    'current_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
    'source_paths': sorted(expected), 'protected_legacy_files': len(before['tracked_sha256']),
    'legacy_files_unchanged': True, 'lockfile_preserved': True, 'baseline_evidence_preserved': True,
    'results': results, 'full_regression_console_seconds': console_seconds,
    'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'wheel_matches_current_source': True,
    'known_warning': 'Pandas4Warning: backend/research/comps.py:26',
    'known_skips': '4 optional Postgres cases: psycopg is not installed',
    'user_decision': 'StrategyIntent uses long/short plus open/reduce/close position_effect',
    'journal_side_effect_archived': True, 'worker_pid_present': False,
    'source_sha256': {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in sorted(expected)},
}
(HERE / 'verification.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
print(json.dumps({key: value for key, value in report.items() if key not in ('results', 'source_sha256', 'source_paths')}, ensure_ascii=False))
print(json.dumps(results, ensure_ascii=False))
