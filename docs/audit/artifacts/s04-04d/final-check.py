"""Verify the committed chart unit and its evidence without rerunning legacy code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

folder=Path(__file__).resolve().parent
workspace=folder.parents[3]
source=workspace/'.worktrees/gabfin-s01'
git=lambda *args:subprocess.check_output(['git',*args],cwd=source,text=True).strip()
base='a434de2134550f6dc6ff32b593327192d309ffda'
tree=git('rev-parse','HEAD^{tree}')
assert tree=='8a9f825027d1f7ca57ed50f07b480584849f28aa'
assert git('rev-parse','HEAD^')==base
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
assert git('ls-files','--others','--exclude-standard')=='web/package-lock.json'
changed=git('diff','--name-only',base,'HEAD').splitlines()
assert len(changed)==24
assert not any(path.startswith(('services/','schemas/')) or path=='pyproject.toml' for path in changed)
assert '28 passed' in (folder/'integration-reviewed.log').read_text(encoding='utf-8')
assert '2 passed' in (folder/'green-generic-expiry.log').read_text(encoding='utf-8')
assert '1 passed' in (folder/'production-capture-final.log').read_text(encoding='utf-8')
assert json.loads((folder/'audit-production.json').read_text())['metadata']['vulnerabilities']['total']==0
assert json.loads((folder/'fixture-reproduction.json').read_text())['reproducible']
preservation=json.loads((folder/'preservation.json').read_text())
assert preservation['original_lock_preserved'] and not preservation['unexpected_baseline_changes']
documents=[workspace/path for path in (
    'docs/audit/s04-04d-chart-2026-11-26.md','docs/memory/tasks.md','docs/memory/execution.md',
    'docs/memory/progress.md','docs/memory/architecture.md',
    'docs/superpowers/plans/2026-11-26-gabfin-frontend-delivery-plan.md')]
links=0
for path in documents:
    text=path.read_text(encoding='utf-8')
    assert text.count('```')%2==0, path
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
        if target.startswith(('http:','https:','#','mailto:')):continue
        assert (path.parent/target.split('#')[0]).exists(),(path,target)
        links+=1
    if path.parent.name=='memory':assert len(text.splitlines())<=80,path
assert len(re.findall(r'^## ',(workspace/'docs/memory/progress.md').read_text(encoding='utf-8'),re.M))<=10
screenshots={path.name:hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (workspace/'output/playwright/s04-04d').glob('*.png')}
assert set(screenshots)=={'chart-desktop.png','chart-mobile.png'}
result=dict(commit=git('rev-parse','HEAD'),reviewed_tree=tree,base=base,committed_files=24,
    playwright_passed=28,browser_cases=23,bar_patch_cases=5,production_capture_passed=1,
    chart_package_version='5.3.0',canonical_synthetic_bars=60,production_known_vulnerabilities=0,
    original_lock_preserved=True,local_markdown_links_checked=links,markdown_anchors_checked=False,
    python_product_unchanged=True,python_full_suite_run_this_unit=False,live_opend_run_this_unit=False,
    g2_approved=False,trading_started=False,pushed=False,deployed=False,screenshot_sha256=screenshots)
(folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
