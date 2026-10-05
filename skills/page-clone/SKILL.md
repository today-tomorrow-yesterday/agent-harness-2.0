---
name: page-clone
description: "Capture any web page three ways — a full-page screenshot scrolled and stitched top to bottom, a self-contained .mhtml clone with every asset embedded, and the rendered DOM to refactor into code — using the system Chrome through a bundled Playwright script. Use when you need a whole page (not just the viewport) as a visual spec, want to model or tear down a reference landing page, store or funnel, or need a page's real rendered HTML/CSS. Triggers on: full page screenshot, clone this page, capture this website, page teardown"
---

# page-clone — capture and clone any web page

A scriptable, batchable replacement for a "full page screenshot" browser extension. It drives the
**system Chrome** (falling back to Edge, then Playwright's bundled Chromium) and the Chrome DevTools
Protocol, and grabs three layers of a page in one pass.

## Prerequisite (once)

The script ships in this skill directory: `page-clone.mjs` + `package.json`. It needs Node 18+ and
Playwright:

```bash
cd <your-skills-dir>/page-clone     # e.g. skills/page-clone in this repo, or the copy in your Claude config dir
npm install
# only if neither Chrome nor Edge is installed:
npx playwright install chromium
```

If `node_modules/` is missing, run the install before the first capture rather than reporting
failure.

## When to use

- A URL needs a **full-page screenshot** (the whole page, not the viewport).
- You want to **clone, model or tear down a reference page** — a landing page, store, pricing page
  or funnel step.
- You need the **real rendered HTML/CSS** of a page to rebuild it as code.
- As the capture stage inside a larger "deconstruct this page and build ours" task.

**Do NOT use** for reading a page's text for research (use a web-fetch tool — cheaper), or for
mirroring a whole multi-page site (that is `wget --mirror` / HTTrack territory; say so instead).

## How to run

```bash
node <skill-dir>/page-clone.mjs <url> [url2 ...] [--out DIR] [--width N] [--shot-only] [--html-only]
```

| Flag | Default | Meaning |
|---|---|---|
| `--out DIR` | `./captures` (current directory) | where capture folders go |
| `--width N` | `1440` | viewport width in px (use `390` for a mobile capture) |
| `--shot-only` | off | screenshot only |
| `--html-only` | off | `.mhtml` + DOM only |

If invoked with no URL, ask for the target URL(s). Several URLs in one call share one browser
launch — batch them. Exit code is non-zero if any page failed.

## What each run produces

Into `<out>/<date>_<slug>/`:

| File | What it is | Read it to… |
|---|---|---|
| `<slug>_fullpage.png` | full-page screenshot, top to bottom, stitched | **see the design** — the visual spec for a rebuild |
| `<slug>_clone.mhtml` | self-contained archive, all CSS/images/fonts embedded | open a faithful offline copy in Chrome or Edge |
| `<slug>_dom.html` | rendered HTML/DOM after scripts ran | **read the real structure** to refactor into clean code |
| `capture.json` | url, title, file paths, timestamp | metadata / chaining into the next step |

## The workflow (capture → read → deconstruct → rebuild)

When the goal is to model a page, not just grab a picture:

1. **Capture** — run the script on the target URL(s). Capture desktop (1440) and, when layout
   matters, mobile (`--width 390`) separately.
2. **Read** — open `_fullpage.png` to see the full layout, then skim `_dom.html` for section order,
   copy, and the component structure.
3. **Deconstruct** — if it is a competing offer, list its parts explicitly: promise · mechanism ·
   audience · pricing · guarantee · proof · emotional angle. Name what it does well and where its
   gaps are.
4. **Rebuild differentiated** — draft the new page around the reference's gaps. Model what works;
   never ship a 1:1 copy (that is both a legal and a positioning problem — a clone is by definition
   not better).
5. If the rebuild is frontend code, run it through whatever design review your team uses before
   showing anyone (in this repo, `ux-psychology` covers the behavioural layer of a conversion page).

## Notes and limits

- Lazy-loaded images are triggered by an auto-scroll pass before capture; the scroll is capped at
  60,000 px so an infinite-scroll page still finishes.
- Captures the **public, logged-out** view only. Pages behind a login are out of scope.
- `waitUntil: networkidle` falls back to `domcontentloaded` for pages that never go idle (chat
  widgets, analytics beacons). If a capture looks half-rendered, re-run — do not guess.
- A very tall PNG (10,000+ px) or a large DOM costs a lot of context to read. Use `--shot-only` or
  `--html-only` when you need one layer, and read only the sections the task needs.
- `.mhtml` is a Chromium format; Firefox and Safari will not open it.
- Respect the target site's terms of service and robots rules; this is for studying public pages,
  not scraping data at volume.
