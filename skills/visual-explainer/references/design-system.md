# The visual-explainer design system

Extracted from a single-file HTML explainer (the artifact that
landed — see `delta.md`), with two defects corrected — see **Corrections** at the bottom. Every value here is
the real value from the working artifact unless marked *(new)*.

The whole system is ~120 lines of CSS in one `<style>` block. That is deliberate: no build
step, no CDN, no fonts to download, no `<script>`. It must render from `file://` with the
network off, in five years.

---

## 1. Colour — meaning first, hex second

Three disjoint colour sets. **The sets never borrow from each other.** That separation is
the single most important rule in the system, and it is the direct visual translation of the
usual chat-emoji palette separation (severity 🔴🟠🟡🟢 vs ranking ⭐ vs status ✅❌⏳ mean
different things and must not be mixed).

### 1a. Ground — structure and depth

| Token | Hex | Meaning / where |
|---|---|---|
| `--bg` | `#0e1116` | the page floor. Everything sits on this. |
| `--panel` | `#161b22` | **depth 1** — a numbered step card. One step = one panel. |
| `--panel2` | `#1c2330` | **depth 2** — a card nested inside a step, and every `<th>`. |
| `--well` | `#0b0f14` | **depth 0, inward** — `code`, `pre`, and key boxes. *Darker* than the page, so raw data reads as recessed into the surface rather than floating on it. |
| `--line` | `#2d3748` | every border, every table rule. One border colour, no exceptions. |
| `--ink` | `#e6edf3` | prose. ~15:1 on `--bg`. |
| `--dim` | `#9aa7b4` | annotation, table headers, `<small>` labels, "this is context not substance". ~7.5:1 — still AA, never a whisper. |

The depth ladder is the page's whole spatial logic: **floor → card → nested card**, with data
wells cut *below* the floor. A reader can tell nesting depth from the background alone,
before reading a word.

### 1b. Verdict — RESERVED. Never used for anything else.

| Token | Hex | Means, and only this | Glyph twin |
|---|---|---|---|
| `--good` | `#3fb950` | correct · works · accepted · both-legal | ✅ / ✓ |
| `--bad` | `#f85149` | wrong · breaks · rejected · data lost | ❌ / ✕ |
| `--warn` | `#d29922` | **the load-bearing thing** — the key column, the caution, the honest cost | 🟡 |

`--warn` is the subtlest and most useful of the three. In the source artifact it outlines the
one column the database rule keys on (`.keycol`) and it backs the "The honest cost" callout.
It means *"this is the pivot — look here"*, not "danger".

**Why reserved:** if green can also mean "category X", then a green row no longer means
"this is right", and the reader has to consult the legend on every single cell. The value of
a semantic palette is that it can be read without lookup.

### 1c. Entity identity — one colour per actor/category

Green and red are **deliberately absent** from this set.

| Token | Hex | Suggested role |
|---|---|---|
| `--e1` | `#a371f7` | violet — first entity (a product type, a table, a service) |
| `--e2` | `#58a6ff` | blue — second entity (in the example: the payer) |
| `--e3` | `#f0883e` | orange — third entity (in the example: the customer) |
| `--e4` | `#2dd4bf` | teal — fourth entity *(new — replaces the green that collided with `--good`)* |
| `--e5` | `#f778ba` | pink — fifth, if you truly need it *(new)* |
| `--e6` | `#c9d1d9` | neutral slate — legacy / retired / "exists but not live". Pair with strikethrough. |

Rules:

- **One colour per CATEGORY, not per item.** Every account type is the same violet; every
  table name is the same slate. The colour teaches the category.
- **Cap at 4 entities + neutral.** More than ~6 token types and the code stops being
  learnable. If you need 8, your page is really two pages.
- **Put the identifier inside the token** when the thing has one (`c-207 Alex`, `Plan 5`)
  — it saves a lookup.
- **Assign colours once, at the top, in the legend.** Then be religiously consistent: if
  Alex is `--e3` in step 2, Alex is `--e3` in step 6.
- **Retired/dead things** get `--e6` + strikethrough rather than deletion — the reader needs
  to see they exist but aren't live.

### 1d. Tints — the highlight layer

| Token | Value | Use |
|---|---|---|
| `--tint-good` | `rgba(63,185,80,.11)` | the row that IS the point (new/correct rows) |
| `--tint-bad` | `rgba(248,81,73,.15)` | the row that breaks (rejected/lost rows) |
| `--tint-warn` | `rgba(210,153,34,.09)` | callout background |

Note the asymmetry: **11% for good, 15% for bad.** Red at 11% is too quiet to read as
alarming; green at 15% starts to overwhelm the mono text on top of it. These are tuned
values, not a mistake — keep them.

### 1e. Contrast (verified against `--bg` #0e1116)

