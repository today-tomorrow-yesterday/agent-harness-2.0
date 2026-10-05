# Cialdini's principles of influence, applied to UI/UX

> Research digest behind `SKILL.md`, produced by one sub-agent of a six-way parallel research pass (each agent had one lane; "Agent A" through "Agent F" below refer to those lanes). Claims carry the agent's own confidence flags; verify a load-bearing one against its cited source before relying on it.


Scope note: Reciprocity is already captured elsewhere in the skill (per instructions) and is
NOT re-reported here. This covers the other six of Cialdini's seven principles (six from
*Influence*, plus Unity added in *Pre-Suasion*, 2016).

Overlap flag (requested): **Scarcity is not a clean, separate mechanism from the loss-aversion /
status-quo-bias content the skill already has.** Multiple sources state scarcity's persuasive power
comes largely BECAUSE it triggers loss aversion — "scarcity is largely effective because of a
cognitive bias known as loss aversion, where people put more subjective value on loss than on
gain" (NN/g, Mind of Consumers). NN/g's own scarcity article defines the mechanism as loss
aversion. Recommendation: keep Cialdini's scarcity entry short and explicitly cross-reference the
existing loss-aversion/status-quo-bias entry rather than re-explaining the mechanism — treat
scarcity here as the *marketing/persuasion packaging* (urgency framing, exclusivity) of a
mechanism already documented, not a new one. Reactance theory and "quality inference" (limited =
must be desirable) are the parts of scarcity that are NOT just loss aversion and are worth
keeping as the differentiator.

---

## 1. Commitment & Consistency

