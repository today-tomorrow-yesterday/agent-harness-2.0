# The eight component patterns

Each has a **name**, a **use when**, and a **minimal snippet**. All eight are already
assembled with placeholder content in `../template.html` — this file is the reference card;
the template is the starter. Class names match both.

Order below is the order they usually appear on a page.

---

## 1. Page Head + Legend

**Use when:** always. Every page opens with these two blocks.

The `<h1>` states the ONE thing the page makes legible. If you can't write it in one line,
you aren't ready to draw the page. The `.sub` line carries the qualifiers (option name, "no
schema change", the scenario) separated by `·`.

The legend is **required**, not optional — one row per colour token you use, with a one-line
description, plus the 🗄/🌐/⚙ marker key. Without it the reader must infer your colour
scheme, which defeats the point of a semantic palette.

```html
<h1>Crediting customers per payment, on the fly</h1>
<p class="sub">Option C — no schema change · real customers · what happens when
   two payers each pay $50 toward the same customer</p>

<div class="legend">
  <div class="lg"><span class="tok e3">customer</span> a real account holder</div>
  <div class="lg"><span class="tok e2">payer</span> whoever sent the money</div>
  <div class="lg"><span class="tok good">✓ works</span> legal / correct outcome</div>
  <div class="lg"><span class="tok bad">✕ breaks</span> rejected / data lost</div>
  <div class="lg"><span class="tok warn">key</span> the column the rule keys on</div>
  <div class="lg"><span class="mk">🗄</span> table &nbsp;<span class="mk">🌐</span> endpoint
      &nbsp;<span class="mk">⚙</span> stored proc</div>
</div>
```

---

## 2. Step Card

**Use when:** the page has a sequence — a walkthrough, a flow, an argument that builds. 3-6
cards, **one idea each**. Past six, the numbered spine stops being a spine; split the page.

The badge colour is the step's *verdict*, which lets a reader skim only the coloured badges
and get the shape of the argument: neutral → violet (context) → green (this part is right) →
red (here's the problem) → green (here's the fix). That is "flow sequencing".

`.note` hangs at `margin-left:54px` so it aligns under the **title text**, keeping the badge
column clean.

```html
<div class="step">
  <div class="stephead">
    <span class="stepnum bad">3</span>
    <span class="steptitle">Two payers, both $50, both toward Alex</span>
  </div>
  <p class="note">Here is the rule the database enforces. Only three columns matter.</p>

  <!-- grids, strips, callouts go here -->
</div>
```

Badge variants: `.stepnum` (neutral blue) · `.stepnum.good` · `.stepnum.bad` · `.stepnum.e1`
… `.stepnum.e3`. Each sets a dark ink colour so the numeral stays legible on the fill.

---

## 3. Evidence Grid ⭐ the most effective pattern

**Use when:** you are making any claim about data. Do not *assert* that a write would
collide, duplicate, or be rejected — **render the rows and tint the one that matters.**

> Show all of the data, then point at the one part to focus on. Both halves are required.

Rules that are not optional:

- **ONE highlighted row per grid.** Two highlights is zero highlights.
- Tint goes on `td`, never `tr` (the zebra stripe paints over a `tr` background).
- `.keycol` on the `<th>` **and** every `<td>` in that column → a vertical amber ribbon
  marking the column the rule keys on. Row = the instance; column = the rule.
- The highlighted row **must carry a word or ✓/✕ in-row**, not only in prose below it.
  Colour is never the only carrier.
- `<caption>` = the table name in bold + a `.cnt` clause in dim text saying what the reader
  is looking at. Prefix table names with 🗄.

```html
<table>
  <caption>🗄 invoice_lines <span class="cnt">— if both payments share one $50 price row</span></caption>
  <tr>
    <th>account</th><th class="keycol">price</th><th>customer</th>
    <th>payer</th><th>payment</th><th>verdict</th>
  </tr>
  <tr>
    <td>900</td><td class="keycol">700</td><td class="e3">c-207 Alex</td>
    <td class="e2">p-900 Sam</td><td>P-1</td><td class="tick">✓ written</td>
  </tr>
  <tr class="badrow">
    <td>900</td><td class="keycol">700</td><td class="e3">c-207 Alex</td>
    <td class="e2">p-901 Dana</td><td>P-2</td><td class="cross">✕ duplicate key</td>
  </tr>
</table>
```

