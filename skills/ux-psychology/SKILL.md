---
name: ux-psychology
description: "Critique or design any UI flow, onboarding sequence, paywall, pricing screen, sign-up form or other conversion-driving surface by reasoning from named behavioral-psychology mechanisms (decision fatigue, goal-gradient, reciprocity, IKEA effect, loss aversion, anchoring, Laws of UX, Cialdini, Hook/Fogg models) rather than surface aesthetics, and flag when a technique crosses into a dark pattern. Use when a screen looks fine but does not convert, when designing a signup/onboarding/pricing flow, or when auditing persuasion for manipulation. Triggers on: ux psychology, why isn't this converting, onboarding drop-off, paywall review, dark pattern check"
---

# UX Psychology — the designer-psychologist lens

## Overview

Most UI critique stops at "does this look good." This skill is the layer underneath: **why does a user's brain actually respond to this screen the way it does.** It gives six named, research-grounded cognitive mechanisms, each with a recognizable failure pattern and fix pattern, so a design decision can be justified by psychological mechanism rather than taste alone.

Grounded in the "6 UX psychology principles" framework popularized by the `uxpeak` YouTube channel, cross-checked against the underlying academic sources (Kahneman & Tversky's prospect theory, Cialdini's reciprocity research, the IKEA-effect and goal-gradient-effect literature, and the classic Iyengar/Lepper Columbia jam study on choice overload). The extended sections were added from a six-lane parallel research pass whose digests ship in `references/` (see "Further reading").

## When to use

- Reviewing a screen that "looks fine but doesn't convert" — onboarding drop-off, paywall bounce, form abandonment, upgrade-prompt dismissal. The gap is usually psychological, not visual.
- Designing a NEW flow (signup, onboarding, pricing, upsell) and wanting the psychological mechanism decided before the pixels.
- A stakeholder asks "why does this work" about a competitor's screen, not just "what does it look like."
- Auditing whether a persuasion technique has crossed from legitimate design into a dark pattern (see Ethical line below) — this skill flags both directions.

**Not for:** visual style, typography, color, layout, code quality, accessibility mechanics, animation/motion — use a visual-design or frontend skill for those. This skill answers "why would a human do the thing," not "does this look premium." It owns the persuasion-and-motivation layer underneath the pixels, so pair it with a visual lens rather than using it alone on frontend work.

## The six mechanisms

