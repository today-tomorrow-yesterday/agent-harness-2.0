# night-monitor.ps1 — read-only host security sweep (Windows). Part of the
# agent-harness security-ops module.
#
# Dependency-free, STRICTLY READ-ONLY. Enumerates the places an intrusion or a
# misbehaving autonomous agent leaves traces, diffs against a stored baseline,
# writes a dated report, and toasts only on NEW items. It changes NOTHING on the
# system (no Set-/Remove-/Stop-/New- except writing its own report + state).
#
# First run = baseline (records current state, no alerts).
# Manual run:  powershell -ExecutionPolicy Bypass -File bin\night-monitor.ps1 -Once
#
# Paths are resolved relative to this module (no hardcoded drive/user), so it works
# in any clone. Run bin\harden.ps1 once (elevated) to ACL-lock the module so a
# non-elevated process can't tamper the baseline or this script.

param([switch]$Once = $false)
$ErrorActionPreference = "Continue"

$Root      = Split-Path $PSScriptRoot -Parent          # the security-ops module dir
$ReportDir = Join-Path $Root "reports"
$StateFile = Join-Path $ReportDir "monitor-state.json"
$LogFile   = Join-Path $ReportDir "night-monitor.log"
$SkillsDir = Join-Path $Root "skills"
$BinDir    = $PSScriptRoot
$ERR       = "__COLLECTOR_ERROR__"                      # sentinel: a collector failed (blind spot) vs. genuinely empty
$now       = Get-Date
$stamp     = $now.ToString("yyyy-MM-dd_HHmm")

if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null }
function Write-Log { param($m) Add-Content -Path $LogFile -Value ("{0} {1}" -f $now.ToString("s"), $m) -Encoding utf8 }