Row variants: `.newrow` (green tint — this row IS the point) · `.badrow` (red tint — this row
breaks). Nothing else. If you find yourself wanting a third, you want a second grid.

---

## 4. Key Composition Strip

**Use when:** an abstract multi-column rule needs to become a concrete object — a composite
unique key, a natural key, a partition key, a cache key, a dedup tuple, an idempotency key.

This is the pattern that made an invisible constraint legible. Each part of the key becomes a
box, and each box is **labelled fixed vs free-to-vary**, which turns "why does this collide?"
into something you can see: if every box is fixed, two writes are the same write.

```html
<div class="keybox">
  <div class="kb fixed">account_id<small>always 900</small></div>
  <div class="plus">+</div>
  <div class="kb vary">price_id<small>the only thing free to change</small></div>
  <div class="plus">+</div>
  <div class="kb fixed">customer_id<small>always Alex — that's the point</small></div>
</div>
```

Box variants:

| Class | Border / text | Means |
|---|---|---|
| `.kb.fixed` | dim grey | pinned by the scenario — cannot absorb a difference |
| `.kb.vary` | `--good` | free to change — this is what makes two writes distinct |
| `.kb.newk` | `--e2` | **added** by the proposed option (a new column in the rule) |
| `.kb.gone` | `--e6` + strikethrough | removed / retired |

Reuse the same strip in both Option Cards with different fixed/vary assignments — that single
move shows the two designs differ only in *what absorbs the difference*, which is usually the
real answer.

---

## 5. Flow Strip

**Use when:** tracing a short sequence inline — a request path, an ETL hop, a state
transition, a call chain. Same box geometry as the Key Composition Strip with `→` separators
instead of `+`, so the two read as the same family.

Mark every node with 🗄 / 🌐 / ⚙ so the reader never has to work out what kind of thing it is.
Cap at ~5 nodes; a longer chain wants Step Cards.

```html
<div class="keybox flow">
  <div class="kb newk">🌐 POST /v2/payments/submit<small>route</small></div>
  <div class="arrow">→</div>
  <div class="kb fixed">SubmitPaymentService<small>service</small></div>
  <div class="arrow">→</div>
  <div class="kb vary">⚙ complete_line_payment<small>atomic</small></div>
  <div class="arrow">→</div>
  <div class="kb fixed">🗄 invoice_lines<small>row written</small></div>
</div>
```

---

## 6. Option Cards (A/B) — also does before/after

**Use when:** 2-3 designs, or a broken-vs-fixed / today-vs-proposed pair. Spatial adjacency
is the whole point: the eye compares two things placed side by side far faster than two
things described in sequence. Collapses to one column under 960px.

Keep the **geometry identical** between cards — same sub-headings, same order, same components
in the same slots — so the eye diffs them instead of reading them. Different structure on the
two sides destroys the comparison.

Lead each `<h3>` with ✓ or ✕. **If both options are viable, both get ✓** — do not rank with
colour. Ranking is ⭐.

```html
<div class="two">
  <div class="card">
    <h3><span class="tick">✓</span> C — price row per payment <span class="muted">(no DDL)</span></h3>
    <div class="keybox tight">
      <div class="kb fixed">account</div><div class="plus">+</div>
      <div class="kb vary">price<small>700 → 701</small></div><div class="plus">+</div>
      <div class="kb fixed">customer</div>
    </div>
    <p class="tail">2 payments → <b>2 new 🗄 prices rows</b> + 2 🗄 invoice_lines rows.</p>
  </div>
  <div class="card">
    <h3><span class="tick">✓</span> B — widen the rule <span class="muted">(one ALTER)</span></h3>
    <div class="keybox tight">
      <div class="kb fixed">account</div><div class="plus">+</div>
      <div class="kb fixed">price<small>700 both times</small></div><div class="plus">+</div>
      <div class="kb fixed">customer</div><div class="plus">+</div>
      <div class="kb newk">payment<small>P-1 vs P-2</small></div>
    </div>
    <p class="tail">2 payments → <b>1 shared price row</b> + 2 rows. Nothing else grows.</p>
  </div>
</div>
```

