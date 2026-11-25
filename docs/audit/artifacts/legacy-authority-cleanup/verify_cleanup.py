"""Verify scope, preserved behavior, links and regression evidence."""
import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT / '.worktrees/gabfin-s01'
HERE = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'docs/superpowers/plans/2026-11-25-gabfin-legacy-authority-cleanup.files.json').read_text(encoding='utf-8'))
before = json.loads((HERE / 'before.json').read_text(encoding='utf-8'))

def git(*args):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=REPO).decode('utf-8').strip()

def production_ast(text):
    tree = ast.parse(text)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        tree.body.pop(0)
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()

def links(text):
    return re.findall(r'\]\(([^)\n]+)\)', text) + re.findall(r'''(?i)href\s*=\s*["']([^"']+)["']''', text)

expected = {p for key in ['replace_authority', 'delete_legacy_adrs', 'retire_or_relink_legacy_docs', 'comments_only', 'update_document_assertions'] for p in manifest[key]}
changed = set(git('diff', '--name-only', before['source_sha']).splitlines())
assert changed == expected, {'unexpected': sorted(changed-expected), 'missing': sorted(expected-changed)}
assert all(not (REPO / name).exists() for name in manifest['delete_legacy_adrs'])
retired_names = {Path(name).name for name in manifest['delete_legacy_adrs']}
for name in manifest['retire_or_relink_legacy_docs']:
    text = (REPO / name).read_text(encoding='utf-8-sig')
    assert 'LEGACY / SUPERSEDED' in text[:20000], name
for name in manifest['replace_authority']:
    text = (REPO / name).read_text(encoding='utf-8-sig')
    assert not re.search(r'MUST FOLLOW|Binding architecture:|Architecture authority is ADR-003|## Architecture Decision \(ADR-003\)', text), name

new_links = 0
unchanged_broken = []
for name in sorted(expected):
    path = REPO / name
    if not path.exists() or path.suffix not in ('.md', '.html'):
        continue
    old_links = set(links(git('show', before['source_sha'] + ':' + name)))
    for target in links(path.read_text(encoding='utf-8-sig')):
        assert not any(retired in target for retired in retired_names), (name, target)
        if target not in old_links:
            new_links += 1
        if not target or target.startswith('#') or re.match(r'[a-z]+:', target, re.I):
            continue
        local = target.split('#')[0]
        if not path.parent.joinpath(local).exists():
            if target in old_links:
                unchanged_broken.append({'file': name, 'target': target})
            else:
                raise AssertionError(('new broken link', name, target))

for name, digest in before['production_body_ast'].items():
    assert production_ast((REPO / name).read_text(encoding='utf-8')) == digest, name
test_file = 'tests/api/test_mobile_desk_ro.py'
def functions(text):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old_functions = functions(git('show', before['source_sha'] + ':' + test_file))
new_functions = functions((REPO / test_file).read_text(encoding='utf-8'))
old_functions.pop('test_serve_doc_is_private_mesh_and_adr_stays_draft')
new_functions.pop('test_serve_doc_is_private_mesh_and_legacy_architecture_retired')
assert old_functions == new_functions, 'Unrelated test functions changed'
for name, digest in before['canonical_sha256'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256((REPO / 'web/package-lock.json').read_bytes()).hexdigest() == before['lock_sha256']
assert not (REPO / 'backend/data/trade_journal.json').exists()
assert not (REPO / 'backend/data/worker.pid').exists()

logs = ROOT / 'docs/audit/artifacts/s01-01b'
red = ET.parse(logs / 'pytest-adr-cleanup-red.xml').getroot().find('testsuite')
green = ET.parse(logs / 'pytest-adr-cleanup.xml').getroot().find('testsuite')
assert int(red.attrib['failures']) == 1
assert (int(green.attrib['tests']), int(green.attrib['failures']), int(green.attrib['errors']), int(green.attrib['skipped'])) == (58, 0, 0, 0)
baseline = json.loads((logs / 'results.json').read_text(encoding='utf-8'))
for name, digest in baseline['artifacts_sha256'].items():
    assert hashlib.sha256((logs / name).read_bytes()).hexdigest() == digest, name
subprocess.run(['git', '-c', 'core.safecrlf=false', 'diff', '--check', before['source_sha']], cwd=REPO, check=True)
result = {
    'base_sha': before['source_sha'], 'head_sha_at_verification': git('rev-parse', 'HEAD'),
    'changed_paths': len(changed), 'removed_legacy_adrs': 4, 'retired_legacy_pages': 23,
    'new_or_rewritten_links': new_links, 'new_broken_links': [], 'preexisting_broken_links': unchanged_broken,
    'production_ast_preserved': True, 'unrelated_test_functions_preserved': len(new_functions),
    'baseline_evidence_preserved': True, 'lockfile_preserved': True,
    'red': {'failures': 1}, 'green': {'passed': 58, 'skipped': 0, 'failures': 0, 'seconds': float(green.attrib['time'])},
    'journal_created': False, 'worker_pid_present': False,
}
(HERE / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key:value for key,value in result.items() if key != 'preexisting_broken_links'}, ensure_ascii=False))
print(json.dumps({'preexisting_broken_links': len(unchanged_broken)}))