| # | Mechanism | One-line trigger | Failure pattern (what breaks it) | Fix pattern |
|---|---|---|---|---|
| 1 | **Decision fatigue → Smart defaults** | Every unfilled field/choice is a tiny tax; too many at once causes abandonment, not careful consideration | Blank forms, long unranked option lists (more choices ≠ more conversion — Iyengar/Lepper's jam study: 24 options → 3% purchase rate, 6 options → 30%) | Pre-fill the most common choice per field. The user's job shifts from "fill this out" to "scan and adjust." A visible default reads as an implicit recommendation, not laziness. |
| 2 | **Goal-gradient effect** | Motivation to finish accelerates as the *perceived* distance to the goal shrinks — independent of real effort remaining | Starting a progress bar/counter at literal 0% feels like standing still, even when the real work left is identical | Never start a user at zero. Give an artificial head start — count something already done (a stamp already punched, a profile field already known) so the first view of progress already shows motion. |
| 3 | **Reciprocity** | Receiving something of value first creates an unconscious pull to reciprocate — ranked by Cialdini as one of the strongest drivers of human behavior | Asking for signup/payment before the user has received anything (paywalling a result behind an unfilled account) | Deliver real, if partial, value FIRST — a real (if partial) report, a working trial, a usable free tier — then ask. The ask stops feeling like a wall because the user already has a reason to reciprocate. |
| 4 | **IKEA / endowment effect** | People assign disproportionately higher value to things they built or chose themselves, even when objectively identical to a pre-made version | A signup form (email/password/submit) has nothing the user made — nothing to lose by abandoning it | Move real choices (name, goal, first small win) BEFORE the signup wall, so leaving feels like abandoning something built, not skipping a form. The CTA can then honestly say "Continue" rather than "Sign up." |
| 5 | **Loss aversion / status-quo bias** | Kahneman & Tversky: the pain of losing something is felt roughly twice as intensely as the pleasure of an equivalent gain | Framing an upsell/CTA purely as a gain ("Upgrade now") gives the user a frictionless, guilt-free exit ("Maybe later") | Reframe around what's already theirs and at risk (named files, an expiring benefit, a real countdown) rather than what they could gain. The dismiss option should require acknowledging the cost ("I'll risk it"), not a free pass. |
| 6 | **Contrast effect / anchoring** | The brain evaluates any number relative to the number it saw immediately before, not in absolute terms | Showing a price/cost in isolation forces an absolute (harsher) judgment | Control what the user sees immediately before the number you want accepted. A $50/mo add-on shown alone reads as $600/year; shown right under a $1,900 purchase it reads as "2.6%, basically nothing." Don't show a cost in isolation — choose its anchor deliberately. |

## Extended mechanisms — Laws of UX

Additional named, research-grounded laws (primarily Jon Yablonski's "Laws of UX," lawsofux.com, cross-checked against Nielsen Norman Group) worth reasoning from once the six core mechanisms above are covered. Full digest: `references/laws-of-ux.md`.

| Law | One-line trigger | Failure pattern | Fix pattern |
|---|---|---|---|
| **Hick's Law** | Decision time rises with the number/complexity of choices offered | A flat nav bar or form exposing every option at once causes stall or abandonment | Progressive disclosure; highlight one recommended default; push rarely-needed complexity into secondary menus |
| **Fitts's Law** | Time to reach a target is a function of its distance and size | Tiny or cramped tap targets, or a primary CTA placed far from the natural thumb zone | 44×44pt+ targets; put the most frequent actions within easy physical reach |
| **Jakob's Law** | Users expect a product to work like every other product they already know | Novel interaction patterns adopted for novelty's sake (nonstandard icons/gestures) | Reuse established conventions; when you must deviate, ease the transition (e.g. offer a "revert to old version" period) |
| **Miller's Law / Chunking** | Working memory holds roughly 7±2 items at once | Long unformatted digit strings, dense ungrouped forms/dashboards | Segment strings into chunks (card numbers); group related fields under clear headings — the lever is meaningful grouping, not raw item-counting |
| **Peak-End Rule** | Experiences are judged by their single peak moment and their ending, not the average of the whole | A flat or frustrating final step undoes an otherwise good journey | Invest disproportionate craft in the ONE highest-value moment and the ending (a delightful confirmation screen, managed wait-time perception) |
| **Zeigarnik Effect** | Incomplete tasks are remembered and pulled toward more strongly than completed ones | No visible sense of "how much is left," so users abandon with nothing pulling them back | Visible progress ("3 of 5 steps"), streaks, unfinished-task reminders — same family as the goal-gradient mechanism above but memory-driven rather than motivation-driven |
| **Von Restorff (Isolation) Effect** | The one item that visually differs from a set is what gets remembered | Every button/element styled with equal visual weight, so the action that matters doesn't stand out | One emphasized primary action per view, applied sparingly, never signaled by color alone (accessibility) |
| **Aesthetic-Usability Effect** | Attractive design is perceived as more usable, which can mask real usability flaws | Visual polish substitutes for actually fixing usability problems, muting negative user feedback | Treat strong visual polish as a reason to usability-test HARDER, not skip testing — the classic finding is from an ATM interface study (Kurosu & Kashimura) |
| **Doherty Threshold** | Productivity/engagement rises sharply once system response time drops below ~400ms | A frozen screen during processing with no feedback | Perceived-performance techniques (skeleton screens, optimistic UI) when true latency exceeds 400ms; note a deliberate small delay can sometimes read as more trustworthy for high-stakes actions |
| **Tesler's Law (Conservation of Complexity)** | Every system carries an irreducible amount of complexity — it has to live somewhere, either in the system or the user | Computation or re-entry the system already has data for gets offloaded onto the user | Push complexity into engineering (auto-fill, smart defaults — same family as decision-fatigue mechanism 1); surface only the genuinely unavoidable complexity, exactly at the point of friction |
| **Serial Position Effect** | The first and last items in a list are recalled best; the middle is weakest | Burying the most important nav item or best pricing tier in the middle of a long list | Place the critical item(s) at the start or end of any list, toolbar, or pricing table |

## Cialdini's other principles of influence

Beyond reciprocity (mechanism 3 above), Robert Cialdini's remaining principles of influence (*Influence*; *Pre-Suasion* for Unity) map onto concrete UI patterns. **Scarcity's core mechanism overlaps with loss aversion (mechanism 5) — don't treat it as a separate lever, just a scarcity-flavored application of the same one.** Full digest: `references/cialdini.md`.

| Principle | Mechanism | UI pattern | Dark-pattern edge |
|---|---|---|---|
| **Commitment & Consistency** | A small voluntary commitment creates pressure to act consistently with it later (foot-in-the-door effect) | Onboarding that opens with a low-effort, self-articulated goal before any account/payment ask — a "micro-yes" chain | Tricking users into an unclear micro-yes (a buried pre-checked upsell framed as a "commitment") |
| **Social Proof** | Observing others' behavior lowers the perceived risk of a decision | Reviews/ratings near the CTA, "X people bought this today," "customers also bought" | Fabricated or stale counters — backfires visibly once numbers look implausibly low or high |
| **Authority** | Automatic deference to titles, credentials, or symbols of expertise — not verified expertise itself | Trust badges at checkout, credentialed staff shown near a decision point, platform-endorsement labels | Unrelated-field endorsements, expired certifications, unauthorized use of a trust logo |
| **Liking** | People are more easily influenced by those they find similar, familiar, or cooperative | Real staff/founder photos and stories, copy voice that mirrors the audience, friend-referral flows | Manufactured "authenticity" — staged photos or fabricated founder stories presented as real |
| **Scarcity** *(cross-ref mechanism 5)* | Limited quantity/time/access raises perceived value, partly by tripping loss aversion and partly by implying quality | Countdown timers plus real stock counts; invite-only access | Fake low-stock labels or countdown timers that silently reset — documented at scale across dark-pattern crawls |
| **Unity** | Shared identity / "we-ness" — distinct from mere liking; Cialdini's 7th principle | "People like you" cohort framing; asking users for "advice" rather than "opinion" (raises felt togetherness) | Fabricated in-group belonging, or "advice"-framing used to extract free user labor while implying false co-ownership |

## Habit-formation models

Two frameworks for diagnosing WHY a desired behavior isn't happening, or why a product becomes habitual — a level up from any single mechanism above. Full digest: `references/habit-models.md`.

**Nir Eyal's Hook Model** (*Hooked*) — a 4-stage loop that turns intentional use into automatic habit:
1. **Trigger** — starts external (a notification, an icon badge) and, over repeated cycles, becomes internal (boredom or loneliness alone is enough to open the app).
2. **Action** — the simplest possible behavior toward a reward, with friction minimized (an infinite-scroll gesture).
3. **Variable Reward** — an unpredictable payoff (tribe/social validation, hunt/information, or self/mastery) — the unpredictability itself is what makes it habit-forming, not the reward's average value. Rooted in Skinner's variable-ratio reinforcement: uncertain payouts produce more persistent behavior than predictable ones.
4. **Investment** — the user deposits time, data, effort, or social capital (playlists built, streaks kept), which raises the switching cost and loads the next trigger.

**BJ Fogg's Behavior Model (B = MAP)** — Stanford Behavior Design Lab: a behavior only happens when **Motivation, Ability, and Prompt** converge simultaneously. Use it to diagnose a stalled CTA — isolate which leg is actually weak:
- **Motivation problem** — an easy, visible CTA that nobody wants.
- **Ability/friction problem** — a wanted action buried behind too many steps or fields.
- **Missing-prompt problem** — motivation and ability both exist, but no cue appears at the moment the user is ready.

**Ethical note:** both frameworks are the exact toolbox that habit-forming design shares with addictive design — the line is the same "would the user consent if they understood the mechanism" test in the Ethical line section below.

## How to apply — the psychology audit

Walk the flow screen-by-screen and ask, for each screen:

1. **What decision is being asked of the user right here, and how many choices does it actually take to get past it?** (→ mechanism 1)
2. **Does any progress/completion indicator start at a literal zero, when it could count something already true?** (→ mechanism 2)
3. **Has the user received anything of real value BEFORE this ask?** (→ mechanism 3)
4. **Has the user made any choice/customization they'd feel they're abandoning by leaving?** (→ mechanism 4)
5. **Is the CTA framed as a gain (weak) or a loss/risk (strong)?** (→ mechanism 5)
6. **What number did the user see immediately before the number you want them to accept, and did you choose that on purpose?** (→ mechanism 6)
7. **Is there one moment (the peak) and the ending getting disproportionate craft, or is effort spread flat across the whole flow?** (→ Peak-End Rule)
8. **Would this technique still work if the user fully understood what it was doing?** If no, it's not persuasion anymore — go to the Ethical line section below before shipping it.

A screen that's flat/non-converting despite good visual polish is almost always missing 2-3 of these, not all of them — name which ones explicitly rather than giving generic "make it pop" feedback.

## Ethical line — persuasion vs. dark pattern

Every mechanism above is a double-edged tool. **The distinction test (Harry Brignull, deceptive.design):** a technique is a dark pattern if the user would NOT have taken the action had they fully understood the mechanism and been given genuine, unimpaired choice. A useful practical check is symmetry — is opting OUT exactly as easy as opting IN? Asymmetric friction is the single most common real-world enforcement trigger.

Common dark-pattern types worth naming explicitly when flagging a design (Brignull's taxonomy, deceptive.design; full ~18-category digest in `references/dark-patterns.md`):

| Pattern | What it does | Example |
|---|---|---|
| **Roach Motel** | Easy to get in, deliberately hard to get out | Sign up in 2 clicks, cancel only via a phone call |
| **Confirmshaming** | The decline option is worded to guilt the user | Exit-offer "No thanks" rewritten as "No, I don't want to save money" |
| **Sneaking** | Hides or delays material information to draw the user into a transaction | Travel insurance pre-added to a cart |
| **Hidden Costs** | A low advertised price balloons with fees revealed only at final checkout | A hotel booking's "resort fee" appearing on the last screen |
| **Visual Interference** | Real information exists but is buried, low-contrast, or disguised | A tiny gray "decline" link beside a huge colorful "accept" button |
| **Disguised Ads** | Ads styled to look like organic content or native UI controls | A "Download" button that's actually a paid ad above the real link |
| **Nagging** | Repeatedly re-prompting for something the user already declined | An app re-asking for notification permission on every launch |
| **Fake Urgency / Fake Scarcity** | Bogus countdowns or "only 2 left" claims untethered to reality | A countdown timer that silently resets on page refresh |
| **Preselection** | Defaults pre-checked to steer a choice against the user's likely preference | The pricier plan or marketing-consent checkbox pre-selected |
| **Fake Social Proof** | Fabricated reviews or live-viewer counters | "14 people are looking at this right now" with no real data behind it |

Three worked distinctions using the mechanisms above:
- Smart defaults (mechanism 1) that save the user real time = legitimate. The same default quietly opting them into a paid tier = **Preselection**.
- An honest countdown on real, expiring inventory (mechanism 5) = legitimate loss-aversion framing. A fake countdown that resets = **Fake Urgency**.
- Reciprocity (mechanism 3) via a genuinely useful free tier = legitimate. A "free" gift with hidden auto-enrolled subscription = **Sneaking**.

**This is not a hypothetical risk category.** Amazon settled an FTC dark-patterns case over Prime sign-up/cancellation for $2.5B (Sept 2025) — the largest such action to date; Epic Games was separately charged over dark patterns driving unintended purchases. In the EU, Digital Services Act Article 25 already bans dark patterns on platforms, with a dedicated Digital Fairness Act targeting addictive/manipulative design planned for tabling in Q4 2026. When using this skill to critique or design something, name the specific dark-pattern type if a recommended technique only works because the user doesn't notice it.

## Further reading — reference library

This skill deliberately stays curated and example-driven rather than exhaustive. The research digests it was built from ship alongside it:

| File | Covers |
|---|---|
| `references/laws-of-ux.md` | All Laws of UX entries with mechanism / failure / fix patterns, plus related named biases (cognitive load, confirmation bias, curse of knowledge) |
| `references/cialdini.md` | Cialdini's principles beyond reciprocity, the scarcity/loss-aversion overlap, dark-pattern edges per principle |
| `references/habit-models.md` | Hook Model, Fogg B=MAP, variable-reward psychology, with confidence flags per claim |
| `references/other-creators.md` | Creators and libraries doing "named principle" app breakdowns, and candidate principles they surface |
| `references/dark-patterns.md` | Brignull's current ~18-category taxonomy and the 2025–2026 regulatory context (FTC, EU DSA / Digital Fairness Act) |
| `references/open-source-references.md` | Open-source bias cheat sheets, dark-pattern datasets, and comparable skills/plugins |

External sources for deeper or broader coverage:

- **[Laws of UX](https://lawsofux.com)** (Jon Yablonski) — the source for the "Extended mechanisms" table above; covers additional laws not included here (Flow, Mental Model, Occam's Razor, Postel's Law, Choice Overload, Gestalt grouping laws).
- **[growth.design case studies](https://growth.design/case-studies)** — comic-style visual teardowns of real apps (Duolingo, Spotify, Airbnb, and 40+ more), each naming a specific psychological principle. Also surfaces two mechanisms not covered above: the **Baby Schema Effect** (Duolingo's mascot's childlike features triggering a protective response) and **Labor Perception Bias** (a visible-effort loading animation increasing perceived value of the result).
- **[Learning Loop](https://learningloop.io)** — an 80+ pattern "Plays" library with named principles and real product examples; its **Endowed Progress Effect** page directly reinforces the IKEA/endowment mechanism above.
- **[deceptive.design](https://www.deceptive.design/types)** (Harry Brignull) — the canonical dark-pattern taxonomy this section's table is drawn from; his 2023 book *Deceptive Patterns* has the full ~18-category version.
- **Buster Benson's Cognitive Bias Cheat Sheet** ([source JSON](https://github.com/busterbenson/public/blob/master/cognitive-bias-cheat-sheet.json)) — organizes ~180 cognitive biases into 4 root problems: too much information, not enough meaning, need to act fast, what to remember. Useful organizing lens if this skill's scope ever needs to expand into general cognitive-bias territory beyond UI-specific patterns.
- **Two open-source Claude Code skills covering similar ground** (reviewed, not adopted wholesale — kept as reference for structural ideas): [`Nuclear-Marmalade/ux-psychology-skill`](https://github.com/Nuclear-Marmalade/ux-psychology-skill) (65 principles across 11 categories, decision-first architecture with an explicit weighting hierarchy — psychology is a weighted input, never overriding brand identity or accessibility) and [`phazurlabs/ux-ui-mastery`](https://github.com/phazurlabs/ux-ui-mastery) (19 skill domains, 25+ Laws of UX with formulas, 50+ biases with ethical annotations, plus React/SwiftUI/CSS implementation code). Worth a closer look if this skill ever needs to grow into full implementation-code territory rather than staying a critique/design lens.
- **Other creators in this genre:** `uxpeak` (YouTube, the six-principle source framework), Enrico Tartarotti (YouTube, longer-form "psychology behind the design" videos), Design From Human / Rian Dutra (cognitive-science-researcher angle), Ansh Mehra's "Product Design Breakdown" YouTube playlist.