**Before/after variant:** identical markup, `<h3>` badges become `<span class="cross">✕</span>
Today` and `<span class="tick">✓</span> Proposed`.

---

## 7. Severity Callout

**Use when:** one sentence needs to survive skimming — a verdict, a cost, a trap, a
correction. The 5px left accent bar is findable while scrolling; the bold first line is the
whole message and the body is optional depth (outcome first, depth optional — in a box).

Maps 1:1 onto the 🔴🟠🟡🟢 severity palette.

```html
<div class="callout good">
  <b>✓ Different price_id → different key → both legal</b>
  Alex is credited $100 from 2 payers. Sam and Dana are each traceable to their own payment.
  No placeholder accounts. No <code>ALTER TABLE</code>.
</div>

<div class="callout bad">
  <b>✕ Bumping 🗄 prices.quantity can't carry the second payment</b>
  <code>quantity</code> is a counter, not the payment — the payment needs its own row, because that
  row is the only place <code>payer_id</code> lives. One row can't hold two payers.
</div>

<div class="callout">              <!-- default = warn: the honest cost -->
  <b>The honest cost</b>
  🗄 prices now grows by one row per payment, and a row there stops meaning
  "a thing for sale". It works. It isn't tidy.
</div>
```

Variants: `.callout` (amber — caution / honest cost / the pivot) · `.callout.good` ·
`.callout.bad` · `.callout.e1`…`.e3` (entity-scoped note, e.g. "both options agree here").

**Always ship one "honest cost" callout on any recommendation.** Part of why the source
artifact was trusted is that it named what the option costs instead of closing on a win.

---

## 8. Verdict Table

**Use when:** closing out an impact assessment, a regression check, a "does this break
anything" question, or an acceptance list — checkmarks for what's right, crosses for what's wrong.

Question → Answer → a dedicated ✓/✕ column. The verdict lives in **its own column**, so the
reader can scan one narrow strip and be done — that's the accessibility win over putting ✓
inline in prose. Add a dim clause after the glyph when a ✓ needs a reason.

```html
<table>
  <caption>25-customer account <span class="cnt">— Sam and Dana each pay $50 toward Alex</span></caption>
  <tr><th>Question</th><th>Answer</th><th>Right?</th></tr>
  <tr><td>Total collected</td><td>$100</td><td class="tick">✓</td></tr>
  <tr><td>Number of payers</td><td>2 <span class="muted">(Sam, Dana)</span></td><td class="tick">✓</td></tr>
  <tr><td>Alex credited</td><td class="e3">$100 from 2 payers</td><td class="tick">✓</td></tr>
  <tr><td>Payments counted</td><td>2</td>
      <td class="tick">✓ <span class="muted">— nothing was pre-seeded</span></td></tr>
  <tr class="badrow"><td>Placeholder accounts created</td><td>0</td>
      <td class="cross">✕ <span class="muted">was 8 before</span></td></tr>
</table>
```

A Verdict Table may use `.badrow` on the rows that fail — that is still **one highlight per
grid** if only one row fails. If several fail, drop the tint and let the ✕ column carry it.

---

## Supporting bits

| Class | Use |
|---|---|
| `.muted` | inline dim aside inside a mono cell (`c-207 <span class="muted">customer</span>`) |
| `.tick` / `.cross` | ✓ / ✕ at weight 800 in verdict colours |
| `.tok` | legend chip, and inline emphasis token for a load-bearing domain noun |
| `.mk` | the 🗄/🌐/⚙ marker glyph, sized up slightly so it survives at data sizes |
| `code` | inline identifier — mono, in a `--well` chip |
| `pre` | multi-line SQL / arithmetic / the whole DDL change. Do arithmetic **as a `pre` block**, not prose: `31 prices × 30 customers = 930 rows` |
| `.tail` | last paragraph in a card, `margin:0` (kills the trailing gap) |
| `.closing` | the final `.sub`-styled line of the page, after the last step |
