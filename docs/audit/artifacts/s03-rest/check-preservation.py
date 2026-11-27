"""Read-only comparison with the work unit's recorded pre-edit files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    before=json.loads(args.baseline.read_text())
    owned=set(subprocess.check_output(['git','diff','--cached','--name-only',before['head']],
                                     cwd=args.source,text=True).splitlines())
    changed=[]
    for name,digest in before['files'].items():
        path=args.source/name
        if name not in owned and (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
            changed.append(name)
    lock=hashlib.sha256((args.source/'web/package-lock.json').read_bytes()).hexdigest()
    unstaged=subprocess.check_output(['git','diff','--name-only'],cwd=args.source,text=True).splitlines()
    result=dict(baseline_head=before['head'],tracked_baseline_files=len(before['files']),
        owned_files=sorted(owned),unexpected_baseline_changes=changed,unstaged_tracked=unstaged,
        original_lock_sha256=lock,original_lock_preserved=lock==before['lock'],
        index_tree=subprocess.check_output(['git','write-tree'],cwd=args.source,text=True).strip())
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='owned_files'}))
    raise SystemExit(0 if not changed and not unstaged and lock==before['lock'] else 2)
