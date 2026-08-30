import playwright from "/tmp/glass-runner/node_modules/playwright/index.js";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const { chromium } = playwright;
const widths = [320, 360, 390, 430, 760, 1024, 1440, 1920];
const candidates = ["a", "b", "c"];
const out = resolve(root, "docs/evidence/glass-cockpit");
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
for (const candidate of candidates) {
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.goto(`file://${resolve(root, `truepanel/glass_cockpit/candidates/${candidate}.html`)}`);
    const measure = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      tasks: new Set([...document.querySelectorAll("[data-task]")].map(node => node.dataset.task)).size,
      minimumTarget: Math.min(...[...document.querySelectorAll("summary,button")].map(node => node.getBoundingClientRect().height)),
    }));
    if (measure.scrollWidth > measure.clientWidth) throw new Error(`${candidate}@${width}: horizontal overflow`);
    if (measure.tasks < 6) throw new Error(`${candidate}@${width}: task path missing`);
    if (measure.minimumTarget < 44) throw new Error(`${candidate}@${width}: target under 44px`);
    if ([360, 1440].includes(width)) await page.screenshot({ path: `${out}/${candidate}-${width}.png`, fullPage: true });
    results.push({ candidate: candidate.toUpperCase(), width, ...measure });
    await page.close();
  }
}
await browser.close();
await writeFile(`${out}/browser-results.json`, JSON.stringify({ widths, results }, null, 2) + "\n");
console.log(`24 responsive cases passed; screenshots and results in ${out}`);
