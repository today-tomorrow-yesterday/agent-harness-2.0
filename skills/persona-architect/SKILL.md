---
name: persona-architect
description: Design and LOCK a consistent, photorealistic AI persona, then route to the right production skill. Owns the train-a-model identity lane (OpenArt @name, Enhancor trigger-word, Crea/Pykaso face-swap) that banana-pro-director/cinema-worldbuilder do NOT cover — the cheap (<5¢/img), drift-proof, reusable persona path for a recurring monetized influencer. Front-ends the concept/brand/brief, picks the consistency path (train vs reference) and tool, builds the reference sheet, then hands off. Use to create a new recurring AI persona, set up character training, or decide which consistency pipeline a character needs.
---

# persona-architect — design, lock, and route an AI persona

> **STATUS: TENTATIVE v0.1 (2026-05-31).** Built from a deep read of 17 roster experts'
> actual methodology files (not the summary pages, which a multi-agent audit proved are
> lossy — they miss the train-vs-reference fork, Licbe's accent-lock, product-in-hand, and
> Joey's v2 stack). Settings below are quoted from the raw expert files; they are
> **defaults to validate against visual results**, not gospel. Tre is the visual oracle:
> he generates, inspects (or I inspect via Read), and we iterate this file.

## What this skill is — and what it is NOT

This is the **front door + the training lane** of the character-skill suite. It does two jobs the existing skills don't:

1. **Persona front-end** — concept, brand, audience, voice, and the *offer it serves* — not just physical looks (the existing skills start at appearance).
2. **Train-a-model identity lock** — OpenArt `@name`, Enhancor trigger-word, Crea/Pykaso face-swap. The existing skills are **100% reference-at-generation with zero training**; this lane gives a **persistent, reusable, <5¢/image, drift-proof** persona for a channel you'll run for months.

It then **routes** the per-shot work to the skill that owns it:

| Need | Hand off to |
|---|---|
| Higgsfield image prompts (face-lock, 6-panel, scene plates, outfit) | `banana-pro-director` |
| Seedance video prompts (5 cinematography modes) | `cinema-worldbuilder` |
| Voice clone + lip-sync | *(future `voice-lipsync` skill — not built yet; manual for now)* |
| Product-in-hand UGC ads, bulk variation | *(future `ugc-ad` skill — not built yet)* |

**Does NOT** generate images (Claude can't — Tre generates, Claude inspects via Read), produce video/voice, commit to git, or duplicate banana-pro's Higgsfield prompt grammar.

## The genuine fork this skill exists to navigate

The roster's deepest split (confirmed across 17 experts): **train a model** vs **reference-at-generation**. Pick deliberately — it changes tools, cost, and durability.

| Path | What it is | Best for | Cost shape |
|---|---|---|---|
| **Reference-only** | Lock identity via a multi-angle sheet, attach as reference each gen. No training. | One-off / cinematic shots, fast prototyping | Per-image full price; identity lives only in the reference file |
| **Trained model** | Train once on a dataset, then generate cheaply by name/trigger | A **recurring monetized persona** run for months | Upfront train, then cheap-per-image; persistent identity asset |

Joey/Tao (and therefore `banana-pro-director`) only do reference-only. Dan Kieft, Dan Ko, Isa, Sirio, Yaroflasher all train. Note the whole UGC-ad cluster (Alfie/Youri/Jason/makeugc/Alex) trains *nothing* — they reuse library actors + edit-from-base.

> **DEFAULT RULE (validated 2026-05-31, the Mia build): start reference-at-generation, don't pay to train.** With Nano Banana Pro's 2026 reference-consistency and a free credit pool (e.g. Gemini Flow's ~10k credits/mo), reference-at-generation holds identity well enough to run a persona's whole feed for **$0** — proven: Mia held her face across a fresh gym scene with only the reference sheet attached. The classic training pitch (cheaper-per-image, tighter lock, type-by-name) is **largely neutralized** when generation is already free and already photographic. **Escalate to a trained model ONLY when** (1) free reference-gen credits run out, (2) drift-at-volume becomes a real problem across months, or (3) you need rock-locked identity feeding *video*. Until then, training is a paid step you don't need — and Tre hates being upsold.

## The procedure

### Stage 0 — Persona brief (concept before looks)

Interview for the full persona, not just appearance. Capture:
- **Offer-first anchor** (Dan Ko): what does this persona *sell / serve*? Design the character around the niche + offer, not the other way around. "They create a face, but they don't create a business."
- **Physical spec** — Cal Kramer's master template (fill blanks, then have an LLM expand it):
  ```
  Age: ___  Gender: ___  Ethnicity: ___  Hair: ___  Eyes: ___
  Clothing: ___  Setting: ___  Lighting: ___
  ```
- **Voice identity** — and **lock the accent explicitly** (Licbe's rule, missing from the summaries): *"mid-20s, strong California accent" — that's what locks voice consistency across clips. Be vague and the voice shifts between generations and the whole thing falls apart.*
- **Aesthetic target** — a real fork: **cinematic gloss** (Joey/Sirio/DIP) vs **deliberate amateur / feed-blend** (Licbe: "Enhanced Prompt + Amateur image style ON," "selfie, amateur photo" — the amateur look is what reads as real for influencer feeds). Pick per channel.
- **Run-length** — prototype (1 image) vs run-for-months (10–15 image trained model). Drives Stage 2.

**Gate:** the brief reads like the persona + business, and the consistency path is chosen.

### Stage 1 — Strong realistic BASE image

Identity quality is set here. *"The source image matters more than the prompting"* (Sirio); *"garbage in, garbage out"* (Dan Ko/Isa).
- **Two-shot base (validated 2026-05-31).** Generate a **full-body, white background, studio** shot so the lock grabs the *person* not the scene (Isa/Alfie; Dan Kieft: *"use a full/upper-body shot, NOT a face close-up"*) — then a **chest-up companion of the SAME person**, edited *from* the full-body ("using the exact woman in this reference, chest-up, identical face"). The full-body gives body context; the chest-up makes the face **readable** so you (and Sol) can actually verify skin, eye color, and markers before locking. Don't try to judge a face you can't see in a full-body — it'll be too small (*"a half-body reference often gives more accurate faces"* — Dan Kieft).
- **Upscale the hero first.** Isa is emphatic this is the step everyone skips and it *"influences the quality of ALL downstream generations — do not skip the upscaling"* (OpenArt "2× + Face").
- Base-model choice is itself a live disagreement — surface it, don't pretend it's settled: **Higgsfield Soul 2.0** (Alex: best for realistic people) vs **GPT Image 2** (Youri/makeugc: best skin) vs **Juggernaut XL** (Isa) vs **Nano Banana 2 / Kora** (Sirio). If on Higgsfield, hand the image prompt to `banana-pro-director` (Mode 0).

**Gate (inspect):** photographic skin (pores/peach-fuzz, not plastic), correct framing, clean background. Iterate the base before anything is built on it.

### Stage 2 — Lock identity

> **Default: reference-at-generation — NO training (per the DEFAULT RULE above).** Lock identity by attaching the reference sheet (Stage 3) to every generation with *"this exact woman, keep her face/marks identical,"* and **always edit from the locked base, never an edited image** (Alfie's anti-drift rule) — that's how you fight drift on the free path. Only drop into a trained mechanism below when one of the three escalation triggers fires. The Mia build (2026-05-31) ran entirely on this free path and held.

The trained mechanisms (escalation only):

#### 2A — OpenArt `@name` (the standard trained path — Dan Kieft, Dan Ko, Isa)
- Plan: **~$14/mo ≈ 4,000 credits** (Essential).
- Dataset: **1 image to prototype** (Isa/Dan Ko quick-start: "a 20-image attempt was worse"); **4–5 standard**; **10–25 to lock a persona for months** (Dan Ko offer-first / Sirio). Branch on the run-length from Stage 0 — this resolves Dan Ko's apparent self-contradiction (different videos, different goals).
- Upload the **upscaled hero image first**.
- **Character weight ~0.8** on the 0–1 scale (Dan Ko: *"the most important setting for consistency"*; Isa: *"the sweet spot," 0.8+ for influencers*). **NOT 1.85** — that's Dan Kieft's legacy 0–2 UI scale, the lone outlier; same optimum, different slider.
- **Prompt Adherence ~2** (higher = plasticky — Dan Ko, DIP). **Coherence ~3.5** (Dan Kieft). **Disable "Preserve Key Features"** when generating scenes (else it locks training clothes/background).
- Generate: `@name + context`, e.g. `@Scarlet is standing on a mountain peak taking a selfie`.
- **Identity-lock append (Dan Ko):** *"Maintain the exact face, expression, hair, and outfit"* — **drop the word "outfit"** to change clothes.

#### 2B — Enhancor trigger-word (the cheap-at-scale path — Sirio)
- **Contact-sheet dataset:** drop base into Nano Banana (16:9, 4K) + *"this is the same person, show her in different everyday scenarios"* → 3–4 sheets → crop frames → **10–15 training images**.
- Enhancor "Influencer" tab → set a **trigger word baking in hair/body/ID**, e.g. `Stephanie334 blonde girl` → train **15–30 min**.
- Then every prompt is **trigger + context**: `Stephanie334 blonde girl eating pasta at a restaurant, selfie, amateur photo`. Drops cost from **~30¢/image → <5¢/image at 2K**.

#### 2C — Face-swap on a trained subject (the fast/repair path — Yaroflasher, DIP)
- **Crea.ai** trained subject (Yaroflasher: *"~3 background-free faces"* despite "up to 50 recommended"), Flux model (supports inpainting), mask + apply. Or **Pykaso** face-swap on a character trained from ~30 variations (DIP). Lightweight small-face swaps: RP / Remaker.ai.

**Training dataset spec (official Higgsfield Soul-ID guide — applies to ANY trained path):** **5–20 images, 8–12 is the sweet spot.** Maximize variety across four axes — **angles** (front, ¾ left, ¾ right, slight up/down), **lighting** (indoor/outdoor/soft/harsh), **expressions** (neutral/smiling/talking — not the same face every frame), **distances** (headshot → head-and-shoulders → full body). Each: clear face, eyes visible, single person, sharp, ≥1024px. Avoid: group photos, repeated identical poses, costumes, sunglasses, hats over the face, heavy makeup she wouldn't normally wear. (This also bakes in the expression-variety rule — same lesson, official source.)

**Gate:** generate 2–3 test shots in NEW settings. Identity holds? If a trained model drifts, the dataset was too small or the base too weak — fix the input, don't max the weight (max *causes* inconsistency).

### Stage 3 — Reference sheet (the reusable asset)

Build once; everything references it. Use the path's native sheet:
- **Sirio 5-image set** (Nano Banana 2, 2K, 16:9) — verbatim micro-phrases matter: (a) multi-angle rotation board on white bg; (b) close-up headshot *"focusing on facial features"*; (c) full-body *"make sure the face is clear"*; (d) side profiles L+R; (e) feature grid (eyes, lips, nose, lashes, brows, hair).
- **Tao 8-shot single prompt** — 4 angles × (full-body + matching close-up) in 4 columns, realism keyword block **at the bottom** (`photorealistic, DSLR camera, muted color tones`); his insight: *everything downstream inherits the sheet's realism, so quality there is load-bearing.*
- **Higgsfield 6-panel** → hand to `banana-pro-director` Mode 2.

### Stage 4 — Realism finishing (defeat AI-plastic)

Root cause (Sirio): *"diffusion treats skin micro-texture as noise and smooths it out"* — corollary, *"a more plastic base is better, more room to correct."* Levers:
- **Enhancor pass** (Sirio): **Standard mode** (preserves identity), **Skin Texture start ~0.39–0.4**, **Skin Realism ~1.9–2.1**, lock mouth/lips/eyes (toggle eyes OFF on a re-run if still AI), then Portrait Upscaler. *(Caveat: these are mid-2025 starting values; the live UI may now show only Heavy Mode + a Texture slider — verify.)*
- **Repair chain** (Yaroflasher): Enhancor **Standard, not detailed** ("detailed emphasizes wrinkles") → Magnific **detail 30–50%, grain 20–30, sharpen 5–10** → upscale.
- **Keyword realism** (DIP, verbatim): *"100% human, no cartoonish look, no smooth skin texture, visible skin texture."*
- **Final cue, always** (Yaroflasher): **film grain + light color correction** in the edit — "always gives a more realistic feel."

**Gate (inspect closely):** pores + peach-fuzz, not a smooth gradient; strand hair with flyaways; real eye moisture.

### Stage 5 — Hand off

Per the routing table at top: Higgsfield stills → `banana-pro-director`; Seedance video → `cinema-worldbuilder`; voice/ads → manual until those skills exist. Keep the trained model name/trigger + the reference sheet as the persona's canonical assets.

## The iteration loop

This is a hypothesis. After each real use, Tre reports what the visual result got wrong; Sol traces it to the offending stage/setting, edits this file (and the wiki page if the wiki was wrong), re-installs to both profiles. Settings that survive visual confirmation get marked validated.

## Reversibility

Delete `Z:\agent-os\skills\persona-architect\` + the two profile copies. No other state.

## Cross-references

- `C:\Users\trerh\.claude-udig\skills\banana-pro-director\SKILL.md` — Higgsfield image lane (hand-off target)
- `C:\Users\trerh\.claude-udig\skills\cinema-worldbuilder\SKILL.md` — Seedance video lane (hand-off target)
- `Z:\Clone\research\character-skill-suite-coverage.md` — the 17-expert coverage analysis behind this design
- `Z:\Clone\techniques\character-consistency.md` · `Z:\Clone\research\ai-influencer-realism.md` · `Z:\Clone\research\prompt-library.md` — wiki sources (known-lossy; prefer the raw expert methodology files)
- `Z:\agent-os\memory\projects\ai_production_engine.md` — the goal this unblocks (channel #1 recurring persona)
- `Z:\agent-os\memory\projects\skill_forge.md` — the build→test→refine loop this is an instance of