# --- Toast (raw WinRT) ---
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
function Show-Toast {
    param($Title, $Body)
    try {
        $t = ($Title -replace '&','&amp;' -replace '<','&lt;' -replace '>','&gt;')
        $b = ($Body  -replace '&','&amp;' -replace '<','&lt;' -replace '>','&gt;')
        $xml = "<toast><visual><binding template=`"ToastGeneric`"><text>$t</text><text>$b</text></binding></visual></toast>"
        $d = New-Object Windows.Data.Xml.Dom.XmlDocument; $d.LoadXml($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SecurityOps").Show((New-Object Windows.UI.Notifications.ToastNotification $d))
    } catch { Write-Log "TOAST FAILED: $_" }
}

# --- Read-only collectors. Each returns string[] of normalized "item" identities.
# On failure a collector returns @("$ERR <msg>") so a failed check is flagged as a
# blind spot instead of silently treated as "clean". ---
function Get-Snapshot {
    $snap = [ordered]@{}

    try {
        $runKeys = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
            "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
            "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\RunOnce"
        )
        $items = @()
        foreach ($k in $runKeys) {
            if (Test-Path $k) {
                $p = Get-ItemProperty -Path $k -ErrorAction Stop
                $p.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object {
                    $items += "$k :: $($_.Name) = $($_.Value)"
                }
            }
        }
        $snap["run_keys"] = $items
    } catch { $snap["run_keys"] = @("$ERR $($_.Exception.Message)") }

    try {
        $snap["scheduled_tasks"] = @(Get-ScheduledTask -ErrorAction Stop |
            Where-Object { $_.TaskPath -notlike '\Microsoft\*' } |
            ForEach-Object { "$($_.TaskPath)$($_.TaskName) [$($_.State)]" })
    } catch { $snap["scheduled_tasks"] = @("$ERR $($_.Exception.Message)") }

    try {
        $startup = @([Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup'))
        $items = @()
        foreach ($s in $startup) {
            if (Test-Path $s) { Get-ChildItem $s -File -ErrorAction SilentlyContinue | ForEach-Object { $items += $_.FullName } }
        }
        $snap["startup_folder"] = $items
    } catch { $snap["startup_folder"] = @("$ERR $($_.Exception.Message)") }

    # Auto-start services NOT Microsoft-Authenticode-signed (keyed on signature, not path).
    try {
        $snap["auto_services"] = @(Get-CimInstance Win32_Service -ErrorAction Stop |
            Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName } |
            ForEach-Object {
                $pn  = $_.PathName
                $exe = if ($pn -match '^\s*"([^"]+)"') { $matches[1] } elseif ($pn -match '^\s*([^\s]+\.exe)') { $matches[1] } else { $null }
                $isMs = $false
                if ($exe -and (Test-Path $exe)) {
                    try {
                        $sig = Get-AuthenticodeSignature $exe -ErrorAction Stop
                        if ($sig.Status -eq 'Valid' -and $sig.SignerCertificate.Subject -match 'Microsoft') { $isMs = $true }
                    } catch {}
                }
                if (-not $isMs) { "$($_.Name) -> $pn" }
            } | Where-Object { $_ })
    } catch { $snap["auto_services"] = @("$ERR $($_.Exception.Message)") }

    try {
        $items = @()
        foreach ($r in @(
            "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options",
            "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows NT\CurrentVersion\Image File Execution Options")) {
            if (Test-Path $r) {
                Get-ChildItem $r -ErrorAction SilentlyContinue | ForEach-Object {
                    $d = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
                    if ($d.Debugger)   { $items += "$($_.PSChildName) Debugger=$($d.Debugger)" }
                    if ($d.GlobalFlag) { $items += "$($_.PSChildName) GlobalFlag=$($d.GlobalFlag)" }
                }
            }
        }
        $snap["ifeo_debuggers"] = $items
    } catch { $snap["ifeo_debuggers"] = @("$ERR $($_.Exception.Message)") }

    try {
        $items = @()
        $w = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -ErrorAction Stop
        foreach ($n in 'Shell','Userinit','Taskman','GinaDLL') { if ($w.$n) { $items += "$n=$($w.$n)" } }
        $snap["winlogon"] = $items
    } catch { $snap["winlogon"] = @("$ERR $($_.Exception.Message)") }

    try {
        $items = @()
        foreach ($r in @(
            "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Windows",
            "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows NT\CurrentVersion\Windows")) {
            if (Test-Path $r) {
                $a = Get-ItemProperty $r -ErrorAction SilentlyContinue
                if ($a.AppInit_DLLs) { $items += "AppInit_DLLs=$($a.AppInit_DLLs) (Load=$($a.LoadAppInit_DLLs))" }
            }
        }
        $snap["appinit_dlls"] = $items
    } catch { $snap["appinit_dlls"] = @("$ERR $($_.Exception.Message)") }

    try {
        $items = @()
        $l = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa" -ErrorAction Stop
        foreach ($n in 'Security Packages','Authentication Packages','Notification Packages') {
            if ($l.$n) { $items += "$n=$(($l.$n) -join ',')" }
        }
        $snap["lsa_packages"] = $items
    } catch { $snap["lsa_packages"] = @("$ERR $($_.Exception.Message)") }

    try {
        $items = @()
        $base = "HKCU:\Software\Classes\CLSID"
        if (Test-Path $base) {
            Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
                $ips = Join-Path $_.PSPath "InprocServer32"
                if (Test-Path $ips) {
                    $v = (Get-ItemProperty $ips -ErrorAction SilentlyContinue).'(default)'
                    if ($v) { $items += "$($_.PSChildName) -> $v" }
                }
            }
        }
        $snap["com_hijack_hkcu"] = $items
    } catch { $snap["com_hijack_hkcu"] = @("$ERR $($_.Exception.Message)") }

    try {
        $snap["wmi_consumers"] = @(Get-CimInstance -Namespace root\subscription -ClassName __EventConsumer -ErrorAction Stop |
            ForEach-Object { "$($_.__CLASS): $($_.Name)" })
    } catch { $snap["wmi_consumers"] = @("$ERR $($_.Exception.Message)") }
    try {
        $snap["wmi_filters"] = @(Get-CimInstance -Namespace root\subscription -ClassName __EventFilter -ErrorAction Stop |
            ForEach-Object { "$($_.Name): $($_.Query)" })
    } catch { $snap["wmi_filters"] = @("$ERR $($_.Exception.Message)") }
    try {
        $snap["wmi_bindings"] = @(Get-CimInstance -Namespace root\subscription -ClassName __FilterToConsumerBinding -ErrorAction Stop |
            ForEach-Object { "$($_.Filter) => $($_.Consumer)" })
    } catch { $snap["wmi_bindings"] = @("$ERR $($_.Exception.Message)") }

    try {
        $snap["local_admins"] = @(Get-LocalGroupMember -Group "Administrators" -ErrorAction Stop |
            ForEach-Object { $_.Name })
    } catch { $snap["local_admins"] = @("$ERR $($_.Exception.Message)") }

    try {
        $snap["listening_ports"] = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
            ForEach-Object {
                $pn = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName
                "$($_.LocalAddress):$($_.LocalPort) ($pn)"
            } | Sort-Object -Unique)
    } catch { $snap["listening_ports"] = @("$ERR $($_.Exception.Message)") }

    return $snap
}

function Get-Posture {
    $p = [ordered]@{}
    try { $d = Get-MpComputerStatus -ErrorAction Stop
          $p["defender_realtime"] = $d.RealTimeProtectionEnabled
          $p["defender_sigs_age_days"] = [math]::Round(((Get-Date) - $d.AntivirusSignatureLastUpdated).TotalDays,1)
    } catch { $p["defender"] = "unavailable" }
    try { $fw = Get-NetFirewallProfile -ErrorAction Stop
          foreach ($pr in $fw) { $p["firewall_$($pr.Name)"] = $pr.Enabled }
    } catch { $p["firewall"] = "unavailable" }
    return $p
}

# Integrity: hash the library (skills + index.json) AND this module's own bin\,
# so a silent edit to the monitor itself is detected too.
function Get-IntegrityHash {
    $files = @()
    if (Test-Path $SkillsDir) {
        $files += Get-ChildItem $SkillsDir -Recurse -File -Include *.py,*.ps1,*.sh,SKILL.md,index.json -ErrorAction SilentlyContinue
    }
    if (Test-Path $BinDir) {
        $files += Get-ChildItem $BinDir -Recurse -File -Include *.ps1 -ErrorAction SilentlyContinue
    }
    if (-not $files) { return "no-library" }
    $h = $files | Sort-Object FullName | ForEach-Object { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($h -join "`n")))).Replace("-","")
}

$prev = $null
if (Test-Path $StateFile) {
    try { $prev = Get-Content $StateFile -Raw -Encoding utf8 | ConvertFrom-Json } catch { Write-Log "STATE LOAD FAILED (treating as baseline): $_" }
}

$snap       = Get-Snapshot
$posture    = Get-Posture
$libHash    = Get-IntegrityHash
$isBaseline = ($null -eq $prev)

$newFindings = @()
$errored     = @()
if (-not $isBaseline) {
    foreach ($cat in $snap.Keys) {
        $items = @($snap[$cat])
        $errs  = @($items | Where-Object { $_ -like "$ERR*" })
        if ($errs.Count -gt 0) {
            $newFindings += "[$cat] COLLECTOR FAILED - blind spot this run: $($errs -join '; ')"
            $errored     += $cat
            continue
        }
        $prevItems = @(); if ($prev.snapshot.$cat) { $prevItems = @($prev.snapshot.$cat) }
        foreach ($item in $items) {
            if ($prevItems -notcontains $item) { $newFindings += "[$cat] NEW: $item" }
        }
    }
    if ($prev.library_hash -and $prev.library_hash -ne $libHash) {
        $newFindings += "[integrity] Library/monitor hash CHANGED since last run - investigate skills/, index.json, or bin/"
    }
    if ($posture.defender_realtime -eq $false) { $newFindings += "[posture] Defender real-time protection is OFF" }
    foreach ($k in $posture.Keys) { if ($k -like 'firewall_*' -and $posture[$k] -eq $false) { $newFindings += "[posture] Firewall profile $k is DISABLED" } }
}

$report = @()
$report += "# Night host-security sweep - $stamp"
$report += ""
$report += if ($isBaseline) { "**BASELINE run** - recorded current state, no diff yet." }
           elseif ($newFindings.Count -eq 0) { "**Clean.** No new persistence/account/network items since last run." }
           else { "**$($newFindings.Count) new/blind item(s) since last run** (below)." }
$report += ""
if ($errored.Count -gt 0) { $report += "> WARNING: $($errored.Count) collector(s) failed this run (blind spots): $($errored -join ', '). Baseline preserved for these." ; $report += "" }
$report += "## Posture"
foreach ($k in $posture.Keys) { $report += "- $k = $($posture[$k])" }
$report += ""
if ($newFindings.Count -gt 0) {
    $report += "## New since last run"
    foreach ($f in $newFindings) { $report += "- $f" }
    $report += ""
}
$report += "## Current snapshot (counts)"
foreach ($cat in $snap.Keys) {
    $c = @($snap[$cat])
    $label = if ($c | Where-Object { $_ -like "$ERR*" }) { "ERROR" } else { "$($c.Count)" }
    $report += "- $cat : $label"
}
$report += ""
$report += "_Integrity hash (skills+index+bin): $($libHash.Substring(0,16))_"
$report += "_Read-only sweep. No system state was modified._"

$reportPath = Join-Path $ReportDir "$stamp.md"
$report -join "`r`n" | Set-Content -Path $reportPath -Encoding utf8

# Save state. Carry prior baseline forward for any errored category; never persist
# the error sentinel or an empty array that would erase real memory.
$stateSnap = [ordered]@{}
foreach ($cat in $snap.Keys) {
    $items = @($snap[$cat])
    if ($items | Where-Object { $_ -like "$ERR*" }) {
        if ($prev -and $prev.snapshot.$cat) { $stateSnap[$cat] = @($prev.snapshot.$cat) }
        else { $stateSnap[$cat] = @() }
    } else {
        $stateSnap[$cat] = $items
    }
}
@{ timestamp = $now.ToString("s"); snapshot = $stateSnap; posture = $posture; library_hash = $libHash } |
    ConvertTo-Json -Depth 8 | Set-Content -Path $StateFile -Encoding utf8

Write-Log ("sweep done: baseline={0} new={1} errored={2} report={3}" -f $isBaseline, $newFindings.Count, $errored.Count, $reportPath)
if ($isBaseline) {
    Show-Toast "SecurityOps: baseline recorded" "First sweep complete. Future runs alert on changes."
} elseif ($newFindings.Count -gt 0) {
    $toastBody = ($newFindings | Select-Object -First 3) -join " | "
    Show-Toast "SecurityOps: $($newFindings.Count) new host change(s)" $toastBody
}
if ($Once) { Write-Host (($report) -join "`n") }
