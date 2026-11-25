param(
    [string]$RunName = 'pytest-baseline',
    [string[]]$TestPaths = @()
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$checkout = Join-Path $workspaceRoot '.worktrees/gabfin-s01'
$pythonExe = Join-Path $checkout '.venv/Scripts/python.exe'

# These changes affect only this PowerShell process and its test child.
# Do not print inherited values or let a local .env provide credentials.
Get-ChildItem Env: | Where-Object {
    $_.Name -match '(?i)(APCA|ALPACA|API_KEY|SECRET|TOKEN|DATABASE|SUPABASE|TELEGRAM|ALERT_OWNER|LLM_|OPENAI|POLYGON|TRADIER|ALPHA_VANTAGE|SCAN_)' -or
    $_.Name -in @('PYTHONPATH', 'PYTEST_ADDOPTS', 'PYTHONSTARTUP', 'VIRTUAL_ENV')
} | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
$env:APCA_PAPER = 'true'
$env:SCAN_AUTO = 'false'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Set-Location -LiteralPath $checkout
$arguments = @('-m', 'pytest', '-ra', '--tb=short', ('--junitxml=' + (Join-Path $PSScriptRoot ($RunName + '.xml')))) + $TestPaths
& $pythonExe @arguments *> (Join-Path $PSScriptRoot ($RunName + '.log'))
$testExitCode = $LASTEXITCODE
Write-Output ('pytest exit: ' + $testExitCode)
Get-Content -LiteralPath (Join-Path $PSScriptRoot ($RunName + '.log')) -Tail 45
exit $testExitCode
