import { readFile, mkdir, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const playwrightRoot = process.env.PLAYWRIGHT_ROOT;
if (!playwrightRoot) throw new Error("PLAYWRIGHT_ROOT is required");
const playwright = await import(pathToFileURL(resolve(playwrightRoot, "node_modules/playwright/index.js")));
const { chromium } = playwright.default;
const root = process.cwd();
const widths = [320, 360, 390, 430, 760, 1024, 1440];
const out = resolve(root, "docs/evidence/aegis-ground-truth-ui");
await mkdir(out, { recursive: true });

const html = await readFile(resolve(root, "truepanel/web/static/index.html"), "utf8");
const cockpitPolish = resolve(root, "truepanel/web/static/cockpit-polish.js");
const reliabilityView = resolve(root, "truepanel/web/static/reliability-view.js");
const payload = {
  health: {
    state: "CRITICAL",
    subsystems: {
      cooling: { state: "NOMINAL" },
      thermal: { state: "ATTENTION" },
      storage: { state: "CRITICAL" },
      network: { state: "UNKNOWN" },
      front_panel: { state: "NOMINAL" },
      services: { state: "DEGRADED" },
    },
  },
  reliability: {
    active_incident: {
      incident_id: "recovery:browser-fixture",
      likely_cause: "Critical drive-health evidence detected",
      hypothesis: "Raw SMART evidence conflicts with a nominal pool state.",
      confidence: 0.62,
      safest_next_action: "Keep the drive installed while evidence remains on HOLD.",
      verification_state: "pending",
      supporting_signals: [{ source: "AEGIS", signal: "storage.smart_warning", state: "diagnosing" }],
    },
    coverage_summary: { total: 8, trusted: 8, gaps: 0 },
    coverage_matrix: { entries: [] },
    correlation_policy: { policy_id: "aegis-declarative-correlation-v1", semantics: "evidence grouping" },
    flight_director: {
      scenario: "storage-smart-recovery-v1",
      presentation_scope: "active_incident",
      applies_to_active_incident: true,
      incident_id: "recovery:browser-fixture",
      domain: "storage",
      identity: { bay: 3, device: "sda", model: "ST8000NE001", serial_last4: "MW6D", verified_from_passive_evidence: true },
      topology: { pool: "HDDs", vdev: "raidz1-0", vdev_topology: "RAIDZ1", remaining_redundancy: 1, zfs_state: "ONLINE" },
      action_gate: { blocked_by: ["provider_attestation_integrity"] },
      verification_signature: { status: "awaiting_external_repair" },
      evidence: { reallocated: 16120, pending: 1608, offline_uncorrectable: 1608 },
      backup_context: { independent_backup_confirmed: true },
      safest_action: "Keep bay 3 installed until ground-truth evidence is complete.",
      abort_conditions: ["Stop if identity changes."],
      rehearsals: [],
      evidence_sha256: "d".repeat(64),
      pre_service_clearance: {
        status: "HOLD",
        expires_after_seconds: 900,
        receipt_sha256: "e".repeat(64),
        gates: [{ code: "provider_attestation_integrity", satisfied: false, detail: "Provider evidence is incomplete." }],
        evidence_ledger: {
          status: "HOLD",
          accepted: [{ kind: "backup.restore-verification", provider: { id: "fixture.restore-verifier", mode: "deterministic_fixture" } }],
          rejected: [{ kind: "storage.replacement-candidate", errors: ["candidate identity is not strongly distinct"] }],
          missing_kinds: ["storage.replacement-candidate"],
          evidence_maturity: "deterministic_lab_fixture",
          ledger_sha256: "f".repeat(64),
        },
      },
    },
  },
};

const browser = await chromium.launch({ headless: true });
const results = [];
for (const width of widths) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } });
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.addScriptTag({ path: cockpitPolish });
  await page.addScriptTag({ path: reliabilityView });
  await page.evaluate(status => window.dispatchEvent(new CustomEvent("truepanel:status", { detail: status })), payload);
  await page.waitForSelector(".fd-attestations");
  const measure = await page.evaluate(() => {
    const annunciators = [...document.querySelectorAll(".gc-annunciator")];
    const states = annunciators.map(node => node.querySelector(".gc-annunciator-state")?.textContent);
    const boxes = annunciators.map(node => node.getBoundingClientRect());
    const ground = document.querySelector(".fd-attestations")?.getBoundingClientRect();
    return {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      annunciatorOrder: annunciators.map(node => node.dataset.gcHealthTarget),
      visibleStates: states,
      minimumAnnunciatorHeight: Math.min(...boxes.map(box => box.height)),
      annunciatorsInsideViewport: boxes.every(box => box.left >= 0 && box.right <= window.innerWidth),
      groundTruthInsideViewport: Boolean(ground && ground.left >= 0 && ground.right <= window.innerWidth),
      groundTruthDisclosure: document.querySelector(".fd-attestations")?.textContent.includes("digest authenticates provider: NO") || false,
    };
  });
  if (measure.scrollWidth > measure.clientWidth) throw new Error(`${width}: page overflow`);
  if (!measure.annunciatorsInsideViewport) throw new Error(`${width}: hidden annunciator`);
  if (!measure.groundTruthInsideViewport) throw new Error(`${width}: ground-truth panel overflow`);
  if (measure.minimumAnnunciatorHeight < 44) throw new Error(`${width}: touch target under 44px`);
  if (!measure.visibleStates.every(Boolean)) throw new Error(`${width}: color-only state`);
  if (measure.annunciatorOrder[0] !== "storage") throw new Error(`${width}: critical state is not first`);
  if (!measure.groundTruthDisclosure) throw new Error(`${width}: integrity disclosure missing`);
  if ([360, 1440].includes(width)) await page.screenshot({ path: `${out}/mission-control-${width}.png`, fullPage: true });
  results.push({ width, ...measure });
  await page.close();
}
await browser.close();
await writeFile(`${out}/browser-results.json`, JSON.stringify({ widths, results }, null, 2) + "\n");
console.log(`${results.length} responsive Mission Control cases passed`);