**Mechanism:** After a small voluntary commitment, people feel internal pressure (cognitive
dissonance / self-perception) to act consistently with it, making them far more likely to agree
to larger, related requests later. Root study: Freedman & Fraser's 1966 "foot-in-the-door"
experiment — homeowners who agreed to display a small "Be a Safe Driver" sign were ~4x more
likely to later agree to a large, ugly yard billboard than those never asked first. (Source:
Cognitigence, "Commitment & Consistency Principle," https://www.cognitigence.com/blog/commitment-and-consistency-principle — HIGH; NN/g, "The Principle of Commitment and Behavioral Consistency," https://www.nngroup.com/articles/commitment-consistency-ux/ — HIGH)

**UI pattern:** Multi-step onboarding that opens with a low-effort question the user answers
about their own goals ("What are you trying to achieve?") before asking for account creation or
payment — each answered micro-step is a "micro-yes" that raises the psychological cost of
abandoning the flow later. Also: newsletter/email opt-in positioned as a small first ask that
increases later purchase likelihood (classic foot-in-the-door in e-commerce funnels). (Source:
Medium/Nudge Notes, "Consistency and Commitment: Building User Loyalty through Design,"
https://medium.com/nudge-notes/consistency-and-behavioral-consistency-building-user-loyalty-through-design-11efe8a94257 — MED; Heyflow, "What is the foot-in-the-door technique?"
https://heyflow.com/blog/foot-in-the-door-technique/ — MED)

**Dark-pattern edge:** The same source distinguishes "White Hat" commitment (user consciously
articulates their own goal, benefits from the flow) from "Black Hat" commitment (user is tricked
into a micro-yes they didn't understand the implications of — e.g., pre-checked upsells buried
inside a "quick" onboarding step — which the source notes produces churn and "class-action
lawsuits"). Ethics agent's lane for depth. (Source: Medium/Nudge Notes, same URL — MED)

---

## 2. Social Proof (Consensus)

**Mechanism:** People use others' observed behavior as a heuristic for correct behavior, which
lowers perceived decision risk under uncertainty. (Source: NN/g, "Social Proof in the User
Experience," https://www.nngroup.com/articles/social-proof-ux/ — HIGH)

**UI pattern:** Star ratings and review counts near the buy button; "customers who viewed this
also bought" modules; live-activity counters ("1,204 people bought this today" / "12 people are
looking at this right now"); follower/subscriber counts as adoption signals. (Source: NN/g, same
URL — HIGH)

**Dark-pattern edge:** NN/g flags a *backfire* risk that borders on manipulation-by-omission: low
real numbers can undermine credibility ("only 1,000 shares... wasn't popular enough"), which
pushes some teams toward fabricated or stale counters — squarely the "fake activity/social proof"
dark pattern the ethics agent will catalog. NN/g's own guidance is to test whether the number is
genuinely credibility-building before shipping it, and not to clutter the UI with proof widgets
that mislead more than inform. (Source: NN/g, same URL — HIGH)

---

## 3. Authority

**Mechanism:** People defer to perceived experts/legitimate authority — often automatically,
triggered by titles, uniforms, credentials, or symbols rather than verified expertise. (Source:
Medium/Nudge Notes, "The Authority Principle: Leveraging Expertise in Design,"
https://medium.com/nudge-notes/the-authority-principle-leveraging-expertise-in-design-e76e359f4e5d — MED; NN/g, "The Authority Principle," https://www.nngroup.com/articles/authority-principle/ — HIGH)

**UI pattern:** Trust badges near the decision point — security/payment certification logos at
checkout, "verified"/"certified" icons, professional photos + credentials (e.g., attorney profile
cards on RocketLawyer showing photos, credentials, press logos), platform-endorsement labels like
Amazon's "Amazon's Choice" / "Best Seller" tags acting as third-party stamps of approval placed
directly beside the CTA. (Source: NN/g, same URL — HIGH; search-aggregated e-commerce example,
Exnoweb "Applying Cialdini's Principles to E-Commerce Design" — MED)

**Dark-pattern edge:** NN/g's explicit test: "is it helpful and honest?" — using an authority
figure/badge unrelated to the actual claim (e.g., a celebrity endorsing an unrelated product
category), displaying expired certifications, or using client/press logos without permission
crosses into deceptive-authority territory. A 2026 aggregator source frames the bar as "defensible
in a deposition." (Source: NN/g, same URL — HIGH; search-aggregated "Authority Bias design
pattern" commentary — LOW)

---

## 4. Liking

**Mechanism:** People are more easily influenced by those they like; liking is driven by
similarity, familiarity, cooperation, association with shared values, and praise. (Source: NN/g,
"The 'Liking' Principle in User Interface Design,"
https://www.nngroup.com/articles/liking-principle-ui-design/ — HIGH)

**UI pattern:** Real photos of support/service staff near chat widgets or "meet the team"
sections to make the brand feel human rather than faceless; founder-story "About Us" pages that
build emotional connection; copy voice mirroring the target audience's own language/in-jokes
("we are one of you") to trigger similarity-based liking; friend-referral flows that leverage an
existing liked relationship (e.g., Rue La La's referral-credit system) to drive trial. (Source:
NN/g, same URL — HIGH; search-aggregated persuasive-web-design commentary — MED)

**Dark-pattern edge:** NN/g's article notably does *not* draw an ethical line here — it frames
liking purely as an effectiveness/testing question (does the imagery/voice resonate, measured via
A/B and usability testing). The manipulation risk is more subtle than the other principles:
manufactured "authenticity" (stock photos posed as real staff, fabricated founder narratives,
astroturfed similarity cues) crosses into deceptive personalization — worth a light flag for the
ethics agent even though this source doesn't name it explicitly. (Source: NN/g, same URL —
inference, LOW)

---

## 5. Scarcity

**Mechanism:** People assign higher value to things perceived as limited in quantity, time, or
access. Per NN/g and secondary sources, scarcity's persuasive force runs largely *through* loss
aversion (fear of missing out on a limited thing), plus two additional levers that are more
distinctly Cialdini's own: reactance theory (restricted access increases desire) and quality
inference (limited availability implies the item must be desirable/good). **See overlap flag
above — do not duplicate the loss-aversion entry; frame this as urgency/exclusivity packaging.**
(Source: NN/g, "Scarcity Principle in UI Design," https://www.nngroup.com/articles/scarcity-principle-ux/ — HIGH)

**UI pattern:** Countdown timers paired with stock indicators (e.g., Groupon-style deal timers);
"Only 3 left in stock" labels (Amazon's is the most widely deployed version); invitation-only /
waitlist access that manufactures exclusivity through curation rather than real capacity limits;
"early access" emails using limited-information framing. A cited study (Knishinsky) found
combining scarcity with exclusivity ("secret" framing) produced up to 6x order-size increases vs.
plain scarcity messaging alone — roughly 3x more persuasive than scarcity by itself. (Source:
NN/g, same URL — HIGH)

**Dark-pattern edge:** This is one of the most-cited dark patterns in the literature: fabricated
low-stock counts, fake countdown timers that reset on refresh, and permanent "sale ends soon"
banners. NN/g's own ethical line is truthfulness — "used in moderation and with true information"
remains persuasive without destroying trust; users who suspect fake scarcity "could go elsewhere."
An academic crawl of 11K shopping sites documented "Low-stock Message" and countdown dark
patterns at scale. (Source: NN/g, same URL — HIGH; arXiv, "Dark Patterns at Scale: Findings from
a Crawl of 11K Shopping Websites," https://arxiv.org/pdf/1907.07032 — HIGH)

---

## 6. Unity

**Mechanism:** Distinct from liking — unity is persuasion via *shared identity* ("we-ness":
family, team, community, co-creators) rather than mere similarity or affection; Cialdini added
this as a 7th principle in *Pre-Suasion* (2016) because it moved people to say yes through
group-membership framing rather than a one-off liking judgment. (Source: search-aggregated
summary of W.P. Carey News "The gentle science of persuasion, part seven: Unity,"
https://news.wpcarey.asu.edu/20250422-gentle-science-persuasion-part-seven-unity — MED; Roger
Dooley / Neuromarketing, "Unity — Robert Cialdini's New 7th Principle,"
https://www.neurosciencemarketing.com/blog/articles/cialdini-7th-unity.htm — MED)

**UI pattern:** "People like you" framing in recommendation/comparison copy (e.g., cohort-based
benchmarking: "users in your industry typically..."); co-creation/feedback flows that ask users
for "advice" on a new feature/concept rather than passive "opinions" — Cialdini's own Splash!
restaurant-concept study found asking for "advice" (a togetherness frame) produced significantly
more positive responses than asking for "opinions," because it cast the respondent as a
collaborator, not a critic; community/tribe language ("join thousands of [X] like you") in
onboarding and upgrade prompts. (Source: search-aggregated summary of Cialdini's Splash! study
via multiple secondary sources (Roger Dooley, Medium/Brady Evan Walker) — MED, underlying primary
source is *Pre-Suasion* itself, not independently re-verified here)

**Dark-pattern edge:** Manufacturing false in-group belonging (e.g., fake "community" activity,
copy that falsely implies the user already belongs to a group they haven't joined, or asking for
"feedback"/"advice" as a manipulation to extract free labor/data while implying genuine
co-ownership) is the deceptive edge here — flagged lightly for the ethics agent; not independently
sourced to a named "dark pattern" taxonomy in this research pass.

---

## Sources consulted (full list)

- NN/g, "Social Proof in the User Experience" — https://www.nngroup.com/articles/social-proof-ux/
- NN/g, "The Authority Principle" — https://www.nngroup.com/articles/authority-principle/
- NN/g, "The 'Liking' Principle in User Interface Design" — https://www.nngroup.com/articles/liking-principle-ui-design/
- NN/g, "Scarcity Principle in UI Design" — https://www.nngroup.com/articles/scarcity-principle-ux/
- NN/g, "The Principle of Commitment and Behavioral Consistency" — https://www.nngroup.com/articles/commitment-consistency-ux/
- Cognitigence, "Commitment & Consistency Principle" — https://www.cognitigence.com/blog/commitment-and-consistency-principle
- Cognitigence, "Cialdini's 7 Principles of Persuasion: Research & Practice" — https://www.cognitigence.com/blog/cialdini-7-principles-of-persuasion
- Medium/Nudge Notes, "The Authority Principle: Leveraging Expertise in Design" — https://medium.com/nudge-notes/the-authority-principle-leveraging-expertise-in-design-e76e359f4e5d
- Medium/Nudge Notes, "Consistency and Commitment: Building User Loyalty through Design" — https://medium.com/nudge-notes/consistency-and-commitment-building-user-loyalty-through-design-11efe8a94257
- Heyflow, "What is the foot-in-the-door technique?" — https://heyflow.com/blog/foot-in-the-door-technique/
- Exnoweb, "Applying Cialdini's Principles to E-Commerce Design" — https://exnoweb.com/blog/applying-cialdinis-principles-to-e-commerce-design/
- Mind of Consumers, "How Loss Aversion and Scarcity Influence Consumer Behaviour" — https://mindofconsumers.com/2025/02/18/loss-aversion-and-the-power-of-scarcity-in-consumer-behaviour/
- arXiv, "Dark Patterns at Scale: Findings from a Crawl of 11K Shopping Websites" — https://arxiv.org/pdf/1907.07032
- W.P. Carey News, "The gentle science of persuasion, part seven: Unity" — https://news.wpcarey.asu.edu/20250422-gentle-science-persuasion-part-seven-unity
- Roger Dooley / Neuromarketing, "Unity — Robert Cialdini's New 7th Principle" — https://www.neurosciencemarketing.com/blog/articles/cialdini-7th-unity.htm
- Roger Dooley, "Ep #134: Unity: Robert Cialdini's Surprising Seventh Principle" — https://www.rogerdooley.com/ep-134-unity-robert-cialdinis-surprising-seventh-principle/
- Medium/Brady Evan Walker, "Bringing it Together: Cialdini's 7th Principle of Influence" — https://medium.com/@Brady.Evan.Walker/bringing-it-together-cialdinis-7th-principle-of-influence-94128816ff67
- CXL, "How to Use Cialdini's 7 Principles of Persuasion to Boost Conversions" — https://cxl.com/blog/cialdinis-principles-persuasion/ (fetch blocked 403; used via search snippet only — LOW confidence on any claim sourced solely here)
- CXL, "Cialdini's 7th Persuasion Principle: Using Unity in Online Marketing" — https://cxl.com/blog/cialdini-unity/ (fetch blocked 403; not used as sole source for any claim)

Notes on confidence: claims backed by direct WebFetch of NN/g, Cognitigence, or arXiv are HIGH.
Claims from Medium contributor posts or aggregated search snippets are MED. The Unity section
relies more heavily on secondary paraphrase of Cialdini's own *Pre-Suasion* case studies (Splash!
restaurant, parent-survey study) rather than the primary text, so treat the *specific numbers* in
those anecdotes as MED, not HIGH, until cross-checked against the book.
