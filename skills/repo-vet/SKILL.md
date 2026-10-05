---
name: repo-vet
description: "Safety-vet an external repo or tool before you RUN it (not just read it) — quarantine clone, authenticity check against the genuine upstream, static security vet, an adversarial multi-lens audit by parallel read-only agents, a fitness check, then a hardened, version-pinned setup recommendation and a SAFE / CONDITIONALLY-SAFE / DO-NOT-USE verdict. Use when someone drops a GitHub URL with \"can we use this\", \"is this safe\", or \"install this\". Triggers on: is this safe, vet this repo, can we use this, install this tool"
---

# repo-vet — clear an external tool for actual use

The recurring shape: someone drops a repo link — "I want this" — and the right response is never
`git clone && npm install && run`. The moment you install, its install scripts execute with your
permissions, next to your credentials. This skill is the pipeline that runs first:
**quarantine → authenticity → static vet → adversarial swarm → fitness → hardened setup → verdict.**

## Scope split (do not blur the lanes)

- **`repo-steal`** — mine an external repo for transferable *patterns* to graft into your own
  code. Read-only consumption; the repo never runs.
- **`repo-vet` (this skill)** — you want to *run* the thing. Higher bar: its code will execute on
  your machine, so the vet is adversarial and the setup is hardened.
- A vet can conclude "don't run it, but these parts are worth stealing" → hand off to `repo-steal`.

## Procedure

1. **Quarantine clone.** Shallow clone (`git clone --depth 1`) into a scratch directory outside
   every working project (e.g. your OS temp dir, or a dedicated `references/` folder for things
   you will keep). Never clone into a project tree; never run ANY part of it — no install scripts,
   no `npm install`, no `pip install`, no `make`, nothing that executes. Opening files in an editor
   is fine; letting an editor run workspace tasks or auto-install extensions recommended by the
   repo is not.
2. **Authenticity check FIRST** — the phishing / lookalike gate. Confirm the cloned HEAD commit
   exists on the genuine upstream (find the canonical org/repo from the project's own website or
   package registry page, then compare stars, fork graph, release history, and maintainers).
   Search for known lookalikes and typosquats of the name and confirm what you cloned is the real
   one. A failed authenticity check ends the vet: verdict MALICIOUS-RISK, delete the clone.
3. **Static security vet** (one pass): manifest and lockfile supply-chain review; install-time
   hooks (`postinstall`/`preinstall`, `setup.py`, build scripts, `prepare`); obfuscated or encoded
   blobs (long base64/hex strings, `eval` of decoded data, minified code in a non-dist path);
   network egress points; credential access patterns (reads of `~/.ssh`, `~/.aws`, browser
   profiles, env-var sweeps); code that runs on import.
4. **Adversarial multi-lens swarm** — parallel read-only agents, one lens each:
   1. backdoor / obfuscation
   2. network egress / command-and-control
   3. supply chain (dependencies + typosquats + unpinned ranges)
   4. passive auto-execution (import-time side effects, hooks, editor/CI config)
   5. credential / secret harvesting
   6. repo authenticity (an independent re-check of step 2)

   Each lens returns `clean` / `suspicious` / `malicious` + evidence (file:line). Any single
   `malicious` = DO-NOT-USE. Two or more `suspicious` = escalate to the user with the evidence; do
   not average suspicion away.
5. **Fitness check** (only if clean). Does it actually fit?
   - **Auth and billing model** — does it require a metered API key when you expected to run it on
     an existing subscription, or route all model calls through a proxy library you do not use?
     (A tool that can only talk to models through a metered-key proxy cannot ride a flat-rate
     subscription — find that out before setup, not after.)
   - **Hardware** — GPU/VRAM, RAM and disk it actually needs vs what you have.
   - **Platform** — does it run on your OS natively, or only under WSL/Docker/Linux?
   - **Overlap** — do you already have a tool that does this? Do not adopt a worse duplicate.
6. **Hardened setup recommendation:**
   - version-pinned install (exact version or commit, lockfile respected);
   - least-privilege runtime — a container, VM, WSL instance or OS sandbox (e.g. bubblewrap,
     sandbox-exec, a sandbox runtime) for anything that executes arbitrary code or drives a
     browser;
   - telemetry off;
   - scope guards — security tools get an explicit allowlist of targets, with `localhost`,
     `host.docker.internal` and LAN ranges excluded unless that is the point;
   - a small wrapper script when the tool needs standing constraints, so nobody has to remember
     the flags;
   - a cost estimate if it is API-metered.
7. **Verdict + record.** SAFE / CONDITIONALLY-SAFE (with the conditions spelled out) / DO-NOT-USE.
   For an adopted tool, record the pinned version, the install location and the wrapper path (in
   the project's docs or your memory notes) so the next session does not re-vet from scratch.

## Hard rules

- **Nothing from the repo executes during the vet.** Reading only. A vet of a tool is never a demo
  of the tool.
- **Authenticity before analysis** — a perfect audit of the wrong repo is worse than no audit.
- **Never vet-and-run in one breath.** Installing and running is a separate, explicit step after
  the user has seen the verdict — unless they already said "if it's clean, install it" for this
  specific tool in this session.
- **Dual-use security tools** are vetted for defensive use on systems you own; the verdict restates
  that authorization boundary (owned targets only).

## Related skills

- `repo-steal` — the mine-patterns sibling (hand-off target for "don't run it, but steal these").
- `research-swarm` — the dispatch mechanics for the step-4 swarm.
- `fable-discipline` — label every finding VERIFIED / INFERRED / ASSUMED; a vet verdict is exactly
  the kind of claim that costs the most if wrong.
