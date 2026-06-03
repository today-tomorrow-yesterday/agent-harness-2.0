---
name: agentshield-watch
description: Configure, inspect, debug, or remove the AgentShield security watcher that monitors Claude Code config changes on this machine. Use when the user asks about shield-watch.ps1, the hourly security scan, toast notifications from agent-os, the shield-state.json file, agentshield-watch.log, or wants to add/remove watched directories, change polling cadence, adjust severity threshold, switch notification modes, or uninstall the watcher.
---

# AgentShield Watch — operator skill

This skill documents the always-running security watcher you installed on 2026-05-23 to detect when sub-agents (or anything else) install new skills, plugins, or agents into his Claude Code profiles without explicit awareness.

## What this is and why it exists

you runs Claude Code with two profiles on this machine: `.claude-<profile>` (<YourOrg> work) and `.claude` (personal). Both can install skills, plugins, agents, MCP servers, and hooks — sometimes via sub-agents he didn't directly approve each time.

The threat model: a sub-agent installs a skill or plugin that carries prompt-injection bait, secret-exfiltration logic, or an over-permissive hook. you might not notice until damage is done.

The watcher catches this by:
1. Polling the file system in both profiles on a schedule
2. Detecting added/modified/removed files in skill/plugin/agent paths
3. Running `npx ecc-agentshield scan` when changes appear
4. Toasting you (Windows notification) for any *new* HIGH or CRITICAL finding
5. Logging everything for after-the-fact review

