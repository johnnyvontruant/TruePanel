/* TruePanel Flight Logs: read-only overlay, deliberately independent of dashboard state. */
(() => {
  "use strict";
  const start = () => {
    if (document.getElementById("tp-flight-open")) return;
    const open = document.createElement("button");
    open.id = "tp-flight-open";
    open.type = "button";
    open.textContent = "Flight Logs";
    open.setAttribute("aria-controls", "tp-flight-panel");
    open.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:9996;padding:10px 16px;border-radius:10px;background:#162d46;color:#fff;border:1px solid #7997ad;cursor:pointer";
    const panel = document.createElement("section");
    panel.id = "tp-flight-panel";
    panel.hidden = true;
    panel.setAttribute("aria-label", "Flight Logs");
    panel.style.cssText = "position:fixed;right:18px;bottom:70px;z-index:9997;width:min(760px,calc(100vw - 36px));max-height:75vh;overflow:auto;background:#142335;color:#f2f5f8;border:1px solid #70859a;border-radius:12px;padding:16px;box-shadow:0 12px 34px #0008";
    const heading = document.createElement("h2");
    heading.textContent = "Flight Logs · Read only";
    const controls = document.createElement("div");
    controls.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px";
    const severity = document.createElement("select");
    const category = document.createElement("select");
    const search = document.createElement("input");
    const refresh = document.createElement("button");
    const close = document.createElement("button");
    for (const [element, values, title] of [
      [severity, ["", "INFO", "WARNING", "CRITICAL", "ALERT"], "Severity"],
      [category, ["", "SYSTEM", "STORAGE", "ALERT", "BUZZER", "LOADMASTER", "THERMAL", "NETWORK"], "Category"]
    ]) {
      element.setAttribute("aria-label", title);
      for (const value of values) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value || "All " + title.toLowerCase() + "s";
        element.append(option);
      }
      element.style.cssText = "padding:7px;max-width:160px";
      controls.append(element);
    }
    search.placeholder = "Search displayed entries";
    search.setAttribute("aria-label", "Search Flight Logs");
    search.style.cssText = "padding:7px;flex:1;min-width:150px";
    refresh.textContent = "Refresh";
    close.textContent = "Close";
    for (const button of [refresh, close]) {
      button.type = "button";
      button.style.cssText = "padding:7px 12px;cursor:pointer";
    }
    controls.append(search, refresh, close);
    const status = document.createElement("p");
    status.setAttribute("role", "status");
    const entries = document.createElement("pre");
    entries.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,monospace;max-height:44vh;overflow:auto";
    panel.append(heading, controls, status, entries);
    document.body.append(open, panel);
    let lines = [];
    const render = () => {
      const term = search.value.toLowerCase();
      const selected = lines.filter(line => line.toLowerCase().includes(term));
      entries.textContent = selected.length ? selected.join("\n") : "No matching events.";
      status.textContent = selected.length + " displayed / " + lines.length + " retrieved";
    };
    const load = async () => {
      status.textContent = "Loading recent events…";
      const params = new URLSearchParams({limit:"300"});
      if (severity.value) params.set("severity",severity.value);
      if (category.value) params.set("category",category.value);
      try {
        const response = await fetch("/api/v1/flight-logs?" + params, {cache:"no-store"});
        if (!response.ok) throw new Error("HTTP " + response.status);
        const payload = await response.json();
        if (!Array.isArray(payload.entries)) throw new Error("Invalid response");
        lines = payload.entries;
        render();
      } catch (error) {
        lines = [];
        entries.textContent = "";
        status.textContent = "Flight Logs unavailable: " + error.message;
      }
    };
    open.addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) load(); });
    close.addEventListener("click", () => { panel.hidden = true; open.focus(); });
    refresh.addEventListener("click", load);
    severity.addEventListener("change", load);
    category.addEventListener("change", load);
    search.addEventListener("input", render);
    document.addEventListener("keydown", event => { if (event.key === "Escape" && !panel.hidden) { panel.hidden = true; open.focus(); } });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
