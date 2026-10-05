# Why the HTML landed and the markdown didn't

Three documents, written within 24 hours of each other, in the same repo's `docs/` folder,
all covering the same subject: how per-customer payment credit is stored and what a unique
constraint does to it.

| Document | Format | Reception |
|---|---|---|
| attribution research doc | 19 KB markdown — research + options | did not land |
| analytics impact doc | 10 KB markdown — impact assessment | did not land |
| data-flow explainer | 15 KB single-file HTML | landed — the reader called it the clearest explanation they had been given |

This matters because **the markdown docs were not bad markdown.** They had tables. They had
`VERIFIED` / `INFERRED` labels. They had 🔴 severity glyphs. They had verdict-in-one-line
sections at the top. They followed a deliberate communication contract. They still didn't
land. So the delta is not "add structure to prose" — it is something more specific.

---

## The five differences that actually carry the effect

### 1. The abstract key became a physical object

The markdown wrote the constraint as text:

```
uc_invoice_lines UNIQUE (account_id, price_id, customer_id)
```

…and then *explained in a sentence* why two payments collide. That sentence asks the reader
to hold three column values in working memory, imagine a second write, and compare tuples —
all without seeing anything.

The HTML made it three labelled boxes: **fixed + free-to-vary + fixed.** Once the boxes carry
"always 900" / "the only thing free to change" / "always Alex — that's the point", the
collision is not an argument any more. It's arithmetic you can look at.

**Generalises to:** any composite/natural/partition/dedup/idempotency key. Draw the key.

### 2. The consequence was rendered, not asserted

Markdown: *"two payments crediting the same customer would be the same triple — a
duplicate-key error on the second payment."* That is a claim the reader must trust.

HTML: two actual table rows with visibly identical key values, the second one tinted red, with
`✕ duplicate key` in the row. Nothing to trust. The claim and its evidence are the same object.

**Generalises to:** never assert what a write will do. Show the rows.

### 3. Emphasis was located inside the data, not around it

Both markdown docs used tables, and in both, **every cell had equal visual weight.** The
reader has to find the important row by reading all of them.

The HTML tints exactly one row per grid, and outlines the one column the rule keys on. This
was the element the reader singled out as most useful: *here is all the data, and here is
the part to focus on.*

That is a two-part statement, and both parts are required. Not a summary instead of the data
— **the full data, plus a pointer.** Trimming the table to only the interesting row would
destroy the effect, because the highlight only means something against the unhighlighted rows.

**Generalises to:** show everything, emphasise one thing. One highlight per grid.

### 4. The comparison became spatial

The markdown described Option B, then Option C, in sequence — so comparing them means
scrolling and remembering. The HTML put them in two columns with **identical internal
geometry**, so the difference is the only thing that moves. The eye diffs rather than reads.

Note the corollary: identical geometry is the load-bearing part. Two cards with different
sub-headings, different orders, or different components are just two documents next to each
other.

**Generalises to:** 2-3 options, before/after, today-vs-proposed — same skeleton, side by side.

### 5. One idea per card, with a numbered spine

The markdown ran continuous prose under `##` headings, with sub-sections nested three deep
(`### 3.1`, `### 4.4`). The HTML is six cards, each holding one idea, each opening with a
coloured numeral.

Skimming only the badges gives the shape of the whole argument before reading a word:
violet (context) → green (this part is fine) → red (here's the break) → green (here's the fix)
→ neutral (the alternative) → neutral (the check). That is "flow sequencing".

**Generalises to:** 3-6 steps, one idea each, badge colour = that step's verdict.

---

## What did NOT cause the difference

Worth stating, so effort goes to the right place:

- **It was not more information.** The HTML has *less* content than either markdown file. It
  drops the pre-existing defects, the metric-by-metric safety table, and most of the
  `file:line` citations. It is a narrower page that answers one question.
- **It was not colour on its own.** Both markdown docs used 🔴. Colour worked here because it
  was *assigned* — one meaning per colour, verdict colours never reused as entity colours
  (see `design-system.md` §1) — and because it was *located* on the specific row and column
  that mattered.
- **It was not the medium.** An HTML file of the same prose would have failed identically.
  The format change was permission to use position, tint, and adjacency as carriers — the
  medium only mattered because markdown can't do those.
- **It was not diagram-ness.** There is no flowchart, no Mermaid, no SVG, no chart anywhere in
  the artifact. It is tables and boxes. Reach for a chart only when the point is a trend.

---

## The one-line rule

**Put the emphasis inside the data, keep one idea per card, and render consequences as rows
instead of claiming them in sentences.**

Everything in `patterns.md` is a mechanism for doing that.
