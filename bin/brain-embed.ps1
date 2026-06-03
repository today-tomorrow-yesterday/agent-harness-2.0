<#
brain-embed.ps1 — nightly semantic-embedding backfill for claude-brain.

Runs scripts/batch_embed.py, which embeds every eligible transcript that has no
row in transcript_vec_meta (the live Stop-hook embeds interactive sessions inline;
bulk session-start / JSONL ingest does NOT, so the imported backlog accumulates
unembedded and search_semantic goes blind to it). Embedding is LOCAL compute
(BAAI/bge-base-en-v1.5) — zero subscription / API cost — so this processes the
full backlog each run; once caught up, nightly runs only embed the day's new
batch-ingested rows.

Logs to claude-brain/logs/<hostname>/batch_embed.log with size-based rotation.
#>

$Root      = 'Z:\agent-os\claude-brain'
$Script    = Join-Path $Root 'scripts\batch_embed.py'
$Python    = 'C:\Users\trerh\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe'
$LogDir    = Join-Path $Root ("logs\" + [System.Net.Dns]::GetHostName())
$LogFile   = Join-Path $LogDir 'batch_embed.log'
$MaxBytes  = 5MB

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

# Size-based rotation: keep one .1 backup, start fresh past MaxBytes.
if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt $MaxBytes)) {
    $bak = "$LogFile.1"
    if (Test-Path $bak) { Remove-Item $bak -Force }
    Move-Item $LogFile $bak -Force
}

function Write-Log($msg) {
    $ts = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Add-Content -Path $LogFile -Value "$ts [brain-embed] $msg" -Encoding utf8
}

Write-Log "starting batch_embed backfill"
# Do NOT treat native stderr as terminating: the embedding lib prints
# informational lines (e.g. "No device provided, using cpu") to stderr that are
# not failures. Capture everything and judge success by the real exit code.
$ErrorActionPreference = 'Continue'
$out = & $Python $Script 2>&1 | Out-String
$rc  = $LASTEXITCODE
Add-Content -Path $LogFile -Value $out -Encoding utf8
Write-Log ("batch_embed exited rc={0}" -f $rc)
exit $rc
