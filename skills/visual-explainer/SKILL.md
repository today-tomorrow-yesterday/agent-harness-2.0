---
name: visual-explainer
description: "Build a self-contained, dark-first HTML explainer page (numbered step cards, real data rows with ONE highlighted row, key-composition boxes, side-by-side option cards, verdict tables) instead of a prose doc, whenever someone needs to UNDERSTAND something structural — a schema or constraint, what rows an operation writes, 2-3 design options, a before/after, a request flow, or an impact assessment. Not for 'keep it simple' requests or step-by-step action docs. Triggers on: explain this visually, walk me through, make this visual, make me a diagram, compare these options, show the data flow"
---

# visual-explainer — the HTML explainer that actually lands

One self-contained `.html` file, dark, big type, numbered steps, real data rows with **one**
row highlighted. No build step, no CDN, no fonts, no JS. Opens from `file://`, works offline.

**Provenance (this is empirical, not taste):** the method was distilled from a single-file
HTML explainer of a unique-constraint collision and two ways to resolve it. Two markdown docs
sitting in the same folder covered the **same subject matter**, had tables, had
`VERIFIED` labels, had 🔴 severity glyphs — and did **not** land with their reader. The HTML
page did, and was singled out as the clearest explanation the reader had been given. The
delta between them is what this skill encodes. Read `references/delta.md` for that
comparison; it is the argument for why the extra effort is worth it.

## Why this works — state it, don't bury it

Reading long-form text is taxing for many readers — anyone skimming between tasks, anyone
reading in a second language, anyone with a reading difficulty or low vision, anyone
reviewing on a phone. Walls of prose are the worst possible format for all of them.

Many teams already use **semantic emoji as wayfinding** in chat — 🔴🟠🟡🟢 severity, ⭐
ranking, ✅❌⏳ status — and ban decorative emoji. **This HTML style is the same convention
expressed in CSS.** A coloured step badge is a glyph. A tinted row is a glyph. A ✓ column is
a glyph. Every rule below is the visual translation of "one meaning per marker, and put the
marker where the eye already is."

The mechanism is emphasis-with-context:

| What readers respond to | The pattern it names |
|---|---|
| colours that make sense on sight | palette is **semantic** — one meaning per colour, verdict colours reserved |
| boldness and size that put emphasis on the things that matter | 19px base / 26px step titles / 800-weight badges; nothing under 13.5px |
| the full data shown, with a pointer to the row that matters | **Evidence Grid** — full truth shown, ONE row tinted |
| checkmarks for what's right and what's wrong | **Verdict Table** with a dedicated ✓/✕ column |
| flow sequencing | numbered step badges + **Flow Strip** |
| comparing A to B at a glance | **Option Cards**, side by side, same geometry |

None of this is specific to one codebase. It is a general way of presenting structure.

## When to fire

Fire when the deliverable's job is **comprehension of something structural**:

- a data model, schema, constraint, unique key, FK, or migration
- what rows get written by an operation (the single strongest use — show the actual rows)
- 2-3 design options that need to be weighed side by side
- a before/after, broken-vs-fixed, or today-vs-proposed state
- a request flow, sequence, state machine, or ETL path
- an impact / blast-radius / regression assessment
- anything where you were about to write a long markdown doc with tables in it

**Do NOT fire when:**

| Situation | Use instead |
|---|---|
| The reader asks for **"simple"** | plain sentences, zero structure — no tables, no headers, no bold |
| The doc's job is to make the reader **DO** something | numbered action steps + paste-ready payloads, rationale cut |
| A short answer genuinely fits in chat | answer in chat, outcome first |
| It's a chart / metric series | a charting tool; embed the resulting SVG here only if it belongs in an explainer |
| It's a UI/product surface, not an explainer | your normal frontend design workflow — this is a document style, not an app style |

## The build loop

1. **Name the ONE thing** the page must make legible. Write it as the `<h1>`. If you can't
   state it in one line, you are not ready to draw it — the page will sprawl.
2. **Copy the template**: `template.html` in this skill's directory → destination.
   Never hand-roll the CSS; the palette and scale are load-bearing.
3. **Assign the entity colours first** and write the legend. One colour per *category or
   actor*, not per item. 4 entities max plus neutral — more than that and the code stops
   being learnable.
4. **Lay out the steps.** 3-6 numbered cards, one idea each. Badge colour = the step's
   verdict (neutral / good / bad / entity).
5. **For every claim about data, show the rows.** Don't assert "this would violate the
   constraint" — render both rows and tint the one that breaks. This is the whole trick.
6. **One highlight per grid.** Two highlights is zero highlights.
7. **Close with a Verdict Table** (✓/✕ per question) or a summary callout naming the
   honest cost. Never end on an unqualified win.
8. **Pre-ship pass** — run the anti-pattern list below top to bottom.
9. **Write the file, then open it** in the default browser — `start "" <path>` (Windows),
   `open <path>` (macOS), `xdg-open <path>` (Linux). Do not just report a path; the reader
   asked for something to look at.
10. Reply with **one line in chat**: what it explains + the path. Nothing else.

## Where the file goes

| Subject | Location |
|---|---|
| A specific project/repo (schema, flow, decision in that codebase) | `<repo>/docs/<slug>.html` — durable, beside the other docs, survives the session |
| Cross-project / one-off / throwaway | a scratch directory outside any repo (your OS temp dir, or a gitignored `tmp/`) |

🔴 **Prefer a real file over an in-chat artifact or canvas.** A file survives the session,
can be opened again, diffed, and versioned; an in-chat rendering disappears with the
conversation. Never write it to a home-directory root or a drive root.