It is **reactive, not preventive**. It does not block tool calls or installs (that would require `agentshield runtime install`, which we explicitly skipped to keep Claude's request path latency-free). It tells you something happened so he can investigate and roll back if needed.

## Architecture at a glance

```
   Claude Code (interactive session)
     ↓ tool calls
     ↓ NEVER touches AgentShield  ← zero added latency
   Done.

   AgentShield-Watch (Windows Scheduled Task, hidden PowerShell)
     ↓ wakes every IntervalSeconds (default 3600 = 1 hour)
     ↓ hashes files under watched paths
     ↓ diffs against shield-state.json
     ↓ if anything changed → runs `npx ecc-agentshield scan`
     ↓ for each NEW HIGH/CRITICAL finding → toast + log
     ↓ updates state
```

## Files involved

| File | Purpose |
|---|---|
| `Z:\agent-os\bin\shield-watch.ps1` | The watcher loop (PowerShell). Polls, hashes, scans, toasts, logs. |
| `Z:\agent-os\bin\shield-alerts.py` | On-demand log viewer. Filters by severity and time window. |
| `Z:\agent-os\bin\install-shield-watch.bat` | Registers the Scheduled Task at `ONLOGON` trigger. User-scoped; no admin. |
| `Z:\agent-os\bin\uninstall-shield-watch.bat` | Stops and removes the Scheduled Task. Log + state preserved. |
| `Z:\agent-os\bin\shield-state.json` | Persisted state: per-profile file hash inventory + `seen_findings` dedupe table. Auto-managed. |
| `Z:\agent-os\agentshield-watch.log` | Append-only log. UTF-8 with BOM. Lines: `<ISO-timestamp> [<LEVEL>] <message>`. |

The watcher itself runs under the Scheduled Task name **`AgentShield-Watch`**. Hidden window, no admin, fires at user logon.

## What it watches

For each profile (`.claude-<profile>` and `.claude`):

- Loose files: `CLAUDE.md`, `settings.json`
- Subdirectories (recursive): `skills/`, `plugins/`, `agents/`, `commands/`, `skills.d/`, `agents.d/`

The path lists live in `shield-watch.ps1` at the top:

```powershell
$WatchedSubdirs = @("skills", "plugins", "agents", "commands", "skills.d", "agents.d")
$WatchedFiles   = @("CLAUDE.md", "settings.json")
$Profiles = @(
    @{ Name = "<profile2>"; Path = Join-Path $env:USERPROFILE ".claude-<profile2>" }
    @{ Name = "personal"; Path = Join-Path $env:USERPROFILE ".claude" }
)
```

Edit those arrays to expand/contract coverage. After editing, the next scheduled tick picks up the new paths automatically.

## How to operate it

### Inspect

```powershell
# Latest HIGH/CRITICAL alerts
python Z:\agent-os\bin\shield-alerts.py

# Last 50 lines (any severity)
python Z:\agent-os\bin\shield-alerts.py --tail 50

# Anything new in the past day
python Z:\agent-os\bin\shield-alerts.py --since 24h

# Anything new in the past hour
python Z:\agent-os\bin\shield-alerts.py --since 1h

# Full log
python Z:\agent-os\bin\shield-alerts.py --all

# Confirm the Scheduled Task is registered and its status
schtasks /Query /TN AgentShield-Watch /V /FO LIST
```

### Run a one-shot scan right now

```powershell
# Inside an existing scheduled task — triggers an immediate tick
schtasks /Run /TN AgentShield-Watch

# Or run the script standalone, single pass, visible output
powershell -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1 -Once

# Or run a temporarily-faster persistent loop for testing
powershell -ExecutionPolicy Bypass -File Z:\agent-os\bin\shield-watch.ps1 -IntervalSeconds 60
```

### Stop / start the watcher

```powershell
schtasks /End    /TN AgentShield-Watch   # stop current run
schtasks /Run    /TN AgentShield-Watch   # start it back up
```

### Uninstall

```powershell
Z:\agent-os\bin\uninstall-shield-watch.bat
```

Removes the task. Preserves the log and state file (delete those manually if you want a clean slate).

## How to configure it

### Change polling cadence

Edit `Z:\agent-os\bin\shield-watch.ps1` line ~28:

```powershell
[int]$IntervalSeconds = 3600   # 1 hour (current default)
```

Common values:
- `60` — every minute (used for testing; high disk I/O if plugin dirs are large)
- `300` — every 5 minutes
- `1800` — every 30 minutes
- `3600` — every 1 hour (current default — balances detection lag vs. background cost)
- `21600` — every 6 hours (minimal load, long detection lag)

After editing, re-trigger the scheduled task to pick up the new value: `schtasks /End /TN AgentShield-Watch; schtasks /Run /TN AgentShield-Watch`. The script reads the default param value at startup.

### Add or remove watched directories

Edit the `$WatchedSubdirs` and `$WatchedFiles` arrays at the top of `shield-watch.ps1`. Restart the task.

If you add a directory that already contains files, the next tick will see them all as "added" and baseline them. Any HIGH+ findings will toast once and then de-dupe.

### Change severity threshold for toasts

The script currently toasts only on `HIGH` and `CRITICAL`. To include `MEDIUM`, edit `shield-watch.ps1` and find the line:

```powershell
if ($severity -notin @("CRITICAL", "HIGH")) { continue }
```

Change to:

```powershell
if ($severity -notin @("CRITICAL", "HIGH", "MEDIUM")) { continue }
```

The scan itself already filters at the CLI layer via `--min-severity high`. To loosen the scan, change `--min-severity high` to `--min-severity medium` in the `Invoke-Scan` function. Be warned: MEDIUM and below include a lot of ECC-funnel-pattern noise (missing version metadata, observation hooks, etc.) that isn't actually security-relevant.

### Add a webhook (push to phone, Slack, etc.) in addition to toast

AgentShield supports `--alert webhook --webhook <url>` directly, but our current design parses scan output rather than relying on AgentShield's own alert mode. To add a webhook:

1. Pick a target. Easiest free option: [ntfy.sh](https://ntfy.sh) — no account, just a URL like `https://ntfy.sh/your-secret-topic-name`.
2. Add a function to `shield-watch.ps1`:

```powershell
function Send-Webhook {
    param([string]$Title, [string]$Body)
    try {
        $payload = @{ title = $Title; message = $Body; priority = 4 } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "https://ntfy.sh/your-topic-here" -Body $payload -ContentType "application/json"
    } catch {
        Write-Log ("WEBHOOK FAILED: {0}" -f $_)
    }
}
```

3. In the finding loop, call it alongside `Show-Toast`:

```powershell
Show-Toast -Title $title -Body $body
Send-Webhook -Title $title -Body $body
```

### Watch only one profile instead of both

Edit `$Profiles` at the top of `shield-watch.ps1`. Comment out or remove the entry you don't want monitored.

### Disable temporarily without uninstalling

```powershell
schtasks /Change /TN AgentShield-Watch /DISABLE
# To re-enable:
schtasks /Change /TN AgentShield-Watch /ENABLE
```

## How to debug if something seems wrong

### Toasts aren't appearing

1. Check Windows Focus Assist / Do Not Disturb — may be suppressing them.
2. Confirm toasts can fire at all:
   ```powershell
   powershell -Command "[void] [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]; [void] [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]; $x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml('<toast><visual><binding template=ToastGeneric><text>test</text></binding></visual></toast>' -replace 'ToastGeneric', '\"ToastGeneric\"'); $t = New-Object Windows.UI.Notifications.ToastNotification $x; [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Test').Show($t)"
   ```
3. Check the log for `TOAST FAILED:` lines.

### Watcher seems silent for too long

1. `schtasks /Query /TN AgentShield-Watch /V /FO LIST` — confirm it's still running.
2. Tail the log: `python Z:\agent-os\bin\shield-alerts.py --tail 30`. You should see periodic INFO lines about ticks even if no findings.
3. Run a one-shot to force a scan: `schtasks /Run /TN AgentShield-Watch`.

### Old findings keep retoasting

The dedupe key is `profile::severity::file::line::title`. If any of those change (e.g., the plugin updates and the line number shifts), the same logical finding will appear "new" and re-toast once. To clear dedupe and start fresh:

```powershell
Remove-Item Z:\agent-os\bin\shield-state.json
```

The next tick will re-baseline. Existing files will surface their HIGH+ findings once (one toast each), then dedupe normally.

### `npx ecc-agentshield scan` itself errors

The watcher logs `Scan invocation failed for <path>` lines when this happens. Common causes:
- npm cache cleared — the next invocation re-downloads, which is slow. Just wait one cycle.
- Network down — npm uses offline cache, but first invocation of a new version needs network.
- Disk full — check.

## Design decisions captured (so future-you can argue with them)

| Decision | Why |
|---|---|
| Watch (reactive) instead of `runtime install` (preventive) | PreToolUse hook adds latency to every Claude tool call. With six existing claude-brain hooks already running, stacking another active hook made the cost > benefit for your threat model. |
| Polling instead of FileSystemWatcher event-driven | FileSystemWatcher in PowerShell is fragile with long-running daemons and doesn't survive across user sessions well. Polling is dumber and more reliable. |
| 1-hour cadence (default) | Background cost basically zero. Acceptable detection lag for "I want to know if a sub-agent installed something today" use case. you explicitly chose this over 60s. |
| Scheduled Task `ONLOGON` instead of a service | No admin required. Survives reboots. Runs in user context so it has the right `~/.claude\` paths. |
| Hashing instead of mtime comparison | Some sub-agents may `touch` files without changing content (or vice versa). SHA-256 is the right granularity for "did the content actually change." |
| HIGH/CRITICAL toast threshold | LOW and INFO are heavily polluted by ECC-funnel-pattern findings (missing version metadata, missing observation hooks). MEDIUM and below would generate too many alerts to be useful. |
| Dedupe via `seen_findings` table | First scan after install fires a baseline burst of toasts for pre-existing HIGH+ findings (mostly false positives in official plugins). After that, only genuinely-new findings break through. |
| All configured profiles watched | you runs two subscriptions on the same machine. A malicious skill landing in either profile is a risk regardless of which Claude Code instance loads it. |

## What this skill does NOT cover

- The runtime `agentshield runtime install` PreToolUse hook (we explicitly didn't install it; consider only if reactive detection proves insufficient)
- Scanning anything outside your configured profile directories (e.g., npm-installed packages, pip-installed Python packages)
- Active blocking — this system observes and reports, it does not prevent anything from happening

If those become needed, the next iteration adds: (a) `agentshield runtime install` for PreToolUse blocking on the most sensitive tool patterns, (b) a `pip list` / `npm list -g` snapshot diff to catch dependency-installed surprises.
