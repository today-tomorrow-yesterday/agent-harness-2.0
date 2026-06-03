# shield-watch.ps1
#
# Polls Claude Code config directories for changes. When a skill, plugin, agent,
# CLAUDE.md, or settings.json changes, runs `agentshield scan` against the
# affected profile and emits Windows Toast notifications for new HIGH or
# CRITICAL findings. Everything also written to the log.
#
# Designed to run as a Scheduled Task at user login, hidden window. Polling
# interval defaults to 1 hour (3600s) — minimal background load, detection
# lag is up to 1 hour. Override with -IntervalSeconds <n> for testing.
#
# Logs:        Z:\agent-os\agentshield-watch.log
# State file:  Z:\agent-os\bin\shield-state.json   (hash inventory + seen findings)
#
# Manual run (foreground, visible):
#     powershell -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1
#
# Manual run (single pass, exits after one scan):
#     powershell -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1 -Once

param(
    [switch]$Once = $false,
    [int]$IntervalSeconds = 3600
)

$ErrorActionPreference = "Continue"

# --- Paths ---
$AgentOsRoot = "Z:\agent-os"
$LogFile     = Join-Path $AgentOsRoot "agentshield-watch.log"
$StateFile   = Join-Path $AgentOsRoot "bin\shield-state.json"

$Profiles = @(
    @{ Name = "<YourOrg>";     Path = Join-Path $env:USERPROFILE ".claude-<profile>" }
    @{ Name = "personal"; Path = Join-Path $env:USERPROFILE ".claude" }
)

# Subdirectories within each profile that we monitor for changes
$WatchedSubdirs = @("skills", "plugins", "agents", "commands", "skills.d", "agents.d")

# Loose files (relative to profile root) that we also hash
$WatchedFiles = @("CLAUDE.md", "settings.json")

# --- Toast notifications ---
[void] [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void] [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]

function Show-Toast {
    param([string]$Title, [string]$Body)
    try {
        $TitleEscaped = $Title -replace '&', '&amp;' -replace '<', '&lt;' -replace '>', '&gt;'
        $BodyEscaped  = $Body  -replace '&', '&amp;' -replace '<', '&lt;' -replace '>', '&gt;'
        $XmlTemplate = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>$TitleEscaped</text>
            <text>$BodyEscaped</text>
        </binding>
    </visual>
</toast>
"@
        $XmlDoc = New-Object Windows.Data.Xml.Dom.XmlDocument
        $XmlDoc.LoadXml($XmlTemplate)
        $Toast = New-Object Windows.UI.Notifications.ToastNotification $XmlDoc
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("AgentShield").Show($Toast)
    } catch {
        Write-Log ("TOAST FAILED: {0}" -f $_)
    }
}

# --- Logging ---
$LogMaxBytes = 5MB
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $line = "$stamp [$Level] $Message"
    # Size-based rotation: keep one .1 backup, start fresh past $LogMaxBytes.
    try {
        if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt $LogMaxBytes)) {
            $bak = "$LogFile.1"
            if (Test-Path $bak) { Remove-Item $bak -Force }
            Move-Item $LogFile $bak -Force
        }
    } catch { }
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    if ($Once) { Write-Host $line }
}

# --- Inventory: list watched paths and hash their files ---
function Get-Inventory {
    param([hashtable]$ProfileSpec)

    $inv = @{}
    $profileRoot = $ProfileSpec.Path
    if (-not (Test-Path $profileRoot)) { return $inv }

    # Hash loose files
    foreach ($f in $WatchedFiles) {
        $full = Join-Path $profileRoot $f
        if (Test-Path $full -PathType Leaf) {
            try {
                $h = (Get-FileHash -Path $full -Algorithm SHA256 -ErrorAction Stop).Hash
                $inv[$full] = $h
            } catch { }
        }
    }

    # Hash files inside watched subdirs, skipping volatile runtime churn. The
    # plugin cache (esp. `\cache\...\.in_use\<pid>` lock files) changes on every
    # tick and is not security-relevant content — including it spammed the log
    # with thousands of bogus added/removed lines per run.
    foreach ($sub in $WatchedSubdirs) {
        $dir = Join-Path $profileRoot $sub
        if (Test-Path $dir -PathType Container) {
            Get-ChildItem -Path $dir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                if ($_.FullName -match '\\cache\\' -or $_.FullName -match '\.in_use') { return }
                try {
                    $h = (Get-FileHash -Path $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
                    $inv[$_.FullName] = $h
                } catch { }
            }
        }
    }
    return $inv
}

