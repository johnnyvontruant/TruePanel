/*
 * Flightdeck skin — TruePanel's "Faceplate x Cockpit" presentation layer.
 *
 * Why this lives in its own injected script:
 *   - It is presentation only. It never changes a DOM id, never rewrites the
 *     text of a telemetry element, and never calls an API.
 *   - Every companion script injects its own <style> at runtime. This file
 *     keeps its stylesheet LAST in <head> so the skin wins consistently.
 *   - Rollback is one query string: ?skin=classic (remembered per browser);
 *     ?skin=flightdeck turns it back on. Removing the injection marker in
 *     pathfinder_server.py removes the skin entirely.
 *
 * Design rules (see docs/FLIGHTDECK_SKIN.md):
 *   red = warning (act now), amber = caution (you need to know),
 *   cyan = things you can select or act on, white/ink = labels and info,
 *   green = a system actively working (never just "fine"),
 *   magenta = target values. No light = normal.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "truepanel-skin";
  const root = document.documentElement;

  function chosenSkin() {
    let requested = null;
    try {
      requested = new URLSearchParams(window.location.search).get("skin");
    } catch (error) {
      requested = null;
    }
    if (requested === "classic" || requested === "flightdeck") {
      try {
        localStorage.setItem(STORAGE_KEY, requested);
      } catch (error) {
        /* storage can be unavailable; the query string still applies */
      }
      return requested;
    }
    try {
      return localStorage.getItem(STORAGE_KEY) || "flightdeck";
    } catch (error) {
      return "flightdeck";
    }
  }

  if (chosenSkin() === "classic") {
    return;
  }

  root.dataset.skin = "flightdeck";

  /* ------------------------------------------------------------------ */
  /* Stylesheet                                                          */
  /* ------------------------------------------------------------------ */

  const FONT_FACES = [
    ["Barlow Condensed", 600, "barlow-condensed-latin-600-normal"],
    ["Barlow Condensed", 700, "barlow-condensed-latin-700-normal"],
    ["Chivo", 400, "chivo-latin-400-normal"],
    ["Chivo", 700, "chivo-latin-700-normal"],
    ["Chivo", 800, "chivo-latin-800-normal"],
    ["Chivo Mono", 400, "chivo-mono-latin-400-normal"],
    ["Chivo Mono", 600, "chivo-mono-latin-600-normal"],
    ["Chivo Mono", 700, "chivo-mono-latin-700-normal"],
  ]
    .map(
      ([family, weight, file]) =>
        `@font-face{font-family:"${family}";font-style:normal;font-weight:${weight};font-display:swap;src:url("/fonts/${file}.woff2") format("woff2")}`
    )
    .join("");

  const S = 'html[data-skin="flightdeck"]';

  // Day lighting = the light theme, Night lighting = the dark theme. The
  // existing theme toggle, its localStorage key and the bootstrap script all
  // keep working unchanged.
  const DAY = `
    --bg:#BDBAB2;--bg-gradient-a:#BDBAB2;--bg-gradient-b:#BDBAB2;
    --panel:#D6D4CE;--panel-solid:#D6D4CE;
    --edge:rgba(26,26,24,.16);--edge-strong:rgba(26,26,24,.30);
    --text:#1A1A18;--muted:#4D4B46;--muted2:#5E5B55;
    --accent:#0A5F73;--accent-soft:rgba(10,95,115,.14);
    --good:#1A1A18;--good-soft:rgba(26,26,24,.06);
    --warn:#7A4F00;--warn-soft:rgba(255,176,0,.22);
    --bad:#9A2018;--bad-soft:rgba(224,42,31,.16);
    --shadow:0 8px 18px rgba(40,38,34,.14);--shadow-lg:0 8px 18px rgba(40,38,34,.14);
    --blur:none;--radius:14px;--radius-sm:8px;
    --font:"Chivo",system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:"Chivo Mono","SF Mono",Menlo,Consolas,monospace;
    --fd-placard:"Barlow Condensed","Arial Narrow",sans-serif;
    --fd-hi:#EEECE6;--fd-lo:#A8A59D;
    --fd-key:#E6E4DE;--fd-key-shadow:#9E9B93;--fd-key-text:#1A1A18;
    --fd-dark-key:#2C2B29;--fd-dark-key-shadow:#121110;
    --fd-lens-off:#C4C1BA;--fd-lens-legend:#4D4B46;--fd-lamp-off:#A8A59D;
    --fd-well:#C9C6BF;
    --fd-sel:#0A5F73;--fd-sel-bg:#BFE3EA;
    --fd-active:#17603A;
    --fd-screw-a:#EDEBE5;--fd-screw-b:#8F8C85;
    --fd-chassis:#2C2B29;
  `;

  const NIGHT = `
    --bg:#121211;--bg-gradient-a:#121211;--bg-gradient-b:#121211;
    --panel:#2B2A28;--panel-solid:#2B2A28;
    --edge:rgba(228,225,217,.12);--edge-strong:rgba(228,225,217,.24);
    --text:#E4E1D9;--muted:#A9A69E;--muted2:#8E8B84;
    --accent:#35D0E8;--accent-soft:rgba(53,208,232,.16);
    --good:#E4E1D9;--good-soft:rgba(228,225,217,.06);
    --warn:#FFB000;--warn-soft:rgba(255,176,0,.16);
    --bad:#FF6A5C;--bad-soft:rgba(255,68,56,.18);
    --shadow:0 8px 20px rgba(0,0,0,.45);--shadow-lg:0 8px 20px rgba(0,0,0,.45);
    --fd-hi:#3A3936;--fd-lo:#121110;
    --fd-key:#3A3936;--fd-key-shadow:#121110;--fd-key-text:#E4E1D9;
    --fd-dark-key:#121110;--fd-dark-key-shadow:#000000;
    --fd-lens-off:#1E1D1B;--fd-lens-legend:#A9A69E;--fd-lamp-off:#3A3936;
    --fd-well:#1E1D1B;
    --fd-sel:#35D0E8;--fd-sel-bg:#0E2A30;
    --fd-active:#3DDC84;
    --fd-screw-a:#5A5853;--fd-screw-b:#1E1D1B;
    --fd-chassis:#1E1D1B;
  `;

  const CSS = `${FONT_FACES}
${S}{${DAY}
  --fd-amber:#FFB000;--fd-amber-edge:#9A6A00;--fd-red:#E02A1F;--fd-red-edge:#7A1209;
  --fd-glass:#0B0D0E;--fd-glass-text:#E8EAE6;--fd-glass-muted:#9AA0A0;
  --fd-cyan:#35D0E8;--fd-green:#3DDC84;--fd-magenta:#E86BFF;--fd-glass-amber:#FFB000;--fd-glass-red:#FF4438;
}
${S}[data-theme="dark"]{${NIGHT}}
@media (prefers-color-scheme: dark){${S}:not([data-theme="light"]){${NIGHT}}}

/* ---- surfaces: flat enclosure, no glass, no mesh ---- */
${S} *,${S} *::before,${S} *::after{backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
${S} body{background:var(--bg)!important;background-image:none!important;font-family:var(--font)}
${S} a{color:var(--accent)}

/* ---- panels: every card is a screwed-in, replaceable module ---- */
${S} .card{
  background:var(--panel-solid)!important;border:0!important;border-radius:var(--radius)!important;
  box-shadow:inset 0 1px 0 var(--fd-hi),inset 0 -2px 0 var(--fd-lo),var(--shadow)!important;
  padding:1.55rem 1.65rem!important;
}
${S} .card::before{display:none!important}
${S} .card:hover{box-shadow:inset 0 1px 0 var(--fd-hi),inset 0 -2px 0 var(--fd-lo),var(--shadow)!important}
${S} .card h2,${S} .section-head h2{
  font-family:var(--fd-placard)!important;font-weight:700!important;text-transform:uppercase;
  letter-spacing:.16em!important;font-size:1rem!important;color:var(--text)!important;
}
${S} .card h3{font-family:var(--fd-placard);font-weight:700;letter-spacing:.14em;text-transform:uppercase}
${S} .label,${S} .detail{font-family:var(--font)}
${S} .metric,${S} .value,${S} code,${S} pre{font-family:var(--mono);font-variant-numeric:tabular-nums}
${S} .metric{font-weight:600;letter-spacing:0}

/* ---- screws: decorative, aria-hidden, never block clicks ---- */
${S} fd-screw{
  position:absolute;z-index:2;width:11px;height:11px;border-radius:50%;pointer-events:none;
  background:
    linear-gradient(var(--fd-slot,25deg),transparent 42%,rgba(0,0,0,.55) 42% 58%,transparent 58%),
    radial-gradient(circle at 35% 35%,var(--fd-screw-a),var(--fd-screw-b));
  box-shadow:0 1px 0 rgba(255,255,255,.18),inset 0 0 0 1px rgba(0,0,0,.28);
}
${S} fd-screw[data-at="tl"]{top:7px;left:7px}
${S} fd-screw[data-at="tr"]{top:7px;right:7px}
${S} fd-screw[data-at="bl"]{bottom:7px;left:7px}
${S} fd-screw[data-at="br"]{bottom:7px;right:7px}
@media print{${S} fd-screw{display:none}}

/* ---- top bar: the instrument panel header ---- */
${S} .topbar{
  background:var(--panel-solid)!important;border-bottom:0!important;
  box-shadow:inset 0 -2px 0 var(--fd-lo),0 4px 12px rgba(0,0,0,.18);padding:.9rem 1.6rem!important;
}
${S} .topbar-title h1{font-family:var(--font);font-weight:800;font-size:1.3rem;letter-spacing:-.01em}
${S} .topbar-title .sub{font-family:var(--mono);font-size:.76rem;color:var(--muted)}
${S} .badge{
  border:0!important;border-radius:6px!important;background:var(--fd-lens-off)!important;color:var(--text)!important;
  font-family:var(--fd-placard);font-weight:700;letter-spacing:.14em;text-transform:uppercase;font-size:.82rem;
  min-height:40px;padding:.35rem .8rem;box-shadow:inset 0 2px 5px rgba(0,0,0,.18);
}
${S} .badge::before{background:var(--fd-active)!important;box-shadow:0 0 8px var(--fd-active)!important}
${S} .badge.bad::before{background:var(--fd-red)!important;box-shadow:0 0 8px var(--fd-red)!important}
${S} #themeToggle{width:auto!important;height:auto!important;min-height:44px;border-radius:6px!important;padding:0 .9rem!important}
${S} #themeToggle .theme-emoji-light,${S} #themeToggle .theme-emoji-dark{display:none!important}
${S} #themeToggle::before{content:"LIGHTING \\00B7  DAY"}
${S}[data-theme="dark"] #themeToggle::before{content:"LIGHTING \\00B7  NIGHT"}
@media (prefers-color-scheme: dark){${S}:not([data-theme="light"]) #themeToggle::before{content:"LIGHTING \\00B7  NIGHT"}}

/* ---- keys: every button is a raised physical key ---- */
${S} button,${S} .button-link,${S} .icon-btn{
  border:0!important;border-radius:6px!important;background:var(--fd-key)!important;color:var(--fd-key-text)!important;
  font-family:var(--fd-placard)!important;font-weight:600!important;letter-spacing:.1em;text-transform:uppercase;
  font-size:.92rem!important;min-height:44px;
  box-shadow:0 3px 0 var(--fd-key-shadow),0 4px 6px rgba(0,0,0,.14)!important;
  transition:transform .06s ease,box-shadow .06s ease!important;
}
${S} button:hover:not(:disabled),${S} .button-link:hover{filter:brightness(1.04)}
${S} button:active:not(:disabled),${S} button.pressed,${S} .button-link:active{
  transform:translateY(2px)!important;box-shadow:0 1px 0 var(--fd-key-shadow)!important;
}
${S} button.primary{
  background:var(--fd-sel-bg)!important;color:var(--fd-sel)!important;
  box-shadow:inset 0 0 0 1.5px var(--fd-sel),0 3px 0 var(--fd-key-shadow)!important;
}
${S} button.danger{color:var(--bad)!important}
${S} button:disabled{opacity:.45!important}
${S} button[aria-pressed="true"],${S} button.active,${S} button.selected{
  background:var(--fd-sel-bg)!important;color:var(--fd-sel)!important;transform:translateY(2px);
  box-shadow:inset 0 0 0 1.5px var(--fd-sel),0 1px 0 var(--fd-key-shadow)!important;
}
${S} :focus-visible{outline:3px solid var(--fd-cyan)!important;outline-offset:3px!important}
${S} input[type=number],${S} input[type=text],${S} select,${S} textarea{
  background:var(--fd-well)!important;border:0!important;border-radius:6px!important;color:var(--text)!important;
  font-family:var(--mono);box-shadow:inset 0 2px 4px rgba(0,0,0,.2)!important;
}

/* ---- annunciators: dark = normal, lit = needs you ---- */
${S} .health-subsystem,${S} .gc-annunciator{
  border:0!important;border-radius:8px!important;background:var(--fd-lens-off)!important;
  box-shadow:0 4px 0 var(--fd-key-shadow),inset 0 2px 5px rgba(0,0,0,.15)!important;color:var(--fd-lens-legend)!important;
}
${S} .health-subsystem .health-name,${S} .gc-annunciator{font-family:var(--fd-placard)!important;font-weight:700!important;letter-spacing:.14em!important}
${S} .health-subsystem .health-name{font-size:.86rem!important;color:inherit!important}
${S} .health-subsystem strong,${S} .gc-annunciator-state{font-family:var(--mono)!important;font-weight:600!important;color:inherit!important;letter-spacing:.02em}
${S} .health-subsystem .health-dot,${S} .gc-annunciator-dot{background:var(--fd-lamp-off)!important;box-shadow:inset 0 1px 2px rgba(0,0,0,.35)!important}
${S} .health-subsystem.attention,${S} .gc-annunciator.attention{
  background:var(--fd-amber)!important;color:#1B1D1F!important;transform:translateY(3px);
  box-shadow:0 1px 0 var(--fd-amber-edge),0 0 16px rgba(255,176,0,.35)!important;
}
${S} .health-subsystem.degraded,${S} .health-subsystem.critical,${S} .gc-annunciator.degraded,${S} .gc-annunciator.critical{
  background:var(--fd-red)!important;color:#FFFFFF!important;transform:translateY(3px);
  box-shadow:0 1px 0 var(--fd-red-edge),0 0 16px rgba(255,68,56,.4)!important;
}
${S} .health-subsystem.attention .health-dot,${S} .gc-annunciator.attention .gc-annunciator-dot{background:#1B1D1F!important}
${S} .health-subsystem.degraded .health-dot,${S} .health-subsystem.critical .health-dot,
${S} .gc-annunciator.degraded .gc-annunciator-dot,${S} .gc-annunciator.critical .gc-annunciator-dot{background:#FFFFFF!important}
${S} .health-command{background:var(--panel-solid)!important}
${S} .health-overall{font-family:var(--fd-placard);font-weight:700;letter-spacing:.06em;text-transform:uppercase}
${S} .health-overall.nominal{color:var(--text)!important}

/* ---- master warning / caution (glareshield) ---- */
${S} .fd-glareshield{display:flex;gap:.6rem;align-items:stretch}
${S} .fd-master{
  display:flex!important;flex-direction:column;align-items:center;justify-content:center;gap:1px;
  min-width:92px;min-height:52px!important;padding:.3rem .6rem!important;line-height:1.05;
  font-weight:700!important;font-size:.8rem!important;letter-spacing:.14em;
  background:var(--fd-lens-off)!important;color:var(--fd-lens-legend)!important;
  box-shadow:0 4px 0 var(--fd-key-shadow),inset 0 2px 6px rgba(0,0,0,.18)!important;
}
${S} .fd-master[data-lit="true"][data-kind="warning"]{
  background:var(--fd-red)!important;color:#FFFFFF!important;transform:translateY(3px);
  box-shadow:0 1px 0 var(--fd-red-edge),0 0 18px rgba(255,68,56,.45)!important;
}
${S} .fd-master[data-lit="true"][data-kind="caution"]{
  background:var(--fd-amber)!important;color:#1B1D1F!important;transform:translateY(3px);
  box-shadow:0 1px 0 var(--fd-amber-edge),0 0 18px rgba(255,176,0,.4)!important;
}
@media (max-width:760px){${S} .fd-glareshield{order:5;width:100%}${S} .fd-master{flex:1 1 0}}

/* ---- fault advisory: an avionics display set into the panel ---- */
${S} .health-advisory{
  background:var(--fd-glass)!important;color:var(--fd-glass-text)!important;
  box-shadow:inset 0 0 0 6px var(--panel-solid),inset 0 0 0 7px var(--fd-lo),inset 0 0 24px rgba(0,0,0,.9)!important;
  padding:1.8rem 2rem!important;
}
${S} .health-advisory-label{font-family:var(--mono)!important;color:var(--fd-glass-amber)!important;font-weight:700;letter-spacing:.08em}
${S} .health-advisory.critical .health-advisory-label,${S} .health-advisory.degraded .health-advisory-label{color:var(--fd-glass-red)!important}
${S} .health-advisory-summary{font-family:var(--font);font-weight:700;font-size:1.25rem!important;color:var(--fd-glass-text)!important}
${S} .health-advisory-reason{color:var(--fd-glass-muted)!important}
${S} .health-advisory-action{color:var(--fd-cyan)!important;font-family:var(--mono)}

/* ---- virtual front panel: the LCD stays exactly as the hardware ---- */
${S} .lcd-faceplate{
  background:var(--panel-solid)!important;border:0!important;
  box-shadow:inset 0 1px 0 var(--fd-hi),inset 0 -2px 0 var(--fd-lo)!important;position:relative;
}
${S} .lcd-rocker{
  display:flex!important;flex-direction:column;align-items:center;justify-content:center;gap:.25rem;
  min-height:72px!important;background:var(--fd-dark-key)!important;color:#E8E6E0!important;
  box-shadow:0 5px 0 var(--fd-dark-key-shadow),0 7px 10px rgba(0,0,0,.25)!important;
}
${S} #virtualLcdSelect.lcd-rocker{background:var(--fd-key)!important;color:var(--fd-key-text)!important;box-shadow:0 5px 0 var(--fd-key-shadow),0 7px 10px rgba(0,0,0,.2)!important}
${S} .lcd-rocker:active:not(:disabled),${S} .lcd-rocker.pressed{transform:translateY(3px)!important;box-shadow:0 2px 0 var(--fd-dark-key-shadow)!important}
${S} .lcd-rocker:disabled{opacity:.62!important}
${S} .fd-key-glyph{display:block;width:22px;height:14px}
${S} .fd-key-legend{font-family:var(--fd-placard);font-weight:700;letter-spacing:.16em;font-size:.86rem}
${S} .lcd-rocker[data-fd-mode="eject"] .fd-key-legend{color:var(--fd-amber)}
${S} .lcd-transport{background:var(--fd-well)!important;border:0!important;box-shadow:inset 0 2px 4px rgba(0,0,0,.18)}
${S} .lcd-state-dot{box-shadow:none!important}
${S} .lcd-state-dot:not(.stale):not(.offline){background:var(--fd-active)!important}
${S} .lcd-state-dot.stale{background:var(--fd-amber)!important}
${S} .lcd-state-dot.offline{background:var(--fd-red)!important}

/* ---- gauges and readouts ---- */
${S} .fan-gauge{background:var(--fd-well)!important;border-radius:2px!important}
${S} .cooling-instrument,${S} .cooling-fans,${S} .diagnostics-drawer,${S} .gc-now>div,${S} .gc-domains section{
  background:var(--fd-well)!important;border:0!important;border-radius:8px!important;
  box-shadow:inset 0 2px 4px rgba(0,0,0,.16)!important;
}
${S} .cooling-instrument .label,${S} .gc-now small,${S} .gc-domains small{font-family:var(--fd-placard)!important;font-weight:700;letter-spacing:.14em}
${S} .row{border-bottom-color:var(--edge)!important}

/* ---- friendly fault view (fault-view.js) ---- */
${S} .ff-hero,${S} .ff-card{
  background:var(--panel-solid)!important;border:0!important;border-radius:var(--radius)!important;
  box-shadow:inset 0 1px 0 var(--fd-hi),inset 0 -2px 0 var(--fd-lo),var(--shadow)!important;
}
${S} .ff-card{padding:1.55rem 1.65rem!important}
${S} .ff-card-title{font-family:var(--fd-placard);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:1.05rem!important}
${S} .ff-tile strong{font-family:var(--mono);font-weight:600}
${S} .ff-kicker{font-family:var(--fd-placard);font-weight:700;letter-spacing:.16em}
${S} .ff-hero.ff-good .ff-hero-icon{background:var(--fd-lens-off)!important;color:var(--text)!important}
${S} .ff-hero.ff-good .ff-kicker{color:var(--muted)!important}
/* a fault turns the hero into an avionics display set into the panel */
${S} .ff-hero.ff-warn,${S} .ff-hero.ff-bad{
  background:var(--fd-glass)!important;color:var(--fd-glass-text)!important;padding:2rem 2.1rem!important;
  box-shadow:inset 0 0 0 6px var(--panel-solid),inset 0 0 0 7px var(--fd-lo),inset 0 0 28px rgba(0,0,0,.9)!important;
}
${S} .ff-hero.ff-warn .ff-hero-text h2,${S} .ff-hero.ff-bad .ff-hero-text h2,
${S} .ff-hero.ff-warn .ff-hero-text p,${S} .ff-hero.ff-bad .ff-hero-text p{color:var(--fd-glass-text)!important;opacity:1}
${S} .ff-hero.ff-warn .ff-hero-cta span,${S} .ff-hero.ff-bad .ff-hero-cta span,
${S} .ff-hero.ff-warn .ff-hero-foot,${S} .ff-hero.ff-bad .ff-hero-foot{color:var(--fd-glass-muted)!important}
${S} .ff-hero.ff-warn .ff-kicker{color:var(--fd-glass-amber)!important;font-family:var(--mono)}
${S} .ff-hero.ff-bad .ff-kicker{color:var(--fd-glass-red)!important;font-family:var(--mono)}
${S} .ff-hero.ff-warn .ff-hero-icon{background:var(--fd-amber)!important;color:#1B1D1F!important;border-radius:8px!important}
${S} .ff-hero.ff-bad .ff-hero-icon{background:var(--fd-red)!important;color:#FFFFFF!important;border-radius:8px!important}
${S} .ff-step{border:0!important;border-radius:8px!important;background:var(--fd-well)!important;box-shadow:inset 0 2px 4px rgba(0,0,0,.14)}
${S} .ff-step.ff-open{background:var(--fd-sel-bg)!important;box-shadow:inset 0 0 0 1.5px var(--fd-sel)!important}
${S} .ff-step-toggle{box-shadow:none!important;background:none!important;text-transform:none;letter-spacing:0;font-family:var(--font)!important;font-size:1rem!important}
${S} .ff-done .ff-step-title{color:var(--fd-active)!important}
${S} .ff-warn-box{border:0!important;border-radius:8px!important;background:var(--warn-soft)!important}

/* ---- pills everywhere become square-shouldered keys ---- */
${S} .pillnav a,${S} .sentinel-state,${S} .sentinel-counts span,${S} .sentinel-master-counts span{border-radius:6px!important}

@media (prefers-reduced-motion: reduce){${S} *{transition:none!important}}
`;

  let styleEl = null;

  function ensureStylesheet() {
    if (!styleEl) {
      styleEl = document.createElement("style");
      styleEl.id = "flightdeckSkin";
      styleEl.textContent = CSS;
    }
    const head = document.head || root;
    if (head.lastElementChild !== styleEl) {
      head.appendChild(styleEl);
    }
  }

  ensureStylesheet();
  new MutationObserver(() => {
    // Companion scripts add <style> elements as they render; keep the skin last.
    ensureStylesheet();
  }).observe(document.head || root, { childList: true });

  /* ------------------------------------------------------------------ */
  /* Screws                                                              */
  /* ------------------------------------------------------------------ */

  const SLOTS = [25, 115, 70, 160, 140, 35, 95, 10, 55, 130];
  let slotIndex = 0;
  const PANEL_SELECTOR = ".card, .topbar, .lcd-faceplate, .ff-hero, .ff-card";

  function addScrews(panel) {
    if (panel.querySelector(":scope > fd-screw")) return;
    const computed = window.getComputedStyle(panel);
    if (computed.position === "static") panel.style.position = "relative";
    for (const at of ["tl", "tr", "bl", "br"]) {
      const screw = document.createElement("fd-screw");
      screw.setAttribute("aria-hidden", "true");
      screw.dataset.at = at;
      screw.style.setProperty("--fd-slot", `${SLOTS[slotIndex % SLOTS.length]}deg`);
      slotIndex += 1;
      panel.appendChild(screw);
    }
  }

  function screwAllPanels() {
    document.querySelectorAll(PANEL_SELECTOR).forEach(addScrews);
  }

  /* ------------------------------------------------------------------ */
  /* LCD keys: BACK / NEXT (EJECT while Loadmaster owns the panel)        */
  /* ------------------------------------------------------------------ */

  // lcd-menu.py: button 0x01 (virtualLcdEnter) = previous page,
  // 0x02 (virtualLcdSelect) = next page. While Loadmaster is active,
  // 0x01 ejects the USB drive, so the left key must not say "Back" then.
  const GLYPHS = {
    back: '<svg class="fd-key-glyph" viewBox="0 0 22 14" aria-hidden="true"><path d="M9 2 3 7l6 5M3 7h16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    next: '<svg class="fd-key-glyph" viewBox="0 0 22 14" aria-hidden="true"><path d="m13 2 6 5-6 5M19 7H3" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    eject: '<svg class="fd-key-glyph" viewBox="0 0 22 14" aria-hidden="true"><path d="M11 1.5 4.5 8h13z" fill="currentColor"/><path d="M4.5 12h13" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  };

  function setKey(id, mode, legend, label) {
    const key = document.getElementById(id);
    if (!key || key.dataset.fdMode === mode) return;
    key.dataset.fdMode = mode;
    key.innerHTML = `${GLYPHS[mode]}<span class="fd-key-legend">${legend}</span>`;
    key.setAttribute("aria-label", label);
    key.setAttribute("title", label);
  }

  function syncLcdKeys() {
    const page = (document.getElementById("virtualLcdPage") || {}).textContent || "";
    const loadmaster = /loadmaster/i.test(page);
    if (loadmaster) {
      setKey("virtualLcdEnter", "eject", "EJECT", "Eject the Loadmaster USB drive");
      setKey("virtualLcdSelect", "next", "NEXT", "Next Loadmaster screen");
    } else {
      setKey("virtualLcdEnter", "back", "BACK", "Previous LCD page");
      setKey("virtualLcdSelect", "next", "NEXT", "Next LCD page");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Master WARNING / CAUTION                                            */
  /* ------------------------------------------------------------------ */

  // Lit from the same subsystem states renderHealth() already draws. Pressing
  // a lit master acknowledges it for this browser session; a NEW fault set
  // re-arms it, exactly like the real thing.
  const ACK_KEY = "truepanel-fd-master-ack";
  let masters = null;

  function readAcks() {
    try {
      return JSON.parse(sessionStorage.getItem(ACK_KEY) || "{}") || {};
    } catch (error) {
      return {};
    }
  }

  function writeAcks(acks) {
    try {
      sessionStorage.setItem(ACK_KEY, JSON.stringify(acks));
    } catch (error) {
      /* acknowledgement then lasts until reload */
    }
  }

  function faultSignature(kind) {
    const selector =
      kind === "warning"
        ? "#healthSubsystems .health-subsystem.degraded, #healthSubsystems .health-subsystem.critical"
        : "#healthSubsystems .health-subsystem.attention";
    return Array.from(document.querySelectorAll(selector))
      .map((node) => node.dataset.healthSubsystem || "")
      .sort()
      .join(",");
  }

  function buildMasters() {
    if (masters) return masters;
    const topbar = document.querySelector(".topbar");
    const connection = document.getElementById("connection");
    if (!topbar) return null;
    const group = document.createElement("div");
    group.className = "fd-glareshield";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Master warning and caution");
    const make = (kind, word) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "fd-master";
      button.dataset.kind = kind;
      button.dataset.lit = "false";
      button.innerHTML = `<span>MASTER</span><span>${word}</span>`;
      button.addEventListener("click", () => {
        const signature = faultSignature(kind);
        if (!signature) return;
        const acks = readAcks();
        acks[kind] = signature;
        writeAcks(acks);
        syncMasters();
      });
      group.appendChild(button);
      return button;
    };
    masters = { warning: make("warning", "WARNING"), caution: make("caution", "CAUTION") };
    topbar.insertBefore(group, connection || null);
    return masters;
  }

  function syncMasters() {
    const built = buildMasters();
    if (!built) return;
    const acks = readAcks();
    for (const kind of ["warning", "caution"]) {
      const signature = faultSignature(kind);
      const lit = Boolean(signature) && acks[kind] !== signature;
      const button = built[kind];
      button.dataset.lit = lit ? "true" : "false";
      const word = kind === "warning" ? "warning" : "caution";
      button.setAttribute(
        "aria-label",
        lit ? `Master ${word} lit — press to acknowledge` : signature ? `Master ${word} acknowledged` : `Master ${word} — nothing to report`
      );
    }
  }

  /* ------------------------------------------------------------------ */
  /* Wiring                                                              */
  /* ------------------------------------------------------------------ */

  let scheduled = false;
  function refresh() {
    scheduled = false;
    screwAllPanels();
    syncLcdKeys();
    syncMasters();
  }
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(refresh);
  }

  function start() {
    refresh();
    new MutationObserver(schedule).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
