# harden.ps1 — ONE-TIME lockdown for the security-ops module. RUN ELEVATED.
#
# Closes the "a diff-monitor whose baseline is writable by the threat it hunts can
# be silently blinded" hole. After this, a non-elevated process (agent / malware
# at your privilege) can READ the module but cannot rewrite the baseline or the
# monitor script. The nightly task is elevated so it retains write.
#
# Fully parameterized — no hardcoded drive/user. Defaults target THIS module and
# the current user.
param(
    [string]$Root     = (Split-Path $PSScriptRoot -Parent),
    [string]$TaskName = "agent-harness-security-ops",
    [string]$User     = "$env:USERDOMAIN\$env:USERNAME"
)
$ErrorActionPreference = 'Stop'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host 'ERROR: not elevated. Re-run from an Administrator PowerShell.' -ForegroundColor Red
    exit 1
}

Write-Host "== 1/3  Task '$TaskName' -> highest privileges (so it can write the locked baseline) =="
try {
    $p = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
    Set-ScheduledTask -TaskName $TaskName -Principal $p | Out-Null
    Write-Host "   done."
} catch { Write-Host "   skipped (task '$TaskName' not found - run setup.ps1 first): $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Host "== 2/3  Owner -> Administrators (a non-elevated process can no longer rewrite the DACL) =="
icacls $Root /setowner 'Administrators' /T /C | Out-Null

# Well-known SIDs (locale-independent): Administrators=S-1-5-32-544, SYSTEM=S-1-5-18, Users=S-1-5-32-545.
Write-Host "== 3/3  DACL: Administrators+SYSTEM Full, Users Read/Execute; inherited write removed =="
icacls $Root /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' /T /C | Out-Null
# /inheritance:r drops the (OI)(CI) flags on files, which can strip the Users ACE
# from files; re-inherit on children so files get Users:RX from the folder ACL.
icacls "$Root\*" /reset /T /C | Out-Null

Write-Host "`n== VERIFY ==" -ForegroundColor Cyan
icacls "$Root\bin\night-monitor.ps1"
Write-Host "`nDone. Non-elevated can read/run; only elevated/SYSTEM can write." -ForegroundColor Green
Write-Host "Test sweep (elevated): powershell -ExecutionPolicy Bypass -File `"$Root\bin\night-monitor.ps1`" -Once"
