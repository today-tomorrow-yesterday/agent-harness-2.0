# Laws of UX and related named laws

> Research digest behind `SKILL.md`, produced by one sub-agent of a six-way parallel research pass (each agent had one lane; "Agent A" through "Agent F" below refer to those lanes). Claims carry the agent's own confidence flags; verify a load-bearing one against its cited source before relying on it.


Source base: lawsofux.com (Jon Yablonski, "Laws of UX: Using Psychology to Design Better Products & Services," 2nd ed. 2024), cross-checked against Nielsen Norman Group (NN/g) where noted.

Excluded per instructions (already in skill): decision fatigue/smart defaults, goal-gradient effect, reciprocity, IKEA/endowment effect, loss aversion/status-quo bias, contrast effect/anchoring.

Full list on lawsofux.com (30 entries) for reference: Aesthetic-Usability Effect, Choice Overload, Chunking, Cognitive Bias, Cognitive Load, Doherty Threshold, Fitts's Law, Flow, Goal-Gradient Effect*, Hick's Law, Jakob's Law, Law of Common Region, Law of Proximity, Law of Prägnanz, Law of Similarity, Law of Uniform Connectedness, Mental Model, Miller's Law, Occam's Razor, Paradox of the Active User, Pareto Principle, Parkinson's Law, Peak-End Rule, Postel's Law, Selective Attention, Serial Position Effect, Tesler's Law, Von Restorff Effect, Working Memory, Zeigarnik Effect. (*already covered elsewhere in skill, excluded here.)

Note: "Confirmation Bias" and "Curse of Knowledge" are NOT on lawsofux.com's list (the site has a generic "Cognitive Bias" entry instead) — sourced from Nielsen Norman Group and secondary sources instead, flagged accordingly.

---

## 1. Hick's Law
**Source:** https://lawsofux.com/hicks-law/ — Confidence: HIGH

**Mechanism:** Decision time increases logarithmically with the number and complexity of choices available (named for William Edmund Hick & Ray Hyman, 1952).

**UI failure pattern:** Navigation bars or settings screens that expose every possible option flatly and simultaneously (e.g., a 15-item top nav, a signup form with 20 unnecessary fields, a remote control with 40 undifferentiated buttons) — causes users to freeze, stall, or bail rather than choose.

**UI fix pattern:** Reduce visible choices at any one decision point; break complex tasks into sequential steps (progressive disclosure); highlight/pre-select a recommended default option; progressively reveal advanced features only after basic competence (Slack's bot-first onboarding); push complexity into secondary menus (Apple TV remote offloads choice into the TV UI rather than the remote itself).

**Caveat from source:** Don't over-simplify to the point of hiding functionality users actually need.

---

## 2. Fitts's Law
**Source:** https://lawsofux.com/fittss-law/ — Confidence: HIGH

**Mechanism:** Time to acquire (click/tap) a target is a function of distance to the target and the target's size — small, far targets take longer and error more (Paul Fitts, 1954). There's an inherent speed-accuracy tradeoff.

**UI failure pattern:** Tiny tap targets on mobile (close buttons, checkboxes, icon-only buttons packed edge-to-edge with no spacing) that cause mis-taps, especially for primary actions users need to hit quickly and repeatedly; important CTAs placed far from the user's current focus/thumb zone.

**UI fix pattern:** Enlarge touch targets (44x44pt+ per platform HIG minimums), add spacing/padding around interactive elements to prevent adjacent mis-taps, place frequent/primary actions within easy reach (thumb zone on mobile, near cursor/content on desktop), keep related action buttons close to the content they act on rather than banished to a distant toolbar.

---

## 3. Jakob's Law
**Source:** https://lawsofux.com/jakobs-law/ — Confidence: HIGH

**Mechanism:** Users spend most of their time on *other* sites/apps, so they transfer expectations from those familiar experiences onto yours and expect your product to behave the same way (Jakob Nielsen).

**UI failure pattern:** Reinventing standard interaction patterns for novelty's sake — nonstandard icon meanings, a hamburger menu that opens a full modal takeover instead of a drawer, custom scroll/gesture behavior, unconventional checkout flows — forces users to relearn basic navigation and increases task time/errors even when the new pattern is "objectively" fine.

**UI fix pattern:** Reuse established mental models and conventions (standard cart icon, standard form control appearance, familiar placement of search/nav/profile) so cognitive effort goes toward the user's actual task, not toward decoding the interface. When you must change a familiar pattern, ease the transition (YouTube's 2017 redesign let users preview/opt into Material Design and revert, avoiding backlash).

