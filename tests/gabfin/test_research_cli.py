"""Explicit research CLI, no implicit credential loading or fake model fallback."""
import subprocess
import sys


def test_research_cli_lists_snapshot_and_run_operations():
    result = subprocess.run([sys.executable, '-m', 'gabfin.research', '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'capture' in result.stdout and 'run' in result.stdout and 'checks' in result.stdout