| Foreground | Ratio | WCAG |
|---|---|---|
| `--ink` #e6edf3 | ~15.0:1 | AAA |
| `--dim` #9aa7b4 | ~7.5:1 | AAA (normal text) |
| `--e4` #2dd4bf | ~9.8:1 | AAA |
| `--e3` #f0883e | ~8.0:1 | AAA |
| `--warn` #d29922 | ~7.0:1 | AAA |
| `--good` #3fb950 | ~7.3:1 | AAA |
| `--e2` #58a6ff | ~7.3:1 | AAA |
| `--e5` #f778ba | ~7.5:1 | AAA |
| `--e1` #a371f7 | ~5.7:1 | AA |
| `--bad` #f85149 | ~5.4:1 | AA |

Every pair clears 4.5:1, and the two lowest are only ever used at weight 700 / ≥16px. This
is why a dark page is acceptable even to readers who dislike dark mode: the usual complaint
is not "dark", it is that the text isn't bright enough against the background.

### 1f. Light theme

Dark is the default because that is what landed. The light palette lives behind
`html[data-theme="light"]` — one attribute on `<html>`, no JS, no media query (a media query
would silently flip the file on a light-mode OS and break the thing that worked).

| Token | Light value |
|---|---|
| `--bg` / `--panel` / `--panel2` / `--well` | `#faf9f6` / `#ffffff` / `#f2f4f7` / `#f7f8fa` |
| `--line` / `--ink` / `--dim` | `#d5dae1` / `#14171a` / `#5b6672` |
| `--good` / `--bad` / `--warn` | `#1a7f37` / `#cf222e` / `#9a6700` |
| `--e1`…`--e6` | `#6639ba` `#0550ae` `#a04100` `#0f766e` `#a4234d` `#57606a` |
| `--tint-good` / `--tint-bad` / `--tint-warn` | `rgba(26,127,55,.10)` / `rgba(207,34,46,.10)` / `rgba(154,103,0,.10)` |

---

## 2. Type — a scale with named jobs

Two families, and they carry meaning:

```css
--emoji: "Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji";
--sans:  ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif, var(--emoji);
--mono:  ui-monospace, Consolas, monospace, var(--emoji);
```

🔴 **The emoji families are not optional, and this was measured, not assumed.** Without them,
a bare 🗄 (U+1F5C4) falls through to a narrow monochrome system glyph — 55px advance at 64px
type, where the real colour emoji is 88px — and reads as tofu next to 🌐 and ⚙. Verified by
glyph-width probe in Chrome on Windows. Two independent fixes both work; the
font-stack one is preferred because it also covers markers sitting **inside table cells**
(which use `--mono`), and it needs no invisible characters in the source:

| Fix | How | Covers |
|---|---|---|
| **append the emoji families** *(used here)* | the CSS above | any bare glyph, anywhere, sans + mono |
| variation selector U+FE0F | write `🗄️` instead of `🗄` | that one glyph; invisible in source, easy to lose on a copy-paste |

🔴 **Use text-presentation ✓ (U+2713) and ✕ (U+2715), never ✅/❌.** Colour emoji carry their
own colour and **ignore CSS `color`**, so a ✅ cannot be tinted `--good` and cannot inherit
the light-theme palette. The two text glyphs measure 47.9px / 52.3px — monochrome — which is
why `.tick` and `.cross` work at all. The source artifact used these codepoints for exactly
this reason. (In *chat* the palette can still be ✅❌; this is an HTML-only
substitution, same meaning.)

**Monospace = data. Sans = explanation.** Identifiers, ids, row values, SQL, table names,
key boxes → mono. Prose, titles, notes, labels → sans. Never swap them; the font *is* a type
signal, and swapping it costs a reader who scans by shape.

| Token | Size | Job | Weight / detail |
|---|---|---|---|
| `--t-title` | 40px | page `<h1>` | 700, line-height 1.15, `letter-spacing:-.02em` |
| `--t-step` | 26px | step / section title | 700, `letter-spacing:-.01em` |
| `--t-lede` | 20px | subtitle under the h1; closing line | 400, `--dim` |
| `--t-body` | **19px** | **base — all prose** | line-height **1.65** |
| `--t-note` | 18px | step annotation, callout body, table caption | |
| `--t-data` | 17px | table body text | |
| `--t-mono` | 16.5px | `code`, `pre`, key boxes | line-height 1.5 in `pre` |
| `--t-label` | 13.5px | `<th>`, and the `<small>` sub-label inside a key box | 600, UPPERCASE (th only), `letter-spacing:.06em`, `--dim` |

**Nothing goes below 13.5px.** (The source artifact used 13px for the key-box `<small>`;
raised here so there is one floor and no exception to remember.) The 19px base is roughly 20% larger than a typical web body
size and is not negotiable — it is a readability accommodation, not a style choice. Negative tracking
on the two large sizes stops big text from looking loose.

The scale has a deliberate shape: **one big jump** (19 → 26 → 40) for the structural spine,
and a **tight cluster** (16.5 / 17 / 18 / 19) for everything at reading level. Nine steps
sounds like a lot; in practice you touch four.

