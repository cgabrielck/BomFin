"""Apply the approved documentation cleanup to the existing local checkout."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]
REPO = WORKSPACE / '.worktrees/gabfin-s01'
ARTIFACTS = Path(__file__).resolve().parent
MANIFEST = json.loads((WORKSPACE / 'docs/superpowers/plans/2026-11-25-gabfin-legacy-authority-cleanup.files.json').read_text(encoding='utf-8'))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def body_ast(text):
    tree = ast.parse(text)
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        tree.body.pop(0)
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()

def write(relative, content):
    (REPO / relative).write_text(content.rstrip() + '\n', encoding='utf-8')

def task1():
    assert not (ARTIFACTS / 'before.json').exists(), 'Do not overwrite the original snapshot'
    assert git('status', '--porcelain=v1', '--untracked-files=all') == '?? web/package-lock.json'
    groups = ['replace_authority', 'delete_legacy_adrs', 'retire_or_relink_legacy_docs', 'comments_only', 'update_document_assertions']
    files = [p for group in groups for p in MANIFEST[group]]
    snapshot = {
        'source_sha': git('rev-parse', 'HEAD'),
        'lock_sha256': digest(REPO / 'web/package-lock.json'),
        'files_sha256': {p: digest(REPO / p) for p in files},
        'production_body_ast': {p: body_ast((REPO / p).read_text(encoding='utf-8')) for p in MANIFEST['comments_only']},
        'canonical_sha256': {p: digest(WORKSPACE / p) for p in ['docs/superpowers/specs/2026-11-25-gabfin-system-design.md', 'docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md']},
        'journal_existed': (REPO / 'backend/data/trade_journal.json').exists(),
    }
    (ARTIFACTS / 'before.json').write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
    write('AGENTS.md', '''# GabFin source checkout instructions

This checkout contains legacy source and the starting point for the new GabFin.
Current user instructions and the confirmed new design govern all work.

## Before working

1. Read the [workspace instructions](../../AGENTS.md).
2. Read [tasks](../../docs/memory/tasks.md) and the [execution checkpoint](../../docs/memory/execution.md).
3. Read only the relevant section of the [confirmed design](../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md)
   and [main upgrade plan](../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).
4. Check branch, HEAD and existing changes. Preserve unrelated work and local evidence.

All legacy ADRs and historical roadmaps are retired as product constraints.
Their old Accepted, binding, or Draft labels do not override the new design.
Legacy source, tests and notes may be used as evidence, not as new requirements.
The new frontend is to be rewritten; reuse of backend modules follows the new plan.

## Working agreement

- Use Traditional Chinese for reports; technical depth and focused questions are welcome.
- Use the existing local checkout and environment; default to one agent.
- Do not start trading, change approved risk limits, deploy or push without applicable authorization.
- Update the outer workspace checkpoint and affected memory after significant work.
- These relative links target the current local workspace. Update them when moving or integrating the checkout.
''')
    write('docs/LOCAL_CURSOR_HANDOFF.md', '''# GabFin local handoff

The previous handoff is retired. This checkout is the legacy source baseline,
not an authority for the new product architecture.

1. Read the [workspace AGENTS](../../../AGENTS.md).
2. Resume from [execution](../../../docs/memory/execution.md) and [tasks](../../../docs/memory/tasks.md).
3. Follow the [confirmed design](../../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md)
   and the current task in the [upgrade plan](../../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).
4. Verify branch, HEAD and dirty files before editing. Preserve baseline evidence and the local lockfile.

Old architecture decisions, strategy-adoption mandates and roadmaps do not constrain the redesign.
Do not restore obsolete no-rewrite, long-only or fixed-sizing requirements from legacy text.
Use the existing local environment and the user's chosen single-agent workflow.
Ask focused engineering or financial questions when a real decision needs the user's input.
Do not start trading or publish changes as part of documentation or baseline work.
''')
    write('docs/ARCHITECTURE_DECISION.md', '''# Architecture authority

**Status: SUPERSEDED — the legacy architecture decisions are retired.**

The current authority is the latest user instruction and the confirmed GabFin design:

- [Workspace instructions](../../../AGENTS.md)
- [Confirmed requirements and system design](../../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md)
- [Main implementation plan](../../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md)
- [Current execution checkpoint](../../../docs/memory/execution.md)

This file is a compatibility pointer for existing links, not another product specification.
All previous ADRs, including the former embedded decisions, are retired as constraints.
Their original content remains available in Git history; it must not govern the redesign.
Historical implementation notes may describe behavior that the new plan replaces.
This documentation change does not enable trading or alter runtime permissions.

The canonical documents currently live in the parent local workspace. If this checkout
is moved or integrated elsewhere, migrate those documents and update these pointers.
''')
    readme = (REPO / 'README.md').read_text(encoding='utf-8')
    readme = readme.replace('# ALPHA//DESK — Institutional-Grade Equity Research Terminal', '# GabFin legacy source — ALPHA//DESK', 1)
    readme = re.sub(r'^\*\*Product name: Cgab\.\*\* Binding architecture:.*$', '**Legacy implementation name: Cgab.** The surfaces below describe existing source, not the target product. The new GabFin follows the [confirmed design](../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md) and [upgrade plan](../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md). The frontend rewrite is planned, not implemented here.', readme, flags=re.M)
    readme = re.sub(r'^Architecture authority is ADR-003,.*$', 'Current authority: the [new GabFin design and execution pointers](docs/ARCHITECTURE_DECISION.md). Old roadmaps and architecture labels are historical evidence only.', readme, flags=re.M)
    readme = re.sub(r'^ADR-003: Desk = product;.*$', 'Legacy source layout: FastAPI serves the Desk shell; Streamlit is the lab interface. Existing Intent and Order paths are documented as implementation history in [MODULAR_ARCHITECTURE.md](docs/MODULAR_ARCHITECTURE.md), not as constraints on the new architecture.', readme, flags=re.M)
    readme = readme.replace('docs/ARCHITECTURE_DECISION.md      ADR-003 (binding)', 'docs/ARCHITECTURE_DECISION.md      Pointer to the new design')
    write('README.md', readme)
    product = (REPO / 'PRODUCT.md').read_text(encoding='utf-8')
    product = product.replace('# Product', '# Legacy product record', 1)
    product = product.replace('<!-- impeccable:product-schema 1 -->', '<!-- impeccable:product-schema 1 -->\n\n> LEGACY / SUPERSEDED — this record describes the previous implementation, not the new GabFin requirements. Follow the [confirmed design](../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md) and [upgrade plan](../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).')
    write('PRODUCT.md', product)
    print(json.dumps({'task': 1, 'modified': MANIFEST['replace_authority'], 'lock_preserved': digest(REPO / 'web/package-lock.json') == snapshot['lock_sha256']}))

def task2():
    before = json.loads((ARTIFACTS / 'before.json').read_text(encoding='utf-8'))
    assert digest(REPO / 'web/package-lock.json') == before['lock_sha256']
    assert all(not (REPO / p).exists() for p in MANIFEST['delete_legacy_adrs'])
    retired = {Path(p).name for p in MANIFEST['delete_legacy_adrs']}
    replacements = []
    for name in MANIFEST['retire_or_relink_legacy_docs']:
        path = REPO / name
        text = path.read_text(encoding='utf-8')
        index = os.path.relpath(REPO / 'docs/ARCHITECTURE_DECISION.md', path.parent).replace('\\', '/')
        changed_links = [0]
        def destination(target):
            if any(filename in target for filename in retired):
                changed_links[0] += 1
                return index
            return target
        text = re.sub(r'\]\(([^)\n]+)\)', lambda m: '](' + destination(m.group(1)) + ')', text)
        text = re.sub(r'(?m)^(\s*\[[^\]]+\]:\s*)(\S+)', lambda m: m.group(1) + destination(m.group(2)), text)
        text = re.sub(r'''(?i)(href\s*=\s*["'])([^"']+)(["'])''', lambda m: m.group(1) + destination(m.group(2)) + m.group(3), text)
        message = 'LEGACY / SUPERSEDED — describes the previous implementation; not instructions for the new GabFin architecture.'
        if path.suffix == '.html':
            banner = '<aside role="note" style="padding:16px;background:#fff3cd;color:#332701">' + message + ' <a href="' + index + '">Current architecture authority</a></aside>'
            text, count = re.subn(r'(?i)<body\b[^>]*>', lambda m: m.group(0) + '\n' + banner, text, count=1)
            assert count == 1, 'HTML body not found: ' + name
        else:
            text = '> ' + message + '\n> See [current architecture authority](' + index + '). Historical rules below do not govern the redesign.\n\n' + text
        write(name, text)
        replacements.append({'file': name, 'repaired_links': changed_links[0]})
    mobile = (REPO / 'backend/api/mobile_desk.py').read_text(encoding='utf-8')
    old = 'ADR-005 stays Draft. Shipping this route does not Accept the ADR and does\nnot open live trading.'
    assert old in mobile
    mobile = mobile.replace(old, 'Legacy implementation only; its old architecture decisions are retired.\nThe adr_005 response metadata is retained for compatibility, not design authority.')
    write('backend/api/mobile_desk.py', mobile)
    models = (REPO / 'backend/trading/intents/models.py').read_text(encoding='utf-8')
    assert 'Binds under ADR-003 Addendum A and MODULAR_ARCHITECTURE §5.6.' in models
    models = models.replace('Binds under ADR-003 Addendum A and MODULAR_ARCHITECTURE §5.6.', 'Legacy implementation model; the new GabFin design defines future contracts.')
    write('backend/trading/intents/models.py', models)
    test_name = 'tests/api/test_mobile_desk_ro.py'
    tests = (REPO / test_name).read_text(encoding='utf-8')
    tests = tests.replace('ADR-005 stays Draft. These checks do not Accept it and do not open live trading.', 'Legacy behavior regression; retired ADR labels do not govern the new architecture.')
    tests = tests.replace('ADR = ROOT / "docs" / "ADR-005-mobile-desk-readonly.md"', 'ARCHITECTURE_INDEX = ROOT / "docs" / "ARCHITECTURE_DECISION.md"')
    tests = tests.replace('def test_serve_doc_is_private_mesh_and_adr_stays_draft():', 'def test_serve_doc_is_private_mesh_and_legacy_architecture_retired():')
    tests = tests.replace('    assert "Draft" in doc\n', '    assert "LEGACY / SUPERSEDED" in doc\n')
    old_assertions = '    adr = ADR.read_text(encoding="utf-8").splitlines()\n    assert any("**Status:** **Draft**" in line for line in adr[:8])'
    assert old_assertions in tests
    tests = tests.replace(old_assertions, '    architecture = ARCHITECTURE_INDEX.read_text(encoding="utf-8")\n    assert "SUPERSEDED" in architecture\n    assert "2026-11-25-gabfin-system-design.md" in architecture')
    write(test_name, tests)
    (ARTIFACTS / 'repaired-links.json').write_text(json.dumps(replacements, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'legacy_pages_retired': len(replacements), 'links_repaired': sum(r['repaired_links'] for r in replacements), 'production_module_bodies_changed': False}))

if __name__ == '__main__':
    if sys.argv[1:] == ['task1']:
        task1()
    elif sys.argv[1:] == ['task2']:
        task2()
    else:
        raise SystemExit('Expected task1 or task2')
