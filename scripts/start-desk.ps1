param(
    [int]$Port = 19443,
    [string]$Tape = '',
    [string]$Runtime = '',
    [switch]$SkipBuild,
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Python environment missing: install project dependencies first.' }

# Loading the local environment is an explicit operator action. Never print values.
$envFile = Join-Path $repo '.env'
if (Test-Path $envFile) {
    foreach ($line in [IO.File]::ReadAllLines($envFile)) {
        if ($line -match '^\s*(MASSIVE_[A-Z0-9_]+|LLM_[A-Z0-9_]+|FRED_API_KEY)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2]
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
}
if (-not $SkipBuild) {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Front-end build failed.' }
}
$tls = Join-Path $repo 'runtime\tls'
$cert = Join-Path $tls 'cert.pem'
$key = Join-Path $tls 'key.pem'
if (-not (Test-Path $cert) -or -not (Test-Path $key)) {
    $openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
    if (-not (Test-Path $openssl)) { throw 'Local TLS certificate missing; install Git OpenSSL or supply runtime/tls/cert.pem and key.pem.' }
    New-Item -ItemType Directory -Path $tls -Force | Out-Null
    & $openssl req -x509 -newkey rsa:2048 -nodes -keyout $key -out $cert -days 30 -subj '/CN=localhost' -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Local TLS certificate creation failed.' }
}
$arguments = @('scripts/desk-server.py', '--cert', $cert, '--key', $key, '--port', "$Port")
if ($Tape) { $arguments += @('--tape', $Tape) }
if ($Offline) { $arguments += '--offline' }
if ($Runtime) { $arguments += @('--runtime', $Runtime) }
Write-Host "GabFin local desk: https://127.0.0.1:$Port"
Write-Host 'Use the one-time pairing code printed by the server. Keep this window open; Ctrl+C stops the desk.'
Write-Host 'The local certificate may require browser confirmation. No order execution is enabled.'
& $python @arguments
exit $LASTEXITCODE
