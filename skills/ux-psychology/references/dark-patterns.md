# Dark-pattern taxonomies (source for the ethical-line section)

> Research digest behind `SKILL.md`, produced by one sub-agent of a six-way parallel research pass (each agent had one lane; "Agent A" through "Agent F" below refer to those lanes). Claims carry the agent's own confidence flags; verify a load-bearing one against its cited source before relying on it.


Source focus: Harry Brignull's deceptive.design (formerly darkpatterns.org), plus 2026 regulatory context (FTC, EU DSA/Digital Fairness Act).

## 1. Brignull's current taxonomy (deceptive.design/types)

Brignull retired the old flat 12-item list (Confirmshaming, Disguised Ads, Fake Urgency, Forced Continuity, Friend Spam, Hidden Costs, Misdirection, Price Comparison Prevention, Privacy Zuckering, Roach Motel, Sneak into Basket, Trick Questions) in favor of a broader ~18-category taxonomy used in his 2023 book *Deceptive Patterns* and the current site. Old names still map onto it (e.g. "Roach Motel" ≈ Hard to Cancel; "Privacy Zuckering"/"Sneak into Basket" ≈ Sneaking/Preselection; "Friend Spam" is now folded under Forced Action-type nagging in some taxonomies). Full current list, definitions, and illustrative examples:

1. **Forced Action** — user wants to do X but is required to do undesirable Y first. Example: must watch an ad or share personal data before accessing content they already paid for.
2. **Sneaking** — hides or delays material info to draw the user into a transaction. Example: extra items ("Sneak into Basket") added at checkout, like travel insurance pre-added to a flight booking.
3. **Hard to Cancel (Roach Motel)** — easy to get in, deliberately hard to get out. Example: sign up for a subscription in two clicks online, but cancellation requires a phone call during business hours.
4. **Preselection** — a default option is pre-chosen to steer the decision. Example: a pricier plan or a marketing-consent checkbox pre-ticked at checkout.
5. **Obstruction** — extra friction/hurdles placed specifically to block a task. Example: burying the "delete account" option several menus deep, or hiding it entirely.
6. **Hidden Subscription (Forced Continuity)** — user is enrolled into recurring billing without clear disclosure. Example: a "free trial" that silently converts to a paid annual subscription with no reminder email.
7. **Hidden Costs** — a low advertised price balloons with surprise fees late in the flow. Example: a hotel booking that adds "resort fee," "service fee," and taxes only on the final payment screen.
8. **Trick Wording (Trick Questions)** — confusing phrasing/double negatives make users pick the opposite of what they intend. Example: "Uncheck this box if you don't want to not receive our newsletter."
9. **Visual Interference** — legitimate info exists but is visually buried, low-contrast, or disguised. Example: a tiny, gray "decline" link next to a large, colorful "accept" button.
10. **Fake Social Proof** — fabricated reviews, testimonials, or "X people are viewing this" counters. Example: a product page showing a constantly-incrementing "12 people bought this in the last hour" that's actually static/randomized.
11. **Fake Urgency** — a bogus countdown or deadline pressures fast action. Example: a "Sale ends in 00:09:59" timer that resets on every page refresh.
12. **Nagging** — repeated interruption with a request the user already declined. Example: an app that re-prompts for a review/notification permission on every single launch.
13. **Confirmshaming** — the decline option is worded to guilt or shame the user. Example: a pop-up exit-offer where "No thanks" is rewritten as "No, I don't want to save money."
14. **Fake Scarcity** — false claims of limited stock/availability. Example: "Only 2 left!" labels shown regardless of actual inventory.
15. **Disguised Ads** — ads styled to look like organic content or UI controls. Example: a "Download" button that's actually a paid ad, placed above the real download link on a software site.
16. **Comparison Prevention** — deliberately complex/inconsistent pricing or packaging that blocks apples-to-apples comparison (was "Price Comparison Prevention"). Example: near-identical products bundled with different, non-overlapping feature sets so no two plans are directly comparable.
17. **Addictive Design** — exploiting psychological vulnerabilities (variable reward, infinite scroll, streaks) to drive compulsive use beyond user benefit.
18. **Currency Confusion** — converting real money into in-app/virtual currency to obscure true spend. Example: buying "gems" in bulk so individual in-game purchases feel abstracted from real dollars.

Recommended additions to the skill's "ethical line" section beyond the current 3 (forced continuity, fake urgency, hidden-strings free gifts): Hard to Cancel/Roach Motel, Confirmshaming, Sneaking/Sneak-into-Basket, Hidden Costs, Visual Interference, Disguised Ads, Nagging, Comparison Prevention — these are the ones most directly relevant to product/growth UI decisions (checkout flows, subscription management, cookie/consent banners, onboarding).

## 2. Regulatory angle (2026)

