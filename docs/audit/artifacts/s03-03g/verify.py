"""Offline scope, preservation, packaging, test and review evidence checks."""
import hashlib
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree
from zipfile import ZipFile

artifact = Path(__file__).resolve().parent
workspace = artifact.parents[3]
repo = workspace / '.worktrees/gabfin-s01'
base = 'a8d23d575baab94420595ca5cddf12255fb40ebc'
changed = {'services/gabfin/market/stream.py', 'services/gabfin/providers/futu/adapter.py',
           'services/gabfin/providers/futu/quote_push.py', 'services/gabfin/providers/futu/quote_worker.py',
           'services/gabfin/providers/futu/symbols_wire.py', 'services/gabfin/providers/futu/symbols.py',
           'tests/gabfin/test_futu_quote_adapter.py', 'tests/gabfin/test_futu_quote_callback.py',
           'tests/gabfin/test_quote_stream.py'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo).decode('utf-8').strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = json.loads((artifact / 'before.json').read_text(encoding='utf-8-sig'))
unrelated = [name for name, sha in before['files'].items() if name not in changed
             and (not (repo / name).is_file() or digest(repo / name) != sha)]
assert not unrelated, unrelated
assert digest(repo / 'web/package-lock.json') == before['lock']
assert not before['journal_existed'] and not (repo / 'backend/data/trade_journal.json').exists()
assert (artifact / 'legacy-test-generated-journal.json').is_file()
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
assert demo == dict(accepted=1000, coalesced=999, last='1000', age_ms=2000,
                    entitlement='unknown', no_sdk_in_host=True)
reviews = json.loads((artifact / 'reviews.json').read_text(encoding='utf-8'))
assert reviews['standards']['final_unresolved'] == 0 and reviews['spec']['final_unresolved'] == 0
cases = list(ElementTree.parse(artifact / 'full-release.xml').getroot().iter('testcase'))
failed = sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
skipped = sum(c.find('skipped') is not None for c in cases)
assert failed == 0 and len(cases) - skipped == 2021 and skipped == 4
gabfin = sum(c.attrib.get('classname', '').startswith('tests.gabfin.') for c in cases)
assert gabfin == 813
live = json.loads((artifact / 'live.json').read_text(encoding='utf-8'))
assert not live['running'] and live['error'] is None and live['failure'] is None
assert live['stats']['accepted'] > 0 and live['result']['cleanup'] == 'unsubscribed'
assert live['result']['closed'] and not live['result']['errors']
metadata = json.loads((artifact / 'post-cleanup-metadata.json').read_text(encoding='utf-8'))['metadata']
assert metadata['total_used_quota'] == 0 and metadata['remaining_quota'] == 100
processes = json.loads((artifact / 'post-process.json').read_text(encoding='utf-8'))
assert processes['sdk_workers'] == 0 and processes['listener_count'] == 1
result = dict(base=base, head=head, scope=sorted(scope), unrelated_tracked_preserved=True,
              original_lock_preserved=True, legacy_mock_journal_archived=True,
              wheel_matches_python_source_files=len(source_files), wheel_sha256=digest(wheel),
              clean_demo_verified=True, independent_review_complete=True,
              full_passed=len(cases)-skipped, full_skipped=skipped, full_failed=failed,
              gabfin_passed=gabfin, live_failure=live['failure'], live_accepted=live['stats']['accepted'],
              source_status=git('status', '--short'))
(artifact / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
