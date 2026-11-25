"""Recheck local source, evidence, packaging and scoped changes; never contact OpenD."""
import hashlib
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree
from zipfile import ZipFile

artifact = Path(__file__).resolve().parent
workspace = artifact.parents[3]
repo = workspace / '.worktrees/gabfin-s01'
base = '953b5d274a10cb7aeaf84ae071f0bcadc1e26693'
changed = {'services/gabfin/providers/futu/history_wire.py', 'services/gabfin/providers/futu/history.py',
           'services/gabfin/providers/futu/runner.py', 'services/gabfin/providers/futu/worker.py',
           'tests/gabfin/test_history_smoke.py'}

def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo).decode('utf-8').strip()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before = json.loads((artifact / 'before.json').read_text(encoding='utf-8'))
unrelated = [p for p, sha in before['files'].items()
             if p not in changed and (not (repo / p).is_file() or digest(repo / p) != sha)]
assert not unrelated, unrelated
assert digest(repo / 'web/package-lock.json') == before['lock']
head = git('rev-parse', 'HEAD')
scope = set(git('diff', '--cached', '--name-only').splitlines()) if head == base else set(git('diff', '--name-only', base, head).splitlines())
assert scope == changed, scope
assert git('branch', '--show-current') == 'codex/s01-source-baseline'
assert not git('diff', '--name-only'), 'Unstaged source changes'
git('diff', '--cached', '--check')

wheel = artifact / 'wheels/gabfin-0.1.0-py3-none-any.whl'
with ZipFile(wheel) as archive:
    source_files = list((repo / 'services/gabfin').rglob('*.py'))
    for source in source_files:
        relative = source.relative_to(repo / 'services').as_posix()
        assert archive.read(relative).replace(b'\r\n', b'\n') == source.read_bytes().replace(b'\r\n', b'\n'), relative
    metadata = archive.read('gabfin-0.1.0.dist-info/METADATA').decode()
    assert 'tzdata==2026.6' in metadata and 'win32' in metadata

from gabfin.providers.futu.runner import _validate
live = json.loads((artifact / 'live-history-final.json').read_text(encoding='utf-8-sig'))
assert _validate(live, 'history_smoke') == live
assert live['metadata']['cleanup'] == 'closed' and not live['metadata']['errors']
clean = json.loads((artifact / 'clean-wheel-verification.json').read_text())
assert all(clean.values())
process = json.loads((artifact / 'process-cleanup-final.json').read_text(encoding='utf-8-sig'))
assert process == {'metadata_exit': 0, 'historical_exit': 0, 'sdk_workers_remaining': 0}
root = ElementTree.parse(artifact / 'full.xml').getroot()
cases = list(root.iter('testcase'))
failed = sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
skipped = sum(c.find('skipped') is not None for c in cases)
assert failed == 0 and len(cases) - skipped == 1902 and skipped == 4
gabfin = sum(c.attrib.get('classname', '').startswith('tests.gabfin.') for c in cases)
assert gabfin == 694, gabfin
result = {'base': base, 'head': head, 'scope': sorted(scope),
          'unrelated_tracked_changes': unrelated, 'original_lock_preserved': True,
          'wheel_matches_python_source_files': len(source_files), 'wheel_sha256': digest(wheel),
          'clean_wheel_verified': True, 'live_result_revalidated': True,
          'full_passed': len(cases) - skipped, 'full_skipped': skipped, 'full_failed': failed,
          'gabfin_passed': gabfin, 'source_status': git('status', '--short')}
(artifact / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
