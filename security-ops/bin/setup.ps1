# setup.ps1 — provision the security-ops module on this machine. NO admin needed.
#   1. clone the public cybersecurity-skill library into skills/  (not bundled in the repo)
#   2. add the heuristic "offensive" flag to its index
#   3. register the nightly scheduled task (normal privilege; harden.ps1 elevates it later)
#   4. record the first baseline
# After this, run bin\harden.ps1 ONCE from an elevated PowerShell.
param(
    [string]$Root      = (Split-Path $PSScriptRoot -Parent),
    [string]$LibRepo   = "https://github.com/mukul975/Anthropic-Cybersecurity-Skills",
    [string]$TaskName  = "agent-harness-security-ops",
    [string]$Time      = "02:30"
)
$ErrorActionPreference = 'Stop'
$SkillsDir = Join-Path $Root "skills"

Write-Host "== 1/4  Skill library ==" -ForegroundColor Cyan
if (Test-Path (Join-Path $SkillsDir "index.json")) {
    Write-Host "   already present at $SkillsDir - skipping clone."
} else {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git not found on PATH - install git, then re-run." }
    $tmp = Join-Path $env:TEMP ("secops-lib-" + [Guid]::NewGuid().ToString("N").Substring(0,8))
    Write-Host "   cloning $LibRepo ..."
    git clone --depth 1 $LibRepo $tmp 2>&1 | Out-Null
    $srcSkills = Join-Path $tmp "skills"
    if (-not (Test-Path $srcSkills)) { throw "cloned repo has no skills/ dir - check $LibRepo layout." }
    New-Item -ItemType Directory -Path $SkillsDir -Force | Out-Null
    Copy-Item (Join-Path $srcSkills "*") $SkillsDir -Recurse -Force
    if ((Test-Path (Join-Path $tmp "index.json")) -and -not (Test-Path (Join-Path $SkillsDir "index.json"))) {
        Copy-Item (Join-Path $tmp "index.json") $SkillsDir -Force
    }
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "   library installed -> $SkillsDir"
}

Write-Host "== 2/4  Flag offensive skills in index.json ==" -ForegroundColor Cyan
$tagger = Join-Path $PSScriptRoot "tag-offensive.ps1"
if ((Test-Path $tagger) -and (Test-Path (Join-Path $SkillsDir "index.json"))) {
    & $tagger -IndexPath (Join-Path $SkillsDir "index.json")
} else {
    Write-Host "   skipped (no index.json or tagger)." -ForegroundColor Yellow
}

Write-Host "== 3/4  Register nightly task '$TaskName' @ $Time (normal privilege) ==" -ForegroundColor Cyan
$tr = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File `"$Root\bin\night-monitor.ps1`""
schtasks /Create /SC DAILY /ST $Time /TN $TaskName /TR $tr /F | Out-Null
Write-Host "   registered. (Run bin\harden.ps1 elevated to upgrade it to highest privileges + lock the ACLs.)"

Write-Host "== 4/4  First baseline ==" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "night-monitor.ps1") -Once | Out-Null
Write-Host "   baseline recorded -> $Root\reports"

Write-Host "`nNEXT (once, elevated):" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$Root\bin\harden.ps1`""
Write-Host "Then copy agents\security-analyst.md into your Claude profile(s) (~\.claude\agents\)."
