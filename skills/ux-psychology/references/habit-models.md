# Habit-formation and engagement design frameworks

> Research digest behind `SKILL.md`, produced by one sub-agent of a six-way parallel research pass (each agent had one lane; "Agent A" through "Agent F" below refer to those lanes). Claims carry the agent's own confidence flags; verify a load-bearing one against its cited source before relying on it.


Scope: Nir Eyal's Hook Model, BJ Fogg's Behavior Model (B=MAP), and variable-reward/slot-machine psychology in digital product design. Explicitly excludes the goal-gradient effect (already covered elsewhere) and dark-pattern taxonomy (owned by agent E).

---

## 1. Nir Eyal's Hook Model ("Hooked: How to Build Habit-Forming Products," 2014)

A four-stage cycle designed to move a product from something users choose to use, to something they use without thinking — habit as a retention/growth engine ("Users Hooked" replacing paid acquisition over time).

### Stage 1 — Trigger
The spark that initiates behavior. Two types:
- **External triggers**: information in the user's environment telling them what to do next — a push notification, an email, a link, the app icon itself.
- **Internal triggers**: an emotion, routine, or situation that cues the behavior with no external prompt needed — boredom, loneliness, "FOMO," the reflex to check a phone at a red light. The goal of repeated hook cycles is to graduate a user from needing external triggers to acting on internal ones (product becomes the automatic response to a negative emotional state).

**UI example**: A red notification badge count on an app icon is the classic external trigger; over time, boredom itself becomes the internal trigger that makes a user open Instagram without any badge present.

