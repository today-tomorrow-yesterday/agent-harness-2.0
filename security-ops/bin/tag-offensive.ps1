# tag-offensive.ps1 — add a heuristic "offensive": true field to clearly-offensive
# skills in the library index, so the security-analyst subagent can gate them.
# Offensive ACTION verbs + known C2/red-team frameworks, MINUS a defensive override
# (detection / analysis / IR / forensics / hardening are never flagged). Idempotent.
param(
    [string]$IndexPath = (Join-Path (Split-Path $PSScriptRoot -Parent) "skills\index.json")
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $IndexPath)) { throw "index.json not found at $IndexPath" }
$json = Get-Content $IndexPath -Raw | ConvertFrom-Json

$verbs       = '^(exploiting|deploying|establishing|executing|bypassing|escalating|dumping|cracking|injecting|evading|abusing|hijacking|spoofing|poisoning|relaying|tunneling|pivoting|harvesting|phishing|brute-forcing|spraying|kerberoasting|impersonating|backdooring|obfuscating|weaponizing|exfiltrating|lateral)-'
$frameworks  = '(sliver|havoc|covenant|mythic|cobalt-strike|powershell-empire|metasploit|msfvenom|mimikatz|dcsync|golden-ticket|silver-ticket|pass-the-hash|pass-the-ticket|ntlm-relay|reverse-shell|bind-shell|shellcode|process-injection|dll-injection|process-hollowing|amsi-bypass|uac-bypass|edr-evasion)'
$engagements = '(penetration-test|pen-test|red-team|adversary-emulation|c2-infrastructure|domain-persistence|man-in-the-middle-attack|lateral-movement|privilege-escalation|password-spray|credential-(dumping|harvesting|theft))'
$defensive   = '^(analyzing|detecting|hunting|investigating|monitoring|parsing|auditing|reviewing|baselining|hardening|securing|defending|patching|enabling|configuring|responding)|(incident-response|forensic|threat-hunting|detection-engineering|blue-team)'

$count = 0
foreach ($s in $json.skills) {
    if ($s.PSObject.Properties.Name -contains 'offensive') { $s.PSObject.Properties.Remove('offensive') }
    $n = $s.name.ToLower()
    if ((($n -match $verbs) -or ($n -match $frameworks) -or ($n -match $engagements)) -and ($n -notmatch $defensive)) {
        $s | Add-Member -NotePropertyName offensive -NotePropertyValue $true -Force; $count++
    }
}
$json | ConvertTo-Json -Depth 8 -Compress | Set-Content $IndexPath -Encoding utf8
Write-Output "Flagged $count of $($json.skills.Count) skills as offensive in $IndexPath"
