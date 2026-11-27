"""Check final checkpoint, local links and memory discipline (no network)."""
import json
from pathlib import Path
import re

artifact = Path(__file__).resolve().parent
root = artifact.parents[3]
names = ['docs/memory/tasks.md', 'docs/memory/execution.md', 'docs/memory/progress.md',
         'docs/memory/issues.md', 'docs/memory/architecture.md',
         'docs/audit/s03-03g-stream-2026-11-26.md', 'docs/audit/feed-entitlements.md',
         'docs/tickets/s03-stream/issues/01-equity-callback-cache.md']
broken = []
counts = {}
for name in names:
    path = root / name
    text = path.read_text(encoding='utf-8')
    counts[name] = len(text.splitlines())
    if name.startswith('docs/memory/'):
        assert counts[name] <= 80, name
    for link in re.findall(r'\]\(([^)]+)\)', text):
        if '://' in link or link.startswith('#'):
            continue
        target = link.split('#')[0]
        if not (path.parent / target).is_file():
            broken.append([name, target])
assert not broken, broken
progress = (root / names[2]).read_text(encoding='utf-8')
assert len(re.findall(r'^## ', progress, flags=re.M)) == 10
execution = (root / names[1]).read_text(encoding='utf-8')
assert '3073cf3b41ac2724979442960b314a0c92598ca0' in execution and '03h' in execution
tasks = (root / names[0]).read_text(encoding='utf-8')
assert 'T018' in tasks and 'T017' not in tasks
ticket = (root / names[-1]).read_text(encoding='utf-8')
assert 'Status: done' in ticket and '- [ ]' not in ticket
result = dict(local_links_verified=True, memory_lines=counts, latest_progress_entries=10,
              checkpoint_matches_source=True, completed_ticket=True)
(artifact / 'document-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