# --- State: persist inventories + seen findings between runs ---

# Windows PowerShell 5.1 has no `ConvertFrom-Json -AsHashtable` (PS 6+ only), so
# walk the PSCustomObject graph and rebuild it as nested hashtables. Without this,
# Load-State threw on every cold start and the watcher silently lost all state
# (re-toasting every HIGH finding and re-logging the full inventory as "added").
function ConvertTo-HashtableDeep {
    param($InputObject)
    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $ht = @{}
        foreach ($k in $InputObject.Keys) { $ht[$k] = ConvertTo-HashtableDeep $InputObject[$k] }
        return $ht
    }
    if ($InputObject -is [System.Management.Automation.PSCustomObject]) {
        $ht = @{}
        foreach ($prop in $InputObject.PSObject.Properties) { $ht[$prop.Name] = ConvertTo-HashtableDeep $prop.Value }
        return $ht
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string]) {
        return @($InputObject | ForEach-Object { ConvertTo-HashtableDeep $_ })
    }
    return $InputObject
}

function Load-State {
    if (Test-Path $StateFile) {
        try {
            $raw = Get-Content -Raw -Path $StateFile -Encoding utf8
            $ht  = ConvertTo-HashtableDeep ($raw | ConvertFrom-Json)
            if ($ht -isnot [hashtable]) { $ht = @{} }
            if (-not $ht.ContainsKey('inventories'))   { $ht['inventories']   = @{} }
            if (-not $ht.ContainsKey('seen_findings')) { $ht['seen_findings'] = @{} }
            return $ht
        } catch {
            Write-Log "Could not read state file, starting fresh: $_" "WARN"
        }
    }
    return @{
        inventories    = @{}   # profile name -> @{ path -> hash }
        seen_findings  = @{}   # finding key -> true (so we don't re-toast)
    }
}

function Save-State {
    param([hashtable]$State)
    try {
        ($State | ConvertTo-Json -Depth 10) | Set-Content -Path $StateFile -Encoding utf8
    } catch {
        Write-Log "Could not save state: $_" "ERROR"
    }
}

# --- Diff inventories ---
function Diff-Inventory {
    param([hashtable]$Prev, [hashtable]$Curr)

    $added    = @()
    $removed  = @()
    $modified = @()

    foreach ($k in $Curr.Keys) {
        if (-not $Prev.ContainsKey($k)) { $added += $k }
        elseif ($Prev[$k] -ne $Curr[$k]) { $modified += $k }
    }
    foreach ($k in $Prev.Keys) {
        if (-not $Curr.ContainsKey($k)) { $removed += $k }
    }
    return @{ added = $added; removed = $removed; modified = $modified }
}

# --- Run AgentShield scan against a profile, return parsed findings ---
function Invoke-Scan {
    param([string]$ProfilePath)

    $output = $null
    try {
        $output = & npx --yes ecc-agentshield scan --path $ProfilePath --format json --min-severity high 2>&1 | Out-String
    } catch {
        Write-Log ("Scan invocation failed for {0}: {1}" -f $ProfilePath, $_) "ERROR"
        return @()
    }

    # The CLI emits human chrome around the JSON. Extract the first {...} block.
    $jsonMatch = [regex]::Match($output, '(?s)\{.*\}')
    if (-not $jsonMatch.Success) {
        Write-Log ("Scan output for {0} did not contain JSON; raw output saved to log" -f $ProfilePath) "WARN"
        Write-Log ("RAW: {0}" -f $output) "DEBUG"
        return @()
    }

    try {
        $parsed = $jsonMatch.Value | ConvertFrom-Json
        if ($parsed.findings) { return $parsed.findings }
        return @()
    } catch {
        Write-Log ("Could not parse scan JSON for {0}: {1}" -f $ProfilePath, $_) "WARN"
        return @()
    }
}