---

## 4. Miller's Law (+ Chunking)
**Source:** https://lawsofux.com/millers-law/ and https://lawsofux.com/chunking/ — Confidence: HIGH

**Mechanism:** Working memory holds roughly 7 (±2) items at once (George Miller, 1956); chunking — grouping related pieces of information into a meaningful whole — is the primary technique for working within that limit (also ties to Miller's own research).

**UI failure pattern:** Long unformatted digit strings (16-digit card numbers, phone numbers) presented as a single blob; forms or dashboards listing many discrete data points with no grouping, forcing users to hold too much ungrouped information in memory to complete a task or compare options.

**UI fix pattern:** Segment long strings into recognizable chunks (card number in 4-digit groups, phone number with area code separated); group related form fields/settings under clear headings; use visual hierarchy and whitespace to cluster related content into scannable modules rather than one long undifferentiated list. Caveat: don't treat "7±2" as a rigid item-count rule — working memory capacity varies by user expertise and context; the real lever is meaningful grouping, not counting items.

---

## 5. Peak-End Rule
**Source:** https://lawsofux.com/peak-end-rule/ — Confidence: HIGH

**Mechanism:** People judge an entire experience mainly by how they felt at its most intense moment (peak) and at its conclusion (end), not by the average or total of every moment (Kahneman et al., 1993).

**UI failure pattern:** A product with a strong core experience but a flat, transactional, or frustrating final step (an abrupt "Order placed." with no delight, a confusing cancellation flow, an error-prone final confirmation screen) — the ending disproportionately damages overall perception even if everything before it was smooth. Also: ignoring the single moment of maximum value/frustration in a journey (e.g., not addressing the exact point users hit friction) while polishing everywhere else.

**UI fix pattern:** Identify and deliberately design the single highest-value/most-intense moment in the journey and the final moment — invest disproportionate craft there (Mailchimp's animated, humor-infused send confirmation turns a routine action into a memorable peak). Manage perceived wait/uncertainty near the end of a flow (Uber shaping perception of wait time to prevent cancellations near the "end" of the request moment). Remember negative peaks are recalled more vividly than positive ones, so prioritize eliminating friction at foreseeable failure points over polishing already-fine steps.

---

## 6. Zeigarnik Effect
**Source:** https://lawsofux.com/zeigarnik-effect/ — Confidence: HIGH

**Mechanism:** People remember and are pulled back toward incomplete or interrupted tasks more than completed ones (Bluma Zeigarnik, 1920s).

**UI failure pattern:** Onboarding or profile-completion flows that give no indication of "how much is left" or that content exists beyond the current view — users don't feel the pull to return and finish, and abandon partway with no psychological tension driving completion.

**UI fix pattern:** Visible progress indicators (progress bars, "3 of 5 steps," profile-completion percentage) that make the *incompleteness* itself salient and motivating; visual cues signaling more content exists just out of view (partially cut-off cards/carousels hinting there's more to scroll); artificial head-start progress (a bar that opens already 10% full) to trigger the drive to close the loop. This is the same underlying mechanism used by "resume where you left off" flows.

---

## 7. Von Restorff Effect (Isolation Effect)
**Source:** https://lawsofux.com/von-restorff-effect/ — Confidence: HIGH

**Mechanism:** Among a set of similar items, the one item that visually differs is disproportionately noticed and remembered (Hedwig von Restorff, 1933).

**UI failure pattern:** Every button/CTA on a screen styled with equal visual weight (all solid colored, same size) so the single action that actually matters (e.g., "Upgrade," "Submit," the one destructive/irreversible action) doesn't stand out and gets missed or, worse, mis-clicked among lookalikes. Also the inverse failure: overusing distinct styling on too many elements so nothing reads as primary anymore, or a promo banner made so distinct it now looks like an ad and gets ignored (interacts with Selective Attention below).

**UI fix pattern:** Give the one truly primary action a distinct visual treatment (color, size, position) against a calmer secondary/tertiary button system; use isolation sparingly — one emphasized element per view, not several competing for attention; don't rely on color alone (accessibility: color-blind/low-vision users need a non-color signal too — shape, icon, weight); be cautious with motion-based emphasis for motion-sensitive users.

---

## 8. Serial Position Effect
**Source:** https://lawsofux.com/serial-position-effect/ — Confidence: HIGH

**Mechanism:** Users best remember the first items (primacy) and last items (recency) in a list or sequence; middle items are recalled worst (Hermann Ebbinghaus).

**UI failure pattern:** Burying the most important nav item, menu option, or list entry in the middle of a long list (e.g., item #6 of 11 in a settings menu, or the actual best-value pricing tier placed dead-center in a 5-tier list) — it statistically gets the least attention and recall.

**UI fix pattern:** Place the most critical actions/items at the very start or very end of navigation, lists, and toolbars; reserve middle positions for lower-priority or reference-only content; in pricing tables, this cautions against assuming "put the best option in the middle" is always optimal for *recall* even if it aids visual comparison — worth testing against this effect specifically for long lists (nav bars, dropdown menus).

---

## 9. Aesthetic-Usability Effect
**Source:** https://lawsofux.com/aesthetic-usability-effect/ — Confidence: HIGH

**Mechanism:** Users perceive visually attractive designs as more usable than they may actually be, and are more forgiving of real usability flaws when the design looks polished (Kurosu & Kashimura, Hitachi, 1995 — ATM interface study where aesthetic ratings predicted perceived usability better than actual usability did).

**UI failure pattern (as an ethics/QA flag, not just a benefit):** Relying on visual polish to paper over genuine usability defects that never get fixed because user complaints are muted by how "nice" the product looks — the effect can mask real problems from surfacing in testing and feedback.

**UI fix pattern:** Invest in visual craft deliberately (it earns real patience/goodwill and reduces perceived friction), but never substitute aesthetics for usability testing — treat a beautiful interface as a reason to test *harder* for hidden usability problems, not a reason to skip testing.

---

## 10. Doherty Threshold
**Source:** https://lawsofux.com/doherty-threshold/ — Confidence: HIGH

**Mechanism:** Productivity and engagement rise sharply when system response time is under ~400ms — fast enough that neither the user nor the system is "waiting" on the other (Doherty & Thadani, IBM Systems Journal, 1982; found response times at this threshold made systems feel "addicting").

**UI failure pattern:** Interfaces that leave users staring at a blank/frozen screen during backend processing with no feedback, or that are simply slow (>400ms, and especially >1-2s) without any perceived-performance mitigation — users perceive the product as sluggish and disengage.

**UI fix pattern:** Deliver real responses within 400ms where possible; where true latency exceeds that, use perceived-performance techniques — skeleton screens, optimistic UI updates, loading animations, progress indicators — to keep the interaction feeling responsive; note the counterintuitive corollary that a small deliberate delay can sometimes increase perceived value/trust (e.g., a "searching thousands of flights..." animation), so instant isn't always better if it undermines credibility.

---

## 11. Tesler's Law (Law of Conservation of Complexity)
**Source:** https://lawsofux.com/teslers-law/ — Confidence: HIGH

**Mechanism:** Every system has an irreducible core of complexity that cannot be designed away — it can only be moved, either absorbed by the system/design or pushed onto the user (Larry Tesler, Xerox PARC, mid-1980s).

**UI failure pattern:** Forms or flows that offload complexity onto the user instead of the system — e.g., asking users to manually compute/derive a value the app already has the data to calculate, requiring users to re-enter information the system could infer or remember, exposing raw configuration/technical steps instead of handling them automatically. Also the failure of assuming an idealized, perfectly rational user who will read every label and never make a mistake.

**UI fix pattern:** Push complexity toward engineering effort rather than user effort whenever it's transferable — auto-fill/inference, smart defaults, sensible pre-computation; when some complexity genuinely can't be removed and must live with the user, surface contextual help exactly at the point of friction (inline tooltips within the workflow, not a separate help doc) rather than assuming users will figure it out unaided.

---

## 12. Gestalt grouping laws relevant to UI: Law of Proximity & Law of Common Region
**Source:** https://lawsofux.com/law-of-proximity/, https://lawsofux.com/law-of-common-region/ — Confidence: HIGH

**Mechanism (Proximity):** Elements placed near each other are perceptually grouped as related, regardless of whether they actually differ in content type.
**Mechanism (Common Region):** Elements sharing a visually bounded area (a border, a card, a background fill) are perceived as one group even if they are not spatially close.

**UI failure pattern:** Inconsistent or ambiguous spacing that accidentally implies false relationships — e.g., a form field's helper text sitting closer to the *next* field than the one it describes, causing users to associate it with the wrong input; unrelated actions crammed into the same visual container so users assume they're related options.

**UI fix pattern:** Use consistent, deliberate whitespace so proximity always reflects true relationships (label/helper text closer to its own field than to neighboring fields); use cards, borders, or background shading (common region) to bundle genuinely related settings/content into a single visually distinct unit — Google's search results use proximity spacing between result blocks to make each feel like one scannable unit.

---

## 13. Cognitive Load
**Source:** https://lawsofux.com/cognitive-load/ — Confidence: HIGH

**Mechanism:** The total mental effort required to understand and operate an interface, split into intrinsic load (inherent task/information difficulty) and extraneous load (unnecessary difficulty added by poor design — clutter, confusing layout, inconsistent patterns) (John Sweller, cognitive load theory, late 1980s).

**UI failure pattern:** Dense dashboards or settings screens with competing visual signals, inconsistent iconography, redundant navigation paths, or unnecessary decorative elements that add extraneous load on top of the task's inherent difficulty — users complete tasks slower, miss details, and report more frustration even when the underlying task isn't objectively hard.

**UI fix pattern:** Ruthlessly cut extraneous load — remove decorative/non-functional elements, simplify layout and reduce simultaneous decisions, apply consistent patterns across the product so users don't re-learn navigation on every screen; reserve the user's limited mental budget for the *intrinsic* difficulty of their actual goal, not for parsing your UI.

---

## 14. Selective Attention (banner blindness, change blindness)
**Source:** https://lawsofux.com/selective-attention/ — Confidence: HIGH

**Mechanism:** Users filter perception down to a subset of stimuli relevant to their current goal, tuning out the rest — includes "banner blindness" (learned dismissal of ad-shaped content) and "change blindness" (failing to notice interface changes without a clear draw of attention).

**UI failure pattern:** Placing genuinely important content (a critical alert, a real feature announcement) in a location or style that visually resembles an ad or promotional banner — users have trained themselves to ignore anything shaped like a banner, so real information gets filtered out along with the ads. Similarly, silently updating interface state (e.g., a saved-status change, a new badge) with no attention-grabbing cue means users don't register the change happened at all.

**UI fix pattern:** Never style important functional content (system messages, key CTAs) to resemble ad units or place it in traditionally ad-occupied zones (top banner strip, right rail); when the interface changes state in a way the user needs to notice, pair it with a deliberate, non-ad-like attention cue (brief animation, toast, distinct color) rather than assuming users will spot a silent change.

---

## 15. Pareto Principle
**Source:** https://lawsofux.com/pareto-principle/ — Confidence: HIGH

**Mechanism:** Roughly 80% of outcomes/usage come from roughly 20% of causes/features (Vilfredo Pareto) — in UX terms, most user value and engagement concentrate in a small subset of features or flows.

**UI failure pattern:** Spreading design/QA/polish effort evenly across every feature regardless of actual usage, so the handful of flows that account for most real usage (login, checkout, core task) get the same shallow attention as rarely-used edge features — the highest-leverage surfaces stay mediocre.

**UI fix pattern:** Instrument usage data to find the actual 20% of flows driving 80% of engagement/value, and concentrate design refinement, performance budget, and usability testing there first, before polishing long-tail features.

---

## 16. Parkinson's Law
**Source:** https://lawsofux.com/parkinsons-law/ — Confidence: HIGH

**Mechanism:** A task expands to fill however much time is allotted to it (Cyril Northcote Parkinson, 1955) — applies to user-facing task duration, not just workplace productivity.

**UI failure pattern:** Open-ended forms/checkouts with no implied time pressure or structure (e.g., a lengthy signup with no sense of "this should take 2 minutes") let users dawdle, second-guess, and abandon, because nothing bounds how long the task "should" take.

**UI fix pattern:** Compress the *actual* time a task takes below what users expect (autofill, pre-filled defaults, fewer fields) and communicate realistic time expectations up front (progress indicators, "2 of 3 steps," estimated completion time) so the task doesn't psychologically expand to fill unlimited perceived time.

---

## 17. Confirmation Bias (in UX practice, not just cognitive bias in general)
**Source:** https://www.nngroup.com/articles/confirmation-bias-ux/ — Confidence: HIGH (direct NN/g article; note this is about bias in the *design/research process* rather than a UI pattern users experience, so it's more of a practitioner self-check than a "UI fix")

**Mechanism:** Designers/researchers who are invested in a design tend to interpret ambiguous evidence, usability test observations, and survey results in ways that confirm their existing assumptions, and discount or under-explore evidence that contradicts them.

**Failure pattern (process-level, not literally "UI" but shapes what ships):** Writing leading research questions that presuppose the answer (NN/g's example: asking "Was the red checkout button difficult to locate?" instead of open-endedly investigating why an e-commerce site had high traffic but low conversion) — this narrows the investigation to confirm a pet theory (the button) and can cause teams to ship a fix for the wrong problem while the real friction (pricing, trust signals, shipping cost surprise, etc.) goes untouched.

**Fix pattern:** Write neutral, open-ended research questions instead of leading ones; deliberately seek disconfirming evidence during usability testing rather than only evidence that supports the current design; separate "what did we observe" from "what did we expect to observe" when synthesizing test notes; the more time/ego invested in a design, the more deliberately researchers should red-team their own conclusions.

**Relevance note:** This is included because it's a well-known named bias frequently taught alongside Laws of UX content, but note it's about designer/researcher cognition shaping decisions, distinct from Yablonski's user-facing "laws." Flagging this distinction for whoever assembles the final skill file — may fit better in the ethics/bias section than the "laws" section.

---

## 18. Curse of Knowledge
**Source:** Medium ("The Curse of Knowledge in UX" by Ehsan Jamalzadeh, https://medium.com/design-bootcamp/the-curse-of-knowledge-in-ux-2f5461887037) — Confidence: LOW (secondary source, not lawsofux.com or NN/g directly; NN/g coverage found was about onboarding new UX *hires*, not this bias specifically, so treat this entry as needing independent verification before being presented as authoritative)

**Mechanism:** Once a designer/team knows how their product works, it becomes very difficult to model the mental state of someone who doesn't — expert knowledge is "cursed" in that it can't easily be unlearned to simulate a novice's perspective.

**UI failure pattern:** Onboarding flows and empty states written by people who already understand the product deeply, so they skip steps that feel "obvious" to them but aren't obvious to a first-time user — jargon-heavy labels, icon-only actions with no label because "everyone knows what that icon means," missing first-run guidance because the team forgot what it felt like not to know the product.

**UI fix pattern:** Test onboarding and first-run experiences specifically with genuinely new users (not internal team members or power users) to catch curse-of-knowledge gaps; write UI copy and first-time tooltips as if for someone with zero context; treat "this feels too obvious to explain" as a signal to explain it anyway.

---

## Gap / coverage notes
- Did not find dedicated deep pages for Flow, Mental Model, Working Memory, Occam's Razor, Postel's Law, Paradox of the Active User, Law of Prägnanz, Law of Similarity, Law of Uniform Connectedness, Choice Overload on lawsofux.com in this pass (site confirmed they exist per the index fetch) — deprioritized per the "8-10 highest value" instruction since they're less directly actionable for everyday onboarding/forms/nav/notification critique than the 17 above. Full site URL for anyone wanting the remaining entries: https://lawsofux.com/ (each law has a page at `https://lawsofux.com/<slug>/`).
- Confirmation Bias and Curse of Knowledge are NOT part of the "Laws of UX" canon (Yablonski's book/site) — included here only because they're closely-related named cognitive biases commonly taught alongside it, per the task's explicit list. Flagging in case the skill maintainer wants these routed to the dark-patterns/ethics section (Agent E's lane) instead of the "named laws" section.
- Book note: Yablonski published a 2nd edition of "Laws of UX" in 2024, which reportedly added coverage of AI/spatial-computing-era interfaces — full content of the 2nd edition beyond the free site content was not independently verified (would require purchasing/reading the book itself).