## The design system

Full extraction with the reasoning behind every value: **`references/design-system.md`**.
The eight component patterns with use-when + copy-paste snippets: **`references/patterns.md`**.
Working starter with every pattern already in place: **`template.html`**.

The short version:

- **Verdict colours are reserved.** `--good` green / `--bad` red / `--warn` amber mean
  *correct / broken / load-bearing-or-caution* and **nothing else, ever**. They map to
  ✅❌ and to the 🟡 rung of the severity palette.
- **Entity colours are a separate, disjoint set** — violet, blue, orange, teal, pink,
  neutral-slate. Green and red are deliberately absent from it. (The source artifact used
  the same green for one of its categories and for "this is correct"; that collision is
  fixed here.)
- **Colour is never the only carrier.** Every tinted row carries a word or ✓/✕ in-row.
  Every key box carries a `<small>` label. Every callout opens with a bold ✓/✕/label line.
- **Monospace = data. Sans = explanation.** Identifiers, ids, row values, SQL, table names →
  mono. Prose, titles, annotations → sans. Never swap them.
- **Inside the HTML use text ✓ (U+2713) / ✕ (U+2715), not ✅/❌.** Colour emoji ignore CSS
  `color`, so a ✅ can't carry the verdict palette or follow the theme. (In *chat* the
  palette can still be ✅❌ — same meaning, different medium.) Three more measured gotchas
  live in `references/design-system.md` §2 and §4: the emoji font stack, the
  zebra-vs-highlight specificity trap, and the on-tint contrast variants. Read them before
  editing the CSS.
- **19px base, 26px step titles, 40px h1.** Nothing below 13.5px anywhere.
- **No max-width, no centred column.** Side padding only. A centred fixed-width column
  wastes most of a wide monitor and forces extra scrolling — worst of all for a reader who
  runs large type or zoom.
- **Depth ladder:** page `--bg` → step card `--panel` → nested card / table head `--panel2`
  → code & key-box wells `--well`. Radius shrinks as you nest inward (16 → 14 → 12 → 11 → 6).

### Emoji markers inside the page

Mark **every occurrence** so the reader never has to work out what kind of thing they're
looking at — and ship the key in the legend:

| Marker | Means | Natural tell |
|---|---|---|
| 🗄 | data — a database table | has **underscores** (`invoice_lines`) |
| 🌐 | API — an HTTP endpoint | has **slashes** (`POST /v2/payments/submit`) |
| ⚙ | stored procedure / view / job | data-side but executable |
| *(none)* | actors, decisions, services, outcomes | |

These are display glyphs inside a `<meta charset="utf-8">` document. A rule against emoji
in *machine-parsed console output* (where a legacy code page can choke on them) does not
apply here — that is about markers a program reads, not content a browser renders.

## Anti-patterns — these ruin it

🔴 **Decorative colour.** A colour with no assigned meaning is noise that steals from the
colours that do mean something. If you can't write the legend row, delete the colour.

🔴 **More than one highlighted row per grid.** The emphasis dilutes to nothing. If two rows
matter, you have two grids, or the second belongs in the next step.

🔴 **Reusing a verdict colour as an entity colour.** Green must never also mean "category
X". This is the one defect carried in the source artifact.

🔴 **Walls of prose inside the cards.** A card holds a title, one or two sentences, and a
visual. If a card needs three paragraphs, split it into two steps or cut it.

🔴 **A chart where a table is clearer.** Row-level truth beats a bar. Reach for a chart only
when the point is a *trend or distribution*, never for 6 values.

🔴 **Tiny type / low contrast.** Nothing under 13.5px. Every foreground/background pair
stays ≥4.5:1. The usual complaint about dark mode is that the text isn't bright enough
against the background — the contrast is what makes this dark page acceptable.

🔴 **More than ~6 steps.** Past six the numbered spine stops being a spine. Split the page.

🔴 **A `max-width` container.** Full browser width, side padding only.

🔴 **🔴🟠🟡🟢 used as a ranking.** Severity only. Ranking is ⭐.

🔴 **Mono for prose or sans for identifiers.** The font is a type signal; swapping it
breaks scanning.

🔴 **Any external dependency.** No CDN, no web fonts, no framework, no `<script src>`.
System font stacks only (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`
and `ui-monospace, Consolas, monospace`). It must work with the network off.

🔴 **Ending on an unqualified win.** Every option has a cost; the source artifact's *"The
honest cost"* callout is part of why it was trusted. Name it.

## Reconciliations you should know about

**Light mode.** Some readers prefer light mode and some style guides say never to default
documents to dark. In practice the objection is usually to **low-contrast** dark mode, not
dark per se — this palette runs ~15:1 on body text. The template therefore ships **dark by
default with a complete light palette behind `<html data-theme="light">`** — one attribute,
no JS, no rebuild. If the reader prefers light or says the page is hard to look at, flip the
attribute rather than redesigning.

**Max-width.** The source artifact used `max-width:1220px`. The template does not. Do not
reintroduce a centred `.wrap`.

**Legend.** The source artifact had no legend; a page with a semantic palette needs one. The
template ships with a legend block — fill it in, don't delete it.

**Disposable-vs-durable.** One-offs go to a scratch directory. A project explainer that a
future session must find belongs in that repo's `docs/` — the table above is the split.

## Files in this skill

- `template.html` — the starter, every pattern in place with placeholder content
- `references/design-system.md` — tokens, type scale, spacing, highlight mechanics, with reasons
- `references/patterns.md` — the eight component patterns, use-when + snippets
- `references/delta.md` — why the HTML landed and the markdown didn't
