# Workflow-launch protocol — pre-dispatch checklist for multi-agent fan-outs

Read BEFORE launching any scripted multi-agent fan-out (for example a Claude Code `Workflow`
script, or any runner that dispatches many agents from one script). A swarm that dies mid-run
re-burns the whole usage window on the relaunch — the single biggest hidden cost measured when
this checklist was written. Each point below encodes a failure mode that actually forced a
full-swarm re-run.

## The 6-point gate (all must pass before dispatch)

1. **Args are a JSON value, never a giant inline string.** Harnesses may stringify `args`; a
   ~32 KB inline manifest was rejected by a permission dialog ("control characters that would be
   hidden"), and a stringified array arrived as one string that `.map`/`.filter` threw on.
   **Fix once, use always:** write the manifest to disk (e.g. `forge/<run>/manifest.json`) and
   have the FIRST agent read it through a schema'd reader ("Read <path>, return the manifest
   array"). Inline args only for small scalars.
2. **Script is LF-only.** A CRLF byte in the script body can trigger the same "control
   characters" permission rejection. If you patch a `.js` workflow from Python or a shell on
   Windows, normalize `\r\n → \n` before re-invoking. (A patch script introduced exactly this CRLF
   and failed a relaunch.)
3. **Every referenced path exists.** Fixtures, ground-truth files, staged run dirs — `test -e`
   them before dispatch. A worker that can't find its input fails and the parcel re-runs.
4. **Post-processing guards undefined.** A failed agent returns `null`; `.filter(Boolean)` before
   `.flat`/`.map`, and guard field access (`(r.evidence || '')`). One unguarded
   `r.evidence.slice()` crashed the reducer of a completed 33-agent run — the agents' work was
   fine, the crash forced a rerun.
5. **Effort per stage set explicitly:** gather/mechanical stages `low`, default `high`,
   judge/synthesis `xhigh`/`max` only where correctness outweighs cost. Unset effort defaults high
   everywhere = output-token burn on stages that don't need it.
6. **Shared prefix byte-identical across parcels; one model tier per chain:** no per-parcel id or
   timestamp inside the shared brief; never switch model mid-chain (it rebuilds the prompt cache).

## On failure — resume, never blind-relaunch

Use the runner's resume mechanism (for a Claude Code `Workflow`, pass the previous run id to
resume from). Completed agents replay from cache instantly; only the failed/new calls re-run. A
blind relaunch re-burns every already-completed agent. Before diagnosing an empty result, read the
run's journal/log — don't assume cached results were non-empty.

## Self-check (one line before every launch)

> args-on-disk? LF-only? paths exist? null-guarded? effort-per-stage? identical-prefix/one-tier?
> — then dispatch.
