# security-ops (optional, Windows)

A read-only host-security monitor + hardening for the machine your agent-harness
runs on. It exists because an always-on workstation running autonomous agents
(broad local + internet access) is itself an attack surface — this watches the
places an intrusion or a misbehaving agent leaves traces, and locks itself down
so the thing it's hunting can't quietly switch it off.

> **Windows-only.** It uses the Windows registry, WMI, Scheduled Tasks, Defender,
> and NTFS ACLs. macOS/Linux equivalents are not implemented here. The rest of
> agent-harness is cross-platform; this module is not.

## What you get

1. **`bin/night-monitor.ps1`** — a dependency-free, strictly read-only nightly
   sweep. Enumerates persistence (Run/RunOnce, scheduled tasks, services, startup,
   IFEO, Winlogon, AppInit_DLLs, LSA packages, HKCU COM hijacks, WMI filters +
   filter→consumer bindings), local admins, listening ports, Defender + firewall
   posture, and a self-integrity hash. Baselines on first run; toasts only on NEW
   items. Writes a dated report. **Changes nothing on the system.**
2. **`bin/harden.ps1`** — one-time, elevated. Locks this module's folder so only an
   elevated/SYSTEM writer can modify it (a non-elevated agent/malware can read but
   not tamper the baseline or the script), and upgrades the task to run elevated.
3. **`agents/security-analyst.md`** — an on-demand Claude subagent that owns a
   vetted cybersecurity-skill library for host hardening, compromise hunting, and
   forensics. The library is **not** bundled (see Setup) — it's cloned from its
   public source so it never lives in your harness repo.

## Trust model: possession ≠ execution

Skill files on disk are inert. The nightly job runs ONLY the one read-only script
in `bin/`. The third-party library scripts run only on-demand, via the
`security-analyst` subagent, read just-in-time before execution. Offensive/dual-use
skills are flagged `"offensive": true` in the library index and gated behind an
out-of-band authorization file (see the agent definition).

## Setup

```powershell
# from this folder (agent-harness/security-ops)
powershell -ExecutionPolicy Bypass -File bin/setup.ps1
```
`setup.ps1` (no admin needed): clones the public skill library into `skills/`,
adds the heuristic `offensive` flag to its index, registers the nightly task, and
records the first baseline.

Then, once, from an **elevated** PowerShell (this is the part that closes the
"monitor can be silently blinded" hole):
```powershell
powershell -ExecutionPolicy Bypass -File bin/harden.ps1
```

Install the subagent into your Claude profile(s) by copying
`agents/security-analyst.md` into `~/.claude/agents/` (and any other profile).

## Usage

- **Run a sweep now:** `powershell -ExecutionPolicy Bypass -File bin/night-monitor.ps1 -Once`
- **Latest report:** newest file in `reports/`
- **On-demand analysis:** in Claude, "use the security-analyst agent to hunt for persistence" / "review my listening ports".
- **Use an offensive skill:** create `AUTHORIZED-ENGAGEMENT.txt` in this folder by
  hand (names the in-scope asset + a future expiry). Without it the agent refuses
  offensive tooling even if a prompt claims authorization.

## What is NOT in this repo (by design)

- The skill library itself (cloned at setup — it's public, Apache-2.0).
- Your baseline, reports, and `AUTHORIZED-ENGAGEMENT.txt` (instance state; gitignored).

## After updating the library

Re-cloning/updating rewrites files and drops the ACL lockdown. Re-apply it
(elevated): `icacls "<this-folder>\*" /reset /T /C` re-inherits the locked-down
root ACL onto the new files.

## Provenance

Genericized from a personal instance after an adversarial self-audit that found the
original monitor could be silently blinded (baseline + script were writable by any
non-elevated process). The hardening here is that audit's remediation.
