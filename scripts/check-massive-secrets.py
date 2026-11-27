"""Check versionable files and git diff without printing Massive secret values."""
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    values = {}
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() in ('MASSIVE_API_KEY', 'MASSIVE_BASE_URL'):
                values[name.strip()] = value.strip().strip('\"\'')
    for name in ('MASSIVE_API_KEY', 'MASSIVE_BASE_URL'):
        print(f'{name}: {"present" if values.get(name) else "missing"}')
    needles = [value.encode() for value in values.values() if value]
    base = values.get('MASSIVE_BASE_URL', '')
    host = urlsplit(base).hostname
    if host:
        needles.append(host.encode())
    names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT
    ).decode('utf-8').split('\0')
    findings = []
    for name in sorted(set(names) - {''}):
        path = ROOT / name
        if path.is_file() and name != '.env':
            content = path.read_bytes()
            if any(needle in content for needle in needles):
                findings.append(name)
    diff = subprocess.check_output(
        ['git', '-c', 'core.safecrlf=false', 'diff', '--no-ext-diff', '--unified=0', 'HEAD', '--'],
        cwd=ROOT, stderr=subprocess.PIPE)
    added = b'\n'.join(line for line in diff.splitlines()
                       if line.startswith(b'+') and not line.startswith(b'+++'))
    if any(needle in added for needle in needles):
        findings.append('<git diff HEAD>')
    for name in findings:
        print(f'Sensitive Massive value found: {name}')
    print(f'Scanned {len(names) - 1} versionable paths; findings: {len(findings)}')
    return int(bool(findings) or len(values) != 2)


if __name__ == '__main__':
    raise SystemExit(main())
