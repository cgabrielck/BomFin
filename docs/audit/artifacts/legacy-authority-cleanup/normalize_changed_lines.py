"""Keep original unchanged line endings; clean only inserted/replaced lines."""
import difflib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPO = ROOT / '.worktrees/gabfin-s01'
HERE = Path(__file__).resolve().parent
before = json.loads((HERE / 'before.json').read_text(encoding='utf-8'))
manifest = json.loads((ROOT / 'docs/superpowers/plans/2026-11-25-gabfin-legacy-authority-cleanup.files.json').read_text(encoding='utf-8'))
count = 0
for name in manifest['retire_or_relink_legacy_docs'] + manifest['comments_only'] + manifest['update_document_assertions']:
    original = subprocess.check_output(['git', 'show', before['source_sha'] + ':' + name], cwd=REPO)
    had_bom = original.startswith(b'\xef\xbb\xbf')
    old_raw = original.decode('utf-8-sig').splitlines(keepends=True)
    old_lines = [line.rstrip('\r\n') for line in old_raw]
    current = (REPO / name).read_text(encoding='utf-8').replace('\ufeff', '')
    new_lines = current.splitlines()
    result = []
    for op, a, b, c, d in difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes():
        if op == 'equal':
            result.extend(old_raw[a:b])
        elif op in ('replace', 'insert'):
            for line in new_lines[c:d]:
                hard_break = name.endswith('.md') and line.endswith('  ')
                cleaned = line.rstrip(' \t\r')
                if hard_break:
                    cleaned += '\\'
                result.append(cleaned + '\n')
    body = ''.join(result)
    if not body.endswith('\n'):
        body += '\n'
    (REPO / name).write_bytes((b'\xef\xbb\xbf' if had_bom else b'') + body.encode('utf-8'))
    count += 1
print(json.dumps({'files_checked': count, 'original_unchanged_lines_preserved': True}))