# --- Main loop iteration ---
function Invoke-Tick {
    param([hashtable]$State)

    foreach ($p in $Profiles) {
        $curr = Get-Inventory -ProfileSpec $p
        $prevName = $p.Name
        $prev = @{}
        if ($State.inventories.ContainsKey($prevName)) {
            # ConvertFrom-Json -AsHashtable returns nested hashtables; coerce
            $prevRaw = $State.inventories[$prevName]
            if ($prevRaw -is [hashtable]) { $prev = $prevRaw }
            elseif ($prevRaw) {
                $prevRaw.PSObject.Properties | ForEach-Object { $prev[$_.Name] = $_.Value }
            }
        }

        $diff = Diff-Inventory -Prev $prev -Curr $curr
        $changeCount = $diff.added.Count + $diff.removed.Count + $diff.modified.Count

        if ($changeCount -gt 0) {
            $summary = "{0} profile changed: {1} added, {2} modified, {3} removed" -f $prevName, $diff.added.Count, $diff.modified.Count, $diff.removed.Count
            Write-Log $summary
            foreach ($f in $diff.added)    { Write-Log ("  + {0}" -f $f) }
            foreach ($f in $diff.modified) { Write-Log ("  ~ {0}" -f $f) }
            foreach ($f in $diff.removed)  { Write-Log ("  - {0}" -f $f) }

            # Trigger AgentShield scan
            Write-Log ("Running agentshield scan on {0} ..." -f $p.Path)
            $findings = Invoke-Scan -ProfilePath $p.Path

            $newCount = 0
            foreach ($finding in $findings) {
                $severity = "$($finding.severity)".ToUpper()
                if ($severity -notin @("CRITICAL", "HIGH")) { continue }

                # Build a stable dedupe key
                $key = "$($p.Name)::$severity::$($finding.file)::$($finding.line)::$($finding.title)"
                if ($State.seen_findings.ContainsKey($key)) { continue }

                $State.seen_findings[$key] = $true
                $newCount++

                $title = "{0} - {1}" -f $severity, $finding.title
                $body  = "{0}:{1} [{2} profile]" -f $finding.file, $finding.line, $p.Name

                Write-Log ("ALERT {0} // {1}" -f $title, $body) $severity
                Show-Toast -Title $title -Body $body
            }

            if ($newCount -eq 0 -and $findings.Count -gt 0) {
                Write-Log ("Scan returned {0} findings, none new" -f $findings.Count)
            } elseif ($findings.Count -eq 0) {
                Write-Log "Scan returned no HIGH+ findings"
            }
        }

        $State.inventories[$p.Name] = $curr
    }

    Save-State -State $State
}

# --- Entry ---

Write-Log ("shield-watch starting (Once={0}, IntervalSeconds={1})" -f $Once, $IntervalSeconds)

if (-not (Test-Path (Split-Path $StateFile))) {
    New-Item -ItemType Directory -Path (Split-Path $StateFile) -Force | Out-Null
}

$state = Load-State

# Open-findings digest: the dedup cache suppresses findings after first sight so
# they never re-toast, which meant standing HIGH/CRITICAL findings became
# invisible. Log the full open set on every launch so they remain greppable and
# get re-surfaced at least once per restart (review with bin\shield-alerts.py).
if ($state.seen_findings -and $state.seen_findings.Count -gt 0) {
    Write-Log ("OPEN FINDINGS DIGEST: {0} acknowledged HIGH/CRITICAL finding(s) currently suppressed from re-toasting:" -f $state.seen_findings.Count) "WARN"
    foreach ($k in ($state.seen_findings.Keys | Sort-Object)) {
        Write-Log ("  OPEN: {0}" -f $k) "WARN"
    }
}

if ($Once) {
    Invoke-Tick -State $state
    Write-Log "shield-watch single-pass complete"
    exit 0
}

# Persistent loop
while ($true) {
    try {
        Invoke-Tick -State $state
    } catch {
        Write-Log ("Tick failed: {0}" -f $_) "ERROR"
    }
    Start-Sleep -Seconds $IntervalSeconds
}