**US / FTC:**
- FTC's 2022 staff report "Bringing Dark Patterns to Light" (ftc.gov/reports/bringing-dark-patterns-light) remains the core enforcement-policy reference, targeting subscription traps, hidden fees, confusing cancellation, and manipulated default settings under Section 5 of the FTC Act (unfair/deceptive practices).
- FTC's 2024 "Click-to-Cancel" rule (require cancellation to be as easy as sign-up) was vacated by a federal appeals court in 2025 on procedural grounds, but the underlying principles (transparency, easy opt-out, express informed consent) remain enforceable under existing unfairness/deception authority.
- Landmark case: Amazon settled an FTC Prime "dark patterns" subscription case for $2.5B in September 2025 — the largest dark-pattern enforcement action to date. FTC also charged Epic Games over dark patterns causing unintended in-game purchases by children and a deliberately hard cancellation/refund process.
- State privacy laws (CCPA/CPRA, Colorado Privacy Act, Texas Data Privacy and Security Act, and others) now explicitly prohibit using dark patterns to obtain consumer consent — meaning dark-pattern risk is now also a privacy-compliance risk, not just an FTC-fairness risk.

**EU:**
- Digital Services Act (DSA) Article 25 already bans "dark patterns" on online platforms, defined as practices that materially distort or impair users' ability to make autonomous, informed decisions (e.g., aggressive pop-ups, confusing consent buttons). Enforced by the European Commission (largest platforms) and national Digital Services Coordinators.
- The European Commission has preliminarily found Meta in breach of the DSA over the addictive design of Instagram/Facebook — a live example of "Addictive Design" being treated as a legal violation, not just an ethics footnote.
- A dedicated Digital Fairness Act (DFA) is planned for tabling in Q4 2026, explicitly targeting dark patterns, addictive design, manipulative personalization, and misleading influencer marketing — though realistic adoption is expected late 2027 with phased application into 2028-2030. Useful to flag as "coming regulation" for any EU-facing product roadmap.

## 3. Legitimate persuasion vs. dark pattern — the distinction test

Brignull's own framing (from his talks/book, paraphrased): a dark pattern is a manipulative or deceptive design trick that gets a user to do something they would NOT have done if they had fully understood what was happening, or if they'd had a genuine, unimpaired choice at the moment of decision. Deceptive.design's homepage phrases the outcome test similarly: patterns that "trick people into doing things they didn't mean to" or "steer them into harmful decisions they would not have made deliberately."

Practical operationalization for the skill's ethical-line section:
- **The counterfactual/consent test**: would the user take this action if they had full information and no artificial friction/pressure? If informed consent would reverse the choice, it's a dark pattern.
- **The "does it work because they don't notice" test**: legitimate persuasion works even when the user is fully aware of the technique (e.g., a real scarcity claim, an honest social-proof stat, a genuine limited-time offer). A dark pattern's effectiveness depends on the user NOT noticing the mechanism, or noticing too late to act on it (e.g., a fake countdown, a disguised ad, obstructive cancellation flow).
- **Reversibility/symmetry check**: is declining/canceling exactly as easy as accepting/subscribing? Asymmetric friction (easy in, hard out) is the single most common enforcement trigger (Amazon Prime, Epic Games cases above).

## Citations & confidence

- deceptive.design/types — full taxonomy and definitions. Confidence: HIGH (primary source, fetched directly).
- deceptive.design homepage — outcome-based definition. Confidence: HIGH (primary source, fetched directly).
- FTC, "Bringing Dark Patterns to Light" (ftc.gov/reports/bringing-dark-patterns-light). Confidence: HIGH (primary source, well-established).
- Amazon Prime $2.5B settlement, Epic Games case, Click-to-Cancel vacatur — via search summaries (Pandectes, PageAuditors, Reed Smith, PerformLine blog posts). Confidence: MED (secondary/legal-blog sources, not independently cross-checked against primary FTC press releases in this pass — figures and framing are consistent across multiple independent sources, which raises confidence, but recommend a primary-source check before citing the $2.5B figure in anything client-facing).
- EU DSA Article 25 dark-patterns ban, Meta preliminary DSA breach finding, Digital Fairness Act Q4 2026 timeline — via search summaries (European Parliament EPRS study PDF, Osborne Clarke, gblock.app, digital-fairness-act.com). Confidence: MED (secondary sources; EPRS PDF is a credible EU Parliament research service study, raising confidence on the DSA/DFA mechanics specifically to MED-HIGH).
- Brignull's "wouldn't have done it if informed" definition and distinction test — via search summary (suebehaviouraldesign.com, arxiv "What Makes a Dark Pattern... Dark?" paper reference). Confidence: MED (paraphrase-of-paraphrase; the core "counterfactual consent" framing is well corroborated across multiple sources and matches the deceptive.design homepage language directly fetched, so treat the core test as HIGH, the precise wording as MED).
