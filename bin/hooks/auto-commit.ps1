# auto-commit.ps1 — PostToolUse hook for Z:\Clone\ wiki content
#
# Triggered by Claude Code on Write|Edit. Receives a JSON payload via stdin
# describing the tool invocation. If the written file is inside Z:\Clone\ and
# inside the wiki layer (not 00_inbox/ raw scrapes — those are owned by the
# farmer), this hook stages the file and commits it with a `clone:` prefix.
#
# Local-only — no push (no remote configured by design). If we ever add a
# remote, switch the pull-then-push pattern in here.
#
# The carve-out in Z:\agent-os\memory\feedback\never_commit_without_permission.md
# covers this autonomous behavior: Tre approved the hook design 2026-05-24
# while implementing the Brad-inspired infrastructure layer. Once approved,
# the hook commits without per-write asks; Claude itself doesn't issue
# `git commit` from session work — only this hook does.

$ErrorActionPreference = "Continue"

# --- Read JSON from stdin ---
$Json = [Console]::In.ReadToEnd()
if (-not $Json) { exit 0 }

try {
    $Payload = $Json | ConvertFrom-Json
} catch {
    exit 0
}

# Extract the written file path (handle both `file_path` and `filePath` shapes)
$FilePath = $null
if ($Payload.tool_input) {
    if ($Payload.tool_input.file_path)    { $FilePath = $Payload.tool_input.file_path }
    elseif ($Payload.tool_input.filePath) { $FilePath = $Payload.tool_input.filePath }
}
if (-not $FilePath) { exit 0 }

# Normalize to a full path with consistent separators
try {
    $FilePath = [System.IO.Path]::GetFullPath($FilePath)
} catch {
    exit 0
}

# --- Scope: must be inside Z:\Clone\ ---
$WikiRoot = "Z:\Clone"
try {
    $WikiRootFull = [System.IO.Path]::GetFullPath($WikiRoot)
} catch {
    exit 0
}
if (-not (Test-Path $WikiRootFull)) { exit 0 }

if (-not $FilePath.StartsWith($WikiRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    exit 0
}

# Relative path from wiki root
$RelPath = $FilePath.Substring($WikiRootFull.Length).TrimStart('\','/').Replace('/', '\')

# --- Carve-outs: don't commit these ---
# 00_inbox/ unrouted folders are farmer territory. Only _routed/ writes are
# clone-route output and worth auto-committing.
if ($RelPath -like "00_inbox\*" -and $RelPath -notlike "00_inbox\_routed\*") {
    exit 0
}
# Git's own files
if ($RelPath -like ".git\*" -or $RelPath -eq ".gitignore") {
    exit 0
}

# --- Type label for the commit message ---
$TypeLabel = "edit"
switch -Wildcard ($RelPath) {
    "experts\*"            { $TypeLabel = "expert"     ; break }
    "techniques\*"         { $TypeLabel = "technique"  ; break }
    "strategies\*"         { $TypeLabel = "strategy"   ; break }
    "tools\*"              { $TypeLabel = "tool"       ; break }
    "workflows\*"          { $TypeLabel = "workflow"   ; break }
    "prompts\*"            { $TypeLabel = "prompt"     ; break }
    "research\*"           { $TypeLabel = "research"   ; break }
    "inspiration\*"        { $TypeLabel = "inspiration"; break }
    "community\*"          { $TypeLabel = "community"  ; break }
    "00_inbox\_routed\*"   { $TypeLabel = "routed"     ; break }
    "_scripts\*"           { $TypeLabel = "script"     ; break }
}
if ($RelPath -eq "_index.md") { $TypeLabel = "index" }
elseif ($RelPath -eq "_log.md") { $TypeLabel = "log" }
elseif ($RelPath -eq "CLAUDE.md") { $TypeLabel = "schema" }
elseif ($RelPath -eq "README.md") { $TypeLabel = "readme" }

$BaseName = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)

# --- Git operations ---
Push-Location $WikiRoot
try {
    # Is the file currently tracked? (Untracked => "new", tracked => "update")
    & git ls-files --error-unmatch -- $FilePath 2>&1 | Out-Null
    $IsUntracked = ($LASTEXITCODE -ne 0)

    # If tracked and no diff vs HEAD or index, nothing to do
    if (-not $IsUntracked) {
        & git diff --quiet --       $FilePath 2>&1 | Out-Null
        $UnstagedChanges = ($LASTEXITCODE -ne 0)
        & git diff --cached --quiet $FilePath 2>&1 | Out-Null
        $StagedChanges   = ($LASTEXITCODE -ne 0)
        if (-not $UnstagedChanges -and -not $StagedChanges) {
            exit 0
        }
    }

    & git add -- $FilePath 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { exit 0 }

    $Action = if ($IsUntracked) { "new" } else { "update" }
    $Msg = "clone: $Action $TypeLabel - $BaseName"
    & git commit -m $Msg 2>&1 | Out-Null
} finally {
    Pop-Location
}

exit 0
