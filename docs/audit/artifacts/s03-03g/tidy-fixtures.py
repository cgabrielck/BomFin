"""Deduplicate independent external-transport test fixtures, not production code."""
from pathlib import Path
import re

repo = Path(__file__).resolve().parents[4] / '.worktrees/gabfin-s01'
path = repo / 'tests/gabfin/test_futu_quote_adapter.py'
source = path.read_text(encoding='utf-8')
source, ready_count = re.subn(re.escape("print(json.dumps(dict(version=1,kind='ready')),flush=True)"), 'ready()', source)
pattern = re.escape("print(json.dumps(dict(version=1,kind='closed',cleanup='") + r"([^']+)" + re.escape("',closed=True,errors=") + r'(\[[^\n]*?\])' + re.escape(',callbacks=') + r'(\d+)' + re.escape(',coalesced=0,rejected=0)),flush=True)')
source, closed_count = re.subn(pattern, lambda match: f"finish(cleanup={match[1]!r}, errors={match[2]}, callbacks={match[3]})", source)
assert ready_count > 5 and closed_count > 5
old = 'worker.write_text("import sys,json\\nc=json.loads(sys.stdin.readline())\\n" + body, encoding=\'utf-8\')'
new = '''worker.write_text("""
import sys,json
c=json.loads(sys.stdin.readline())
def ready():
    print(json.dumps(dict(version=1,kind='ready')),flush=True)
def finish(*,cleanup='unsubscribed',errors=None,callbacks=0):
    print(json.dumps(dict(version=1,kind='closed',cleanup=cleanup,closed=True,
                          errors=errors or [],callbacks=callbacks,coalesced=0,rejected=0)),flush=True)
""" + body, encoding='utf-8')'''
assert source.count(old) == 1
path.write_text(source.replace(old, new), encoding='utf-8')
print(dict(ready_fixtures=ready_count, terminal_fixtures=closed_count))
