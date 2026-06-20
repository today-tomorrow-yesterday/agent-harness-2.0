# Vetting methodology — third-party security-skill libraries

How to decide whether a large cybersecurity-skill library is safe to keep on disk
and use on demand. This is the *method*; it is not a verdict for any specific
library version — re-run it whenever you install or update one.

## The core problem

A keyword scan of a security corpus is **false-positive-saturated**: the subject
matter *is* the danger vocabulary. Credential-security skills read credentials;
malware-analysis skills decode base64; injection-detection skills contain the
payloads they detect. A naive "scan every script for scary strings" will flag a
large fraction of a benign library. So a clean keyword scan is neither achievable
nor meaningful here.

## Trust model: possession ≠ execution

A skill file on disk is inert. Installing a library introduces **no runtime risk**
by itself. Risk appears only at execution. Therefore:

- **Unattended automation runs only code you wrote and personally verified** (here,
  the one read-only `bin/night-monitor.ps1`). It never runs the library's scripts.
- **The library's scripts run only on demand**, via the `security-analyst` subagent,
  human-in-the-loop, with the specific script **read just-in-time before execution**.
- **Offensive/dual-use skills** (C2, exploit, red-team) are retained as inert
  methodology for authorized use on owner-controlled systems only, flagged
  `"offensive": true` in the index and gated behind an out-of-band authorization
  file (see the agent definition).

## A defensible vetting pass

1. **Static scan** for high-signal categories (destructive ops, hidden/coercive
   instructions, unexpected network egress, obfuscation). Expect a high raw hit
   count — most will be domain noise.
2. **Triage the high-signal categories by hand.** The categories where a planted
   attack would actually hide (destructive actions, real prompt-injection /
   coercive instructions, exfiltration) are usually small enough to read fully.
3. **Sample the dismissed bucket.** Do NOT dismiss the remaining hits as "domain
   noise" wholesale — read a documented random sample (e.g. 20–30) so the dismissal
   is evidence-based, not asserted. Record the sample.
4. **Provenance check.** Confirm the executable surface is what it claims (e.g. all
   `agent.py` unique, sharing one read-only shell) rather than copy-pasted unknowns.
5. **Record a verdict** that states what it does and does NOT certify. Clearing a
   library for *presence + gated use* is not certifying every script bug-free.

## Re-verify on update

Updating the library rewrites files (and drops the module's ACL lockdown — re-apply
it). Re-run the static scan + hand-triage on the new version before trusting any
new or changed skill. The integrity hash in `night-monitor.ps1` will flag that the
library changed.