---

## 3. Spacing rhythm — 4px base

| Token | Value | Where |
|---|---|---|
| `--s1` | 8px | table cell padding (y), tight gaps between boxes |
| `--s2` | 12px | table cell padding (x) |
| `--s3` | 16px | inside small components |
| `--s4` | 20px | grid gap between the two option cards |
| `--s5` | 24px | **between step cards** — the page's main breathing rhythm |
| `--s6` | 28px | step card padding |
| `--s7` | 40px | after the head block, before the first step |

Page frame: `body { padding: 40px 32px 120px }`. **No `max-width`, no `margin:0 auto`.**
Content fills the browser width; side padding only. The oversized bottom gutter (120px)
means the last card is never jammed against the viewport edge on a short scroll.

**The hanging indent** — the one spacing detail worth calling out:

```css
.stepnum { width:40px; margin-right:14px }
.note    { margin-left:54px }   /* 40 + 14 — hangs under the TITLE, not the badge */
```

The step's annotation lines up with the step's *title text*, not with the card edge. The
numbered badges then form an unbroken vertical spine down the left of the page, and nothing
else intrudes on that column. That spine is what carries "flow sequencing".

### Radius ladder — outer bigger than inner

| Token | Value | Component |
|---|---|---|
| `--r-step` | 16px | step card (outermost) |
| `--r-card` | 14px | nested card |
| `--r-callout` | 12px | callout — `border-radius: 0 12px 12px 0` (square on the accent edge) |
| `--r-box` | 11px | key box |
| `--r-chip` | 6px | inline `code` |

Radius shrinks as you nest inward. This is what makes the nesting read as physical rather
than as arbitrary boxes-in-boxes.

Border weights are also a signal: **5px** left border on a callout (an accent bar you can
find while scrolling), **2px** on a key box (a real edge, because the box *is* the content),
**1px** everywhere else, and a **2px inset outline** for the highlighted table column.

---

## 4. The highlight mechanics — the most praised element

The element readers single out most: *here is all the data, and here is the part to focus
on.*

```css
tbody tr:nth-child(even) { background: var(--zebra) }      /* zebra ON THE TR */
tr.newrow td { background: var(--tint-good) }              /* THE row — ON THE TD */
tr.badrow td { background: var(--tint-bad)  }              /* the row that breaks */
.keycol      { outline: 2px solid var(--warn); outline-offset: -2px }
```

Four load-bearing implementation details:

1. **Zebra on the `tr`; highlight on the `td`.** A cell's background paints *above* its row's
   background, so a `td` tint always wins over a `tr` stripe — no specificity fight. Write
   the zebra as `tbody tr:nth-child(even) td` instead and it out-specifies `tr.newrow td`
   → (0,1,3) vs (0,1,2) → **the highlight silently disappears on every even row.** This is
   the bug you will otherwise ship; it was caught by browser verification, not by reading.
2. **`.keycol` goes on the `<th>` and on every `<td>` in that column.** The result is a
   vertical amber ribbon running the height of the table — it marks *the column the rule
   keys on*, which is a different statement from "this row matters". Row = instance,
   column = rule. Being able to say both at once is why the constraint became legible.
3. **`outline`, not `border`.** A border would shift the cell geometry and misalign the
   column; `outline` with `outline-offset:-2px` draws inside the existing box.
4. **One highlight per grid.** Two highlights is zero highlights. If two rows matter, that
   is two grids — or the second row belongs in the next step.

**Accessibility requirement (an improvement on the source):** a tinted row must also carry a
word or symbol *in the row* — a trailing `<td class="cross">✕ rejected — duplicate key</td>`
or `<td class="tick">✓ new</td>`. The source artifact put that verdict in the prose
underneath, which works for a sighted reader with the colour but leaves nothing behind if
the colour is lost. Colour must never be the only carrier.

`<caption>` carries the table's name in bold plus a `.cnt` clause in `--dim` explaining what
the reader is looking at (*"— a row is minted at the moment of each payment"*). Table headers
are UPPERCASE 13.5px tracked `--dim`, so they read as scaffolding rather than as data.

---

## 5. Corrections applied to the source artifact

Two real defects, fixed here rather than inherited:

🔴 **Entity/verdict colour collision.** One entity colour and `--good` were the same hex
`#3fb950`. Green therefore meant both "this category" and "this is correct" in the same
document. It was harmless only by accident — that category happened to appear in a row that
was also correct (`$0` ✓). The palettes are now disjoint by construction.

🔴 **`max-width:1220px` on `.wrap`.** A fixed-width centred column wastes most of a wide
monitor and forces more scrolling — worst of all for a reader running large type or browser
zoom, who is exactly the reader this style is for. The template has no centred shell at all.

One addition:

🟡 **A legend was missing.** Any technical HTML doc with a semantic palette needs a legend at
the top showing each token with a one-line description.
The template ships one; fill it in rather than deleting it.
