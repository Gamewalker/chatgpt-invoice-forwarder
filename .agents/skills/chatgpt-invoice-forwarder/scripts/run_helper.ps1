param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AgentArguments
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..\..')).Path
$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Lokale Python-Umgebung fehlt. Fuehre zuerst scripts\setup.ps1 aus."
}

$configPath = Join-Path $repoRoot 'config\agent.json'
& $venvPython -m chatgpt_invoice_agent --config $configPath @AgentArguments
exit $LASTEXITCODE

