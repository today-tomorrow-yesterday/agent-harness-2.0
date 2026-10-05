#!/usr/bin/env node
/**
 * page-clone — capture a web page three ways, scriptable and batchable.
 *
 *   node page-clone.mjs <url> [url2 ...] [--out DIR] [--width N] [--shot-only] [--html-only]
 *
 * Per URL it writes (into <out>/<date>_<slug>/):
 *   <slug>_fullpage.png  — full-page screenshot (scrolled top to bottom, stitched)
 *   <slug>_clone.mhtml   — self-contained archive (CSS/images/fonts embedded), opens in Chrome/Edge
 *   <slug>_dom.html      — rendered HTML/DOM (the structure to refactor into code)
 *   capture.json         — metadata (url, title, paths, timestamp)
 *
 * Browser: prefers the system Chrome, then Edge (Playwright "channel"), so nothing has to be
 * downloaded. If neither is installed it falls back to Playwright's bundled Chromium, which
 * needs `npx playwright install chromium` once.
 *
 * Requires: Node 18+ and `npm install` in this directory (installs playwright).
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const USAGE =
  "usage: node page-clone.mjs <url> [url2 ...] [--out DIR] [--width N] [--shot-only] [--html-only]";

// ---- args ----
const argv = process.argv.slice(2);
const urls = [];
let outDir = resolve(process.cwd(), "captures");
let width = 1440;
let shotOnly = false;
let htmlOnly = false;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--out") outDir = resolve(argv[++i]);
  else if (a === "--width") width = parseInt(argv[++i], 10) || 1440;
  else if (a === "--shot-only") shotOnly = true;
  else if (a === "--html-only") htmlOnly = true;
  else if (a === "-h" || a === "--help") { console.log(USAGE); process.exit(0); }
  else if (a.startsWith("--")) console.warn(`(ignoring unknown flag ${a})`);
  else urls.push(a);
}
if (urls.length === 0) {
  console.error(USAGE);
  process.exit(1);
}
if (shotOnly && htmlOnly) {
  console.error("--shot-only and --html-only together would capture nothing");
  process.exit(1);
}

const today = new Date().toISOString().slice(0, 10);
const slugify = (u) => {
  try {
    const x = new URL(u);
    return (x.hostname + x.pathname)
      .replace(/^www\./, "")
      .replace(/[^a-z0-9]+/gi, "-")
      .replace(/-+$/g, "")
      .slice(0, 80)
      .toLowerCase();
  } catch {
    return "page";
  }
};

async function autoScroll(page) {
  // Trigger lazy-loaded images, then return to the top so the stitch is complete.
  // Capped, because an infinite-scroll page would otherwise never finish.
  await page.evaluate(async () => {
    await new Promise((res) => {
      let y = 0;
      const step = 600;
      const maxY = 60000;
      const t = setInterval(() => {
        window.scrollBy(0, step);
        y += step;
        if (y >= document.body.scrollHeight || y >= maxY) {
          clearInterval(t);
          res();
        }
      }, 80);
    });
  });
  await page.waitForTimeout(600);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
}

async function launch() {
  for (const channel of ["chrome", "msedge"]) {
    try {
      return await chromium.launch({ channel });
    } catch {
      /* not installed — try the next one */
    }
  }
  return chromium.launch(); // bundled Chromium
}

const browser = await launch();
const results = [];
for (const url of urls) {
  const slug = slugify(url);
  const folder = join(outDir, `${today}_${slug}`);
  mkdirSync(folder, { recursive: true });
  const rec = { url, slug, folder };
  console.log(`\n> ${url}`);
  try {
    const ctx = await browser.newContext({ viewport: { width, height: 1000 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page
      .goto(url, { waitUntil: "networkidle", timeout: 60000 })
      .catch(() => page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 }));
    rec.title = await page.title().catch(() => "");
    await autoScroll(page);
    if (!htmlOnly) {
      const pngPath = join(folder, `${slug}_fullpage.png`);
      await page.screenshot({ path: pngPath, fullPage: true });
      rec.screenshot = pngPath;
      console.log(`  ok screenshot -> ${pngPath}`);
    }
    if (!shotOnly) {
      // Self-contained archive via the Chrome DevTools Protocol (all resources embedded).
      try {
        const client = await ctx.newCDPSession(page);
        const { data } = await client.send("Page.captureSnapshot", { format: "mhtml" });
        const mhtmlPath = join(folder, `${slug}_clone.mhtml`);
        writeFileSync(mhtmlPath, data);
        rec.mhtml = mhtmlPath;
        console.log(`  ok self-contained clone -> ${mhtmlPath}`);
      } catch (e) {
        rec.mhtmlError = String(e);
        console.log(`  FAILED mhtml: ${rec.mhtmlError.slice(0, 160)}`);
      }
      // Rendered DOM (raw HTML structure for refactoring into code).
      const domPath = join(folder, `${slug}_dom.html`);
      writeFileSync(domPath, await page.content());
      rec.dom = domPath;
      console.log(`  ok rendered DOM -> ${domPath}`);
    }
    await ctx.close();
    writeFileSync(
      join(folder, "capture.json"),
      JSON.stringify({ ...rec, captured: new Date().toISOString() }, null, 2),
    );
  } catch (e) {
    rec.error = String(e);
    console.log(`  FAILED: ${rec.error.slice(0, 200)}`);
  }
  results.push(rec);
}
await browser.close();

const ok = results.filter((r) => !r.error).length;
console.log(`\ndone: ${ok}/${results.length} pages captured -> ${outDir}`);
process.exit(ok === results.length ? 0 : 1);
