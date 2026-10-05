# Safety hooks

Claude Code runs **hooks** -- small scripts -- at fixed points in a session: before a tool call
(`PreToolUse`), when you submit a prompt (`UserPromptSubmit`), and when a turn ends (`Stop`). The
hooks in `bin/hooks/` turn standing rules ("never force-push", "do not publish from an unattended
run") into checks that run at the moment of action, instead of prose an agent can walk past.

Nothing is active until you register it. Pick the hooks you want.

| Hook | Kind | Events | One line |
|---|---|---|---|
| `pre-tool-guard` | blocks | PreToolUse `Bash\|PowerShell` | refuses destructive / irreversible shell commands |
| `safety-queue` | pauses (unattended only) | PreToolUse `Bash\|PowerShell` | queues outward-facing actions for a human to review |
| `placement-guard` | blocks | PreToolUse `Write\|Edit\|MultiEdit\|NotebookEdit\|Bash\|PowerShell` | refuses new top-level folders in protected roots |
| `design-gate` | blocks | PreToolUse `Skill\|Write\|Edit\|MultiEdit`, Stop | frontend edits must go through your design skills |
| `skill-shape-guard` | blocks | PreToolUse `Write\|Edit\|MultiEdit\|NotebookEdit` | refuses a "skill" that could never be invoked |
| `capability-gate` | advises | PreToolUse, UserPromptSubmit | one-time hints: the keyring wrapper, memory index, matching skills |

## Turning hooks on and off

```
python bin/register_hook.py --list                       # what exists, what is registered
python bin/register_hook.py pre-tool-guard safety-queue  # register some
python bin/register_hook.py --all                        # register every hook
python bin/register_hook.py safety-queue --remove        # unregister one
python bin/register_hook.py pre-tool-guard --verify      # check, change nothing
```

The registrar writes to `~/.claude/settings.json` (override with `CLAUDE_CONFIG_DIR` or
`CLAUDE_SETTINGS_PATH`). It works the same on Windows, macOS and Linux: it uses the Python you run
it with and a forward-slash path to the script, so the entry works from Git Bash, WSL, PowerShell,
cmd, zsh and bash. It is idempotent, validates the new file before replacing the old one, keeps
every unrelated setting, and never adds a byte-order mark. Hook config is read at session start, so
**restart Claude Code** after registering or removing.

Temporary off switches (set in the environment Claude Code is started from, or in the `env`
block of `settings.json`):

| Variable | Effect |
|---|---|
| `HARNESS_HOOKS_DISABLED=1` | every hook in `bin/hooks/` does nothing |
| `DESIGN_GATE=off` | only `design-gate` does nothing |
| `CAPABILITY_GATE=off` | only `capability-gate` does nothing |
| `HARNESS_SAFETY_NOTIFY=off` | `safety-queue` still pauses, but sends no Slack message |

Every hook shares one contract: a block is exit code 2 with the reason on stderr (Claude Code
shows it to the model); anything else is exit 0. **A hook never breaks your session**: malformed
input, a missing file or an internal bug all end in "allow". `bin/tests/test_hooks_bin_stdin.py`
holds every hook to that.

---

## pre-tool-guard

Blocks shell commands that are destructive or irreversible:

- git history rewrites and force operations: `push --force` / `-f` / `+refspec`, `rebase`,
  `filter-branch` / `filter-repo`, `commit --amend`, `reset --hard`, deleting a remote branch
- recursive force-delete of a filesystem root, or of an absolute path **outside the current
  working directory** (bash `rm -rf` and PowerShell `Remove-Item -Recurse -Force`, including the
  `rm` / `ri` / `del` / `erase` aliases and abbreviated flags)
- `mkfs`, `dd of=/dev/...`
- piping a download into a shell (`curl ... | sh`, `iwr ... | iex`)
- `DROP TABLE` / `DROP DATABASE` / `DROP SCHEMA` / `TRUNCATE TABLE`
- recursive `chmod` / `chown` on a root
- `git commit` when the **staged** diff adds something shaped like a secret (private key, AWS
  key id, `sk-` API key, GitHub token). The value is never printed.
- in unattended runs (`HARNESS_UNATTENDED=1`): every `git commit` and `git push`

Allowed on purpose: plain `git commit` / `git add` in an interactive session (commit policy is a
per-project choice), `--force-with-lease`, deletes inside the working directory. Quoted text is
ignored, so `grep "DROP TABLE" schema.sql` or a commit message mentioning `rm -rf` passes.

When it blocks something you really want: run the command yourself, or tell the agent explicitly
in chat that this exact command is approved. The guard protects against accidents, not
adversaries.

## safety-queue  (+ the `/safety-review` skill)

**Does nothing unless `HARNESS_UNATTENDED=1`.** Set that variable in the environment of any
headless or scheduled `claude -p` run. In such a run, these commands are paused instead of run:

- sending email or messages (`sendmail`, `Send-MailMessage`, `mail -s`, `aws ses send-email`,
  `aws sns publish`, `aws sqs send-message`, ...)
- an HTTP write (`-X POST/PUT/PATCH/DELETE`, `-Method Post`, or a request body such as `-d`,
  `--data`, `-Body`) to any host that is not localhost
- publishing: `npm` / `pnpm` / `yarn publish`, `twine upload`, `cargo publish`, `gem push`,
  `docker push`
- public GitHub actions: `gh release create`, `gh pr create`, `gh issue create`, `gh gist create`
- production deploys: `vercel --prod`, `netlify deploy --prod`, `wrangler deploy`

A paused command is written to `forge/safety/queue.json` (with an event in
`forge/safety/history.json`), the attempt is refused, and the model is told to move on. If
`bin/notify_slack.py` has a webhook configured, a short Slack message is sent (the command text is
not included). Work the queue in an interactive session with `/safety-review` -- list, approve,
deny or clear. Approving does **not** run the command; you run it yourself. Plain downloads,
GETs, localhost traffic and ordinary file work are never paused. `HARNESS_SAFETY_DIR` moves the
queue elsewhere.

## placement-guard

Refuses a tool call that would create a **new top-level directory** inside a protected root. The
`Write` tool creates parent folders silently, so the guard reads the exact path from
`Write` / `Edit` / `MultiEdit` / `NotebookEdit`, and also watches `mkdir` / `md` / `New-Item` in
the shell.

Protected by default: this repository, with the allowlist `REPO_ALLOWED` in
`bin/placement_policy.py` (`bin`, `docs`, `memory`, `skills`, `forge`, `logs`, ...). Always fine:
nested folders under an existing top-level folder, folders that already exist, and plain files.

To protect other places, write a JSON policy and point `HARNESS_PLACEMENT_POLICY` at it:

```json
{
  "include_repo": true,
  "roots": {
    "~/work": ["clients", "tools", "_scratch"]
  }
}
```

To allow a new top-level name, add it to the allowlist with a reason. The barrier is meant to
cost a decision, not to be impossible.

## design-gate

For projects with a frontend. Names no skills of its own -- you tell it yours:

```
python bin/register_hook.py design-gate \
    --hook-arg=--build-skills=frontend-design,my-ui-skill \
    --hook-arg=--review-skills=my-design-review
```

- A frontend file (`.tsx .jsx .vue .svelte .css .html` by default) may not be edited until at
  least one **build** skill has been invoked in the session.
- If **review** skills are set, the turn may not end while a frontend file was edited after the
  last run of every review skill. This Stop block fires at most twice per edit, so it can never
  trap a session.
- Never gated: tests and specs, `node_modules/`, `docs/`, `__tests__/`.

The environment overrides the registered arguments: `DESIGN_GATE_BUILD_SKILLS`,
`DESIGN_GATE_REVIEW_SKILLS`, `DESIGN_GATE_EXTENSIONS` (comma-separated). With no build skills
configured the gate does not block, and says so once per session in the model's context.
Re-running the registrar with new `--hook-arg` values updates the entry in place.

## skill-shape-guard

Refuses to write a "skill" that could never be loaded: a loose `.md` in a skills root, a
`SKILL.md` without valid BOM-free frontmatter, or a file outside any skills root that announces
itself as a skill. Policy: `bin/skill_policy.py`. See `skills/skill-authoring/`.

## capability-gate

Advisory only -- it never blocks. Each hint appears at most once per session.

- Reading `bin/secrets/keyring.env`: points at `bin/api.py`, which injects keys and redacts them.
- Writing under `memory/`: reminds to keep `memory/MEMORY.md` in step.
- Writing under `skills/`: reminds to regenerate the skill-discovery map.
- Creating a new `bin/*.py`: reminds that scheduled jobs belong in `bin/scheduler/jobs.py`.
- On a prompt that matches a skill's declared triggers: names that skill (at most three hints).
  Skills switched `"off"` in `settings.json` `skillOverrides` are never suggested.

The skill hints come from `bin/hooks/capability_map_generated.py`, built from this repo's
`skills/` by:

```
python bin/capability-map-gen.py --write    # after adding, renaming or re-describing a skill
python bin/capability-map-gen.py --check    # is the committed map current?
```

Triggers come only from a skill's name and an explicit `Triggers on:` / `Use when:` clause in its
description -- so the way to make a skill discoverable is to write that clause.

## State and files

| Path | Written by | Notes |
|---|---|---|
| `forge/safety/queue.json`, `history.json` | safety-queue, /safety-review | should be gitignored |
| `logs/hook-state/design-gate/` | design-gate | one small JSON per session |
| `logs/hook-state/capability-gate/seen.json` | capability-gate | bounded |

`HARNESS_HOOK_STATE_DIR` moves `logs/hook-state/` elsewhere.
