"""Read-only comparison against the recorded pre-unit checkout bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

source=Path(__file__).resolve().parents[4]/'.worktrees'/'gabfin-s01'
folder=Path(__file__).resolve().parent
before=json.loads((folder/'before.json').read_text())
owned=set(subprocess.check_output(['git','diff','--cached','--name-only',before['head']],cwd=source,text=True).splitlines())
changed=[]
for name,digest in before['files'].items():
    path=source/name
    if name not in owned and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
        changed.append(name)
lock=hashlib.sha256((source/'web/package-lock.json').read_bytes()).hexdigest()
unstaged=subprocess.check_output(['git','diff','--name-only'],cwd=source,text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=source,text=True).splitlines()
result=dict(baseline_head=before['head'],tracked_baseline_files=len(before['files']),owned_files=sorted(owned),
    unexpected_baseline_changes=changed,unstaged_tracked=unstaged,untracked=untracked,
    original_lock_sha256=lock,original_lock_preserved=lock==before['original_lock'],
    index_tree=subprocess.check_output(['git','write-tree'],cwd=source,text=True).strip())
(folder/'preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='owned_files'}))
raise SystemExit(0 if not changed and not unstaged and untracked==['web/package-lock.json'] and result['original_lock_preserved'] else 2)
