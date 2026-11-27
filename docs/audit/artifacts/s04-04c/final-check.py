"""Tie evidence, the reviewed commit tree and affected documentation together."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

folder=Path(__file__).resolve().parent
workspace=folder.parents[3]
source=workspace/'.worktrees'/'gabfin-s01'
documents=[workspace/path for path in (
    'docs/audit/s04-04c-market-2026-11-26.md','docs/audit/feed-entitlements.md',
    'docs/memory/tasks.md','docs/memory/execution.md','docs/memory/progress.md',
    'docs/memory/architecture.md','docs/memory/decisions.md','docs/memory/issues.md',
    'docs/superpowers/plans/2026-11-26-gabfin-frontend-delivery-plan.md',
    'docs/tickets/test-determinism/issues/01-shadow-holiday-clock.md')]
links=0
for path in documents:
    text=path.read_text(encoding='utf-8')
    assert text.count('```')%2==0, path
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
        if target.startswith(('https:','http:','#','mailto:')): continue
        assert (path.parent/target.split('#')[0]).exists(), (path,target)
        links+=1
    if path.parent.name=='memory': assert len(text.splitlines())<=80, path
assert len(re.findall(r'^## ',(workspace/'docs/memory/progress.md').read_text(encoding='utf-8'),re.M))<=10
git=lambda *args:subprocess.check_output(['git',*args],cwd=source,text=True).strip()
commit=git('rev-parse','HEAD'); tree=git('rev-parse','HEAD^{tree}')
assert commit=='a434de2134550f6dc6ff32b593327192d309ffda'
assert tree=='24c9183fef8aa8c93f364bf4986408c3f70e1876'
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
assert git('ls-files','--others','--exclude-standard')=='web/package-lock.json'
core=ET.parse(folder/'core-final.xml').getroot().find('testsuite').attrib
full=ET.parse(folder/'full-integration.xml').getroot().find('testsuite').attrib
assert (core['tests'],core['failures'],core['errors'])==('925','0','0')
assert (full['tests'],full['failures'],full['skipped'])==('2137','1','4')
assert '17 passed' in (folder/'browser-final.log').read_text(encoding='utf-8')
assert json.loads((folder/'live-api-chain.json').read_text())['success'] is True
assert json.loads((folder/'preservation.json').read_text())['original_lock_preserved'] is True
evidence={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()
    if path.is_file() and path.name!='verification.json'}
result=dict(commit=commit,reviewed_tree=tree,staged_files_committed=28,core_passed=925,
    browser_passed=17,full_passed=2132,full_failed=1,full_skipped=4,
    full_failure_reproduced_at_base=True,local_markdown_links_checked=links,
    markdown_anchors_checked=False,documents_checked=len(documents),original_lock_preserved=True,
    internal_socket_live_api_smoke=True,real_live_browser_render_measured=False,
    g2_approved=False,trading_started=False,pushed=False,deployed=False,evidence_sha256=evidence)
(folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='evidence_sha256'}))
