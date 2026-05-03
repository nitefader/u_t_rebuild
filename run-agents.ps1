param(
    [int]$MaxCycles = 20,
    [switch]$Reset,
    [switch]$Safe,
    [switch]$DiscardQuestion
)

$ErrorActionPreference = "Stop"

$RepoRoot = "C:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild"
Set-Location $RepoRoot

$argsList = @(
    "scripts\mission_orchestrator_auto.py",
    "--max-cycles",
    "$MaxCycles"
)

if ($Reset) {
    $argsList += "--reset"
} else {
    $argsList += "--resume"
}

if ($DiscardQuestion) {
    $argsList += "--discard-question"
}

if (-not $Safe) {
    $argsList += "--dangerous"
}

Write-Host "Starting Ultimate Trader agent loop..." -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "Max cycles: $MaxCycles"
Write-Host "Reset: $Reset"
Write-Host "Discard question: $DiscardQuestion"
Write-Host "Dangerous mode: $(-not $Safe)"

python @argsList