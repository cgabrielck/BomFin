"""Offline verification of planner scope, wheel/source and archived test evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree
from zipfile import ZipFile

artifact = Path(__file__).resolve().parent
workspace = artifact.parents[3]
repo = workspace / '.worktrees/gabfin-s01'
base = '87e295311fd7ef9dbb77c930084b15dc1b4dff23'
changed = {'services/gabfin/market/__init__.py', 'services/gabfin/market/subscriptions.py',
           'services/gabfin/providers/futu/symbols.py', 'tests/gabfin/test_symbols.py',
           'tests/gabfin/test_subscription_planner.py'}

def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo).decode('utf-8').strip()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before = json.loads((artifact / 'before.json').read_text(encoding='utf-8'))
unrelated = [p for p, sha in before['files'].items()
             if not (repo / p).is_file() or digest(repo / p) != sha]
assert not unrelated, unrelated  # This unit adds files only.
assert digest(repo / 'web/package-lock.json') == before['lock']
head = git('rev-parse', 'HEAD')
scope = set(git('diff', '--cached', '--name-only').splitlines()) if head == base else set(git('diff', '--name-only', base, head).splitlines())
assert scope == changed, scope
assert git('branch', '--show-current') == 'codex/s01-source-baseline'
assert not git('diff', '--name-only')
git('diff', '--cached', '--check')
wheel = artifact / 'wheels/gabfin-0.1.0-py3-none-any.whl'
with ZipFile(wheel) as archive:
    source_files = list((repo / 'services/gabfin').rglob('*.py'))
    for source in source_files:
        name = source.relative_to(repo / 'services').as_posix()
        assert archive.read(name).replace(b'\r\n', b'\n') == source.read_bytes().replace(b'\r\n', b'\n'), name
demo = json.loads((artifact / 'demo.json').read_text(encoding='utf-8'))
assert demo['synthetic_only'] and demo['apply_allowed'] and demo['no_futu_sdk'] and demo['no_pandas']
assert demo['latency_label_unchanged'] == 'unknown'
assert demo['unsubscribe_symbols'] == ['US.AAPL']
assert set(demo['accepted_symbols']) == {'US.MSFT', 'US.AAPL261218C350000', 'US.AAPL261218P350000'}
reviews = json.loads((artifact / 'reviews.json').read_text())
assert reviews['standards']['final_blocking'] == 0 and reviews['spec']['final_unresolved'] == 0
cases = list(ElementTree.parse(artifact / 'full.xml').getroot().iter('testcase'))
failed = sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
skipped = sum(c.find('skipped') is not None for c in cases)
assert failed == 0 and len(cases) - skipped == 1959 and skipped == 4
gabfin = sum(c.attrib.get('classname', '').startswith('tests.gabfin.') for c in cases)
assert gabfin == 751, gabfin
result = {'base': base, 'head': head, 'scope': sorted(scope),
          'all_previous_tracked_files_preserved': not unrelated, 'original_lock_preserved': True,
          'wheel_matches_python_source_files': len(source_files), 'wheel_sha256': digest(wheel),
          'clean_wheel_demo_verified': True, 'independent_review_complete': True,
          'full_passed': len(cases) - skipped, 'full_skipped': skipped, 'full_failed': failed,
          'gabfin_passed': gabfin, 'source_status': git('status', '--short')}
(artifact / 'verification.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
