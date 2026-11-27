"""The secret audit examines files and added diff lines without leaking values."""
from pathlib import Path
import shutil
import subprocess
import sys


SCANNER = Path(__file__).resolve().parents[2] / 'scripts/check-massive-secrets.py'


def test_scan_allows_removing_a_secret_but_rejects_new_leaks(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copyfile(SCANNER, scripts / SCANNER.name)
    secret = 'fixture-secret-never-print-999'
    endpoint = 'https://private.example.test'
    (tmp_path / '.env').write_text(
        f'MASSIVE_API_KEY={secret}\nMASSIVE_BASE_URL={endpoint}\n', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('.env\n', encoding='utf-8')
    doc = tmp_path / 'guide.txt'
    doc.write_text(endpoint, encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.test',
                    'commit', '-qm', 'fixture'], cwd=tmp_path, check=True)
    doc.write_text('<MASSIVE_BASE_URL>', encoding='utf-8')
    command = [sys.executable, str(scripts / SCANNER.name)]
    clean = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout
    doc.write_text(secret, encoding='utf-8')
    leaked = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert leaked.returncode == 1
    assert 'guide.txt' in leaked.stdout
    assert secret not in leaked.stdout + leaked.stderr
    assert endpoint not in leaked.stdout + leaked.stderr