### Stage 2 — Action
The simplest behavior performed in anticipation of a reward, executed when motivation and ability are both sufficient (this stage explicitly borrows from Fogg's model, see below). Products reduce friction here to make the action nearly automatic.

**UI example**: A single scroll gesture (infinite scroll) or a single tap to "pull to refresh" — both engineered to be the lowest-friction possible action standing between the user and a reward.

### Stage 3 — Variable Reward
An unpredictable payoff that follows the action. Predictable rewards satiate; unpredictable ones create sustained craving (see Section 3 below for the underlying mechanism). Eyal categorizes rewards into three types: rewards of the tribe (social validation), rewards of the hunt (resources/information), and rewards of the self (mastery/completion).

**UI example**: A social feed refresh where the next item might be a friend's exciting update, an ad, or nothing interesting at all — the mix of relevant and unexpected content (e.g., Pinterest interleaving expected pins with surprising ones) is deliberately variable rather than a sorted, predictable list.

### Stage 4 — Investment
The user puts something in — time, data, effort, social capital, or money — which (a) increases the odds they return, and (b) improves the product for next time, loading the next trigger. Investment stores value forward, unlike the reward stage which delivers value now.

**UI example**: Building a Spotify playlist, following boards on Pinterest, building a streak, or filling out a profile — each deposits effort that raises switching cost and personalizes the next cycle's trigger/reward.

Confidence: HIGH — model is well-documented and consistent across primary and secondary sources.

Sources:
- [The Hooked Model: How to Manufacture Desire in 4 Steps — nirandfar.com (primary source, Nir Eyal's own site)](https://www.nirandfar.com/how-to-manufacture-desire/)
- [The Hook Model: Retain Users by Creating Habit-Forming Products — Amplitude](https://amplitude.com/blog/the-hook-model)
- [Hook Model — ProductPlan glossary](https://www.productplan.com/glossary/hook-model)
- [The Hook Model of Behavioral Design — Mindtools](https://www.mindtools.com/aapqtdb/the-hook-model-of-behavioral-design/)

---

## 2. BJ Fogg's Behavior Model (B = MAP) — Stanford Behavior Design Lab (formerly Persuasive Technology Lab / "Captology")

**B = MAP**: Behavior happens when Motivation, Ability, and a Prompt converge at the same moment. Originally formalized as B=MAT (Trigger) in the early 2000s; Fogg later renamed the third element "Prompt" to reflect that real-world cues are richer than mechanical triggers.

- **Motivation**: the person's desire to do the behavior right now (core motivators: sensation/pleasure-pain, anticipation/hope-fear, social acceptance/rejection).
- **Ability**: how easy the behavior is to do given the person's time, money, physical effort, brain cycles, social deviance, and non-routineness — "simplicity factors." Fogg's key insight: it's usually easier to increase ability (remove friction) than to increase motivation, which is why "make it simple" beats "make them want it more" as a design lever.
- **Prompt**: the cue that tells the person to act at that moment — without it, motivation and ability alone don't produce behavior.

**Diagnostic use** — when a target behavior (e.g., clicking a CTA) isn't happening, the model is used as a checklist to isolate which of the three is missing or too weak:
1. **Motivation problem**: ability and prompt are present, but the person doesn't want the outcome enough right now (e.g., a well-placed, easy "Upgrade" button nobody clicks because the value isn't compelling).
2. **Ability/friction problem**: motivation and prompt are present, but the action is too hard — too many form fields, unclear next step, requires context-switching (e.g., users want to buy but abandon at a complex checkout).
3. **Missing-prompt problem**: motivation and ability are both sufficient, but there's no cue at the right moment — the CTA isn't visible when the user is ready to act, or there's no reminder at all.

This is the "new" diagnostic contribution for this section — distinct from the Hook Model's Action stage, which assumes trigger+action already exist and focuses on the reward/investment loop that follows.

Confidence: HIGH — primary source (behaviormodel.org, Fogg's own site) confirms the equation, the three elements, and the diagnostic principle ("when a behavior does not occur, at least one of the three elements is missing"). Note: the fetched primary source didn't enumerate the specific "types of prompts" (spark/facilitator/signal) in the excerpt retrieved — secondary sources (Yu-kai Chou, Growth Engineering) reference this typology but should be verified against Fogg's own materials before citing in the final skill file.

Sources:
- [Fogg Behavior Model — behaviormodel.org (Fogg's primary site)](https://www.behaviormodel.org/)
- [Fogg Behavior Model — Stanford Behavior Design Lab](https://behaviordesign.stanford.edu/resources/fogg-behavior-model)
- [BJ Fogg Behavior Model (B=MAP): The 6 Factors of Ability — Yu-kai Chou](https://yukaichou.com/behavioral-analysis/bj-fogg-extended-part-1-of-2/)
- [Fogg Behavior Model: Motivation, Ability, and Prompts — Northbeam](https://www.northbeam.io/blog/fogg-behavior-model-motivation-ability-and-prompts)

---

## 3. Variable Reward / "Slot Machine" Psychology

**Mechanism**: Rooted in B.F. Skinner's operant conditioning research on schedules of reinforcement. A *variable ratio* schedule (reward after an unpredictable number of actions) and a *variable interval* schedule (reward after an unpredictable amount of time) both produce faster-acquired, more persistent, and more extinction-resistant behavior than a *fixed* schedule where the reward is predictable. The uncertainty itself — not the reward's size — is what drives compulsive checking: dopamine in the brain's reward circuitry (ventral tegmental area) fires in anticipation of an uncertain reward, not just on receipt of it, so not-knowing keeps the behavior loop active. This is the textbook mechanism behind slot machines, and digital products deliberately mirror it.

**Concrete product examples**:
1. **Pull-to-refresh feeds** (Instagram, Twitter/X, short-video "For You" feeds): the gesture is mechanically identical to pulling a slot machine lever — a physical action produces an unpredictable payload (could be nothing interesting, could be something great), reinforcing repeated pulls.
2. **Notification badges + unpredictable content mix**: a badge signals "something happened" without saying what (likes, comments, a match, a reply) — it functions as a variable-interval trigger that provokes a variable-ratio checking behavior once opened, since the app doesn't reveal what triggered it until the user checks.
3. **Dating app matches / like counts** (e.g., Tinder-style swiping): each swipe has an unknown outcome (match or no match), and matches arrive on an unpredictable schedule — structurally identical to a slot machine's variable ratio payout, which is part of why swiping mechanics are so persistent/compulsive relative to a simple sorted list of profiles.

Confidence: HIGH on the core mechanism (well-established behavioral psychology, consistently cited across sources); MED on some of the specific neuroscience claims (VTA/dopamine-in-anticipation framing) since these come from secondary/popular-science sources rather than a single peer-reviewed citation — flag for verification if the skill file wants a rigorous citation here.

Sources:
- [Engineered highs: Reward variability and frequency as potential prerequisites of behavioural addiction — ScienceDirect (peer-reviewed)](https://www.sciencedirect.com/science/article/pii/S0306460323000217)
- [You're Being Played: Social Media's Slot Machine Techniques Revealed — Medium](https://aditimehta687.medium.com/youre-being-played-social-media-s-slot-machine-techniques-revealed-1be36fafa6c3)
- [Variable Reward Schedules: Why Slots Use Social Media Psychology — Prof. Boston](https://www.teachboston.org/variable-reward-schedules-gambling/)
- [Why Social Media Hijacks Your Brain — Variable Rewards on Tap — Feynmanpedia](https://feynmanpedia.com/dopamine-and-attention/why-social-media-hijacks-your-brain/)

---

## 4. Explicit non-overlap note

The **goal-gradient effect** (progress bars, "you're 80% done," momentum toward a finish line) is already covered elsewhere in the skill file and is NOT re-covered here. This section's "Investment" stage in the Hook Model is related but distinct: goal-gradient is about accelerating effort as a known endpoint nears; Investment is about depositing effort/data that pays off in a *future* cycle (no defined finish line — the loop is meant to repeat indefinitely). Keep these as separate mechanisms in the skill file.

## 5. Ethical tension (brief — full taxonomy owned by agent E)

The same mechanics that make a habit tracker or language-learning app "sticky" in a healthy way (Hook Model, variable reward, low-friction prompts) are structurally identical to what critics call "addictive design" — Eyal himself has faced criticism for popularizing techniques that, applied without a user-benefit constraint, shade directly into dark patterns (manufactured compulsion loops, engagement-at-all-costs notification design). The ethics/dark-patterns section (agent E) should treat habit-formation frameworks as the toolbox that dark patterns often misuse, not a separate concern.

Confidence: MED (this is an interpretive/critical framing rather than a single documented model — widely discussed but not from one authoritative source).
