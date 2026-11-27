"""Verify skill installation and the documentation-only setup; no app execution."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

artifact = Path(__file__).resolve().parent
workspace = artifact.parents[3]
skill_root = Path('C:/Users/001/.agents/skills')
manifest = json.loads((artifact / 'upstream-manifest.json').read_text(encoding='utf-8'))
checks = []
for item in manifest['files']:
    path = skill_root / item['skill'] / item['relative']
    data = path.read_bytes() if path.is_file() else None
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() if data is not None else None
    checks.append({'path': str(path), 'expected_blob': item['sha'], 'actual_blob': actual, 'matches': actual == item['sha']})
install = {'revision': manifest['revision'], 'checked_files': len(checks), 'matching_files': sum(c['matches'] for c in checks), 'checks': checks}
(artifact / 'verification.json').write_text(json.dumps(install, indent=2) + '\n', encoding='utf-8')

files = [Path('AGENTS.md'), *[p.relative_to(workspace) for p in (workspace / 'docs/agents').glob('*.md')],
         Path('docs/audit/skills-workflow-2026-11-25.md'),
         Path('docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md'),
         *[Path('docs/memory') / n for n in ['tooling.md', 'tasks.md', 'execution.md', 'progress.md']]]
broken, fences, link_count = [], [], 0
for relative in files:
    path = workspace / relative
    content = path.read_text(encoding='utf-8')
    if sum(line.startswith('```') for line in content.splitlines()) % 2:
        fences.append(str(relative))
    for destination in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
        if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', destination) or destination.startswith('#'):
            continue
        link_count += 1
        target = unquote(destination.split('#')[0].strip('<>'))
        if not (path.parent / target).exists():
            broken.append({'file': str(relative), 'target': destination})
memory_lines = {str(p): len((workspace / p).read_text(encoding='utf-8').splitlines()) for p in files if p.parent == Path('docs/memory')}
progress_entries = sum(line.startswith('## ') for line in (workspace / 'docs/memory/progress.md').read_text(encoding='utf-8').splitlines())
missing = [p.name for p in skill_root.iterdir() if p.is_dir() and not (p / 'SKILL.md').is_file()]
repo = workspace / '.worktrees/gabfin-s01'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
status = subprocess.check_output(['git', 'status', '--short'], cwd=repo, text=True).strip()
lock = hashlib.sha256((repo / 'web/package-lock.json').read_bytes()).hexdigest()
historical_lock = json.loads((workspace / 'docs/audit/artifacts/s03-03c/before.json').read_text(encoding='utf-8-sig'))['lock']
review_manifest = json.loads((artifact / 'review-fixed-input-sha256.json').read_text(encoding='utf-8'))
changed = [p for p, expected in review_manifest.items() if hashlib.sha256((workspace / p).read_bytes()).hexdigest() != expected]
report = {'checked_markdown_files': len(files), 'local_links_checked': link_count, 'broken_links': broken,
          'unbalanced_fences': fences, 'memory_lines': memory_lines, 'progress_entries': progress_entries,
          'skill_dirs': sum(p.is_dir() for p in skill_root.iterdir()), 'skill_md_missing': missing,
          'source_head': head, 'source_status': status, 'source_lockfile_sha256': lock,
          'source_lock_matches_03c_evidence': lock == historical_lock, 'review_input_changed': changed,
          'app_tests_run': False}
(artifact / 'document-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'matching_skill_files': install['matching_files'], **report}, indent=2))
assert all(c['matches'] for c in checks)
assert not broken and not fences and not missing and not changed
assert all(n <= 80 for n in memory_lines.values()) and progress_entries <= 10
assert head == '2607a81a073a5fac2286b0fc0aa5742a5f6fabba'
assert status == '?? web/package-lock.json' and lock == historical_lock
