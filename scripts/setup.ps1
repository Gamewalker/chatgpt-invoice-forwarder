param(
    [string]$Python = 'py'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $repoRoot '.venv'

if ($Python -eq 'py') {
    & py -3.11 -m venv $venv
} else {
    & $Python -m venv $venv
}
if ($LASTEXITCODE -ne 0) {
    throw 'Python-Umgebung konnte nicht erstellt werden.'
}

$venvPython = Join-Path $venv 'Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Projektinstallation ist fehlgeschlagen.'
}

& $venvPython -m unittest discover -s (Join-Path $repoRoot 'tests') -v

