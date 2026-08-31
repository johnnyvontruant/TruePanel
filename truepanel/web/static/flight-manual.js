(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const POLL_MS=5000;
const PRIORITY={
    "storage.disk_faulted":0,
    "storage.pool_degraded":1,
    "storage.smart_warning":2,
    "cooling.fan_stall":3,
    "thermal.high_temperature":4,
    "network.link_down":5,
    "front_panel.lcd_unavailable":6,
    "telemetry.stale":7,
};

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

const label=value=>String(value||"")
    .replaceAll("_"," ")
    .replace(/\b\w/g,char=>char.toUpperCase());

function safeUrl(value){
    try{
        const url=new URL(String(value||""),window.location.href);
        return ["http:","https:"].includes(url.protocol)?url.href:"";
    }catch(_error){
        return "";
    }
}

function phaseText(phase){
    return ({
        diagnose:"DIAGNOSE",
        identify:"IDENTIFY",
        prepare_repair:"PREPARE REPAIR",
        monitor_recovery:"MONITOR RECOVERY",
    })[phase]||String(phase||"REVIEW").replaceAll("_"," ").toUpperCase();
}

function phaseNote(item){
    const runtime=item.runtime||{};
    const evidence=runtime.evidence||{};
    if(runtime.phase==="monitor_recovery"){
        const resilver=evidence.resilver_state||{};
        const progress=resilver.percent!=null?` ${resilver.percent}% complete.`:"";
        const remaining=resilver.remaining?` ${resilver.remaining}.`:"";
        return `Recovery is already in progress.${progress}${remaining} Do not replace another member until redundancy is restored.`;
    }
    if(item.code==="storage.disk_faulted"){
        const bay=evidence.bay?`Bay ${evidence.bay}`:"the physical bay";
        const device=evidence.device?` /dev/${evidence.device}`:"";
        return `A faulted ZFS member is identified. ${bay}${device} is evidence only until every service gate below is satisfied.`;
    }
    if(item.code==="storage.pool_degraded"){
        return "The pool is degraded, but TruePanel will not guess which disk to remove. Resolve the affected VDEV and exact hardware identity first.";
    }
    if(item.code==="storage.smart_warning"){
        return "A drive-health warning is not the same as a faulted ZFS member. Correlate SMART evidence, ZFS state, and physical identity before considering replacement.";
    }
    return "Review the verified evidence and complete safe diagnostic checks before considering any disruptive action.";
}

function evidenceDisplay(key,value){
    if(typeof value==="boolean") return value?"Yes":"No";
    if(Array.isArray(value)){
        if(!value.length) return "None";
        return value.map(item=>{
            if(item&&typeof item==="object"){
                const name=item.label||item.name||"Item";
                const rpm=Number(item.rpm);
                return Number.isFinite(rpm)?`${name} · ${rpm} RPM`:String(name);
            }
            return String(item);
        }).join(", ");
    }
    if(value&&typeof value==="object"){
        const parts=[];
        if(value.resilver_running===true) parts.push("Resilver running");
        if(value.scrub_running===true) parts.push("Scrub running");
        if(value.percent!=null) parts.push(`${value.percent}%`);
        if(value.remaining) parts.push(String(value.remaining));
        if(value.status_line) parts.push(String(value.status_line));
        return parts.length?parts.join(" · "):JSON.stringify(value);
    }
    if(key==="device") return `/dev/${value}`;
    if(key==="current_rpm") return `${value} RPM`;
    if(key.endsWith("_temperature_c")) return `${value}°C`;
    if(key==="telemetry_age_seconds") return `${value}s`;
    return String(value);
}

function evidenceRows(evidence){
    const preferred=[
        ["pool","Pool"],["pool_state","Pool state"],["vdev","VDEV"],
        ["vdev_topology","Topology"],["remaining_redundancy","Redundancy remaining"],
        ["bay","Physical bay"],["device","Linux device"],["label","Label"],
        ["model","Model"],["serial_last4","Serial suffix"],["zfs_state","ZFS state"],
        ["read_errors","Read errors"],["write_errors","Write errors"],
        ["checksum_errors","Checksum errors"],["mapping_source","Bay mapping source"],
        ["fan_label","Fan"],["fan_channel","Fan channel"],["current_rpm","Current RPM"],
        ["failure_observations","Failure observations"],["other_fan_rpm","Other monitored fans"],
        ["cpu_temperature_c","CPU temperature"],["system_temperature_c","System temperature"],
        ["telemetry_age_seconds","Telemetry age"],["interface","Interface"],
        ["link_up","Carrier"],["operstate","Operating state"],["address","Address"],
        ["primary","Primary path"],["other_reachable_interfaces","Alternate reachable paths"],
        ["tailscale_reachable","Tailscale reachable"],["serial_device","Serial device"],
        ["reader_connected","Reader connected"],["last_successful_io","Last healthy I/O"],
        ["dispatcher_alive","Dispatcher running"],["mission_control_reachable","Mission Control reachable"],
    ];
    const rows=[];
    for(const [key,title] of preferred){
        const value=evidence[key];
        if(value===undefined||value===null||value==="") continue;
        rows.push(`<div class="fm-evidence-row"><span>${esc(title)}</span><strong>${esc(evidenceDisplay(key,value))}</strong></div>`);
    }
    return rows.join("")||'<div class="fm-empty">No fault-specific evidence is verified yet.</div>';
}

function calloutFor(item,evidence){
    const code=String(item.code||"");
    if(code.startsWith("storage.")){
        const exactBay=Boolean(evidence.bay&&evidence.device);
        const critical=String(item.severity||"").toLowerCase()==="critical";
        return{
            className:critical||!exactBay?"danger":"caution",
            headline:critical
                ?(exactBay
                    ?"CRITICAL DRIVE HEALTH. Prepare a validated replacement; removal remains locked until every service gate is satisfied."
                    :"CRITICAL DRIVE HEALTH. DO NOT REMOVE A DISK until TruePanel verifies the exact physical bay and device.")
                :(exactBay
                    ?"Physical identity has been correlated, but removal remains locked until the service gates are satisfied."
                    :"DO NOT REMOVE A DISK. TruePanel has not verified an exact physical bay and device pair."),
            detail:phaseNote(item),
        };
    }
    if(code==="cooling.fan_stall"){
        return{
            className:"caution",
            headline:"Cooling capacity may be reduced.",
            detail:"Keep temperatures within safe limits. Do not open the chassis until the model-specific service procedure is verified.",
        };
    }
    if(code.startsWith("thermal.")){
        return{
            className:"caution",
            headline:"Protect thermal margin while diagnosing the cause.",
            detail:"Reduce avoidable load and restore trustworthy cooling telemetry before escalating control or service actions.",
        };
    }
    if(code==="network.link_down"){
        return{
            className:"caution",
            headline:"Preserve any working management path.",
            detail:"Check carrier, cable, and the peer switch/router port before changing interface configuration.",
        };
    }
    if(code.startsWith("front_panel.")){
        return{
            className:"caution",
            headline:"This is a front-panel fault, not a storage fault.",
            detail:"Keep managing the NAS through Mission Control while checking the LCD reader service and serial path.",
        };
    }
    if(code==="telemetry.stale"){
        return{
            className:"caution",
            headline:"Hardware state is partially unknown until fresh telemetry returns.",
            detail:"Keep automated decisions conservative and recover the narrowest stale telemetry source first.",
        };
    }
    return{
        className:"caution",
        headline:"Safe diagnostic guidance only.",
        detail:"Review verified evidence before taking any disruptive action.",
    };
}

function gate(name,value){
    const ready=Boolean(value);
    return `<div class="fm-gate ${ready?"ready":"locked"}"><span>${ready?"READY":"LOCKED"}</span><strong>${esc(name)}</strong></div>`;
}

function steps(title,items){
    if(!Array.isArray(items)||!items.length) return "";
    const slug=String(title||"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
    return `<section class="fm-section fm-section-${esc(slug)}"><h4>${esc(title)}</h4>${items.map(step=>{
        const destructive=Boolean(step.destructive)||step.risk==="destructive";
        const shutdown=Boolean(step.requires_shutdown);
        const chips=[];
        if(destructive) chips.push('<span class="fm-chip danger">DESTRUCTIVE · LOCKED</span>');
        else if(step.risk&&step.risk!=="safe") chips.push(`<span class="fm-chip caution">${esc(String(step.risk).toUpperCase())}</span>`);
        else chips.push('<span class="fm-chip safe">SAFE CHECK</span>');
        if(shutdown) chips.push('<span class="fm-chip caution">SHUTDOWN REQUIRED</span>');
        return `<div class="fm-step"><div class="fm-step-head"><strong>${esc(step.title)}</strong><div>${chips.join("")}</div></div><p>${esc(step.detail)}</p></div>`;
    }).join("")}</section>`;
}

function sources(items){
    if(!Array.isArray(items)||!items.length) return "";
    return `<section class="fm-section fm-sources"><h4>Authoritative references</h4>${items.map(source=>{
        const href=safeUrl(source.url);
        const title=esc(source.title||source.authority||"Reference");
        const link=href?`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${title}</a>`:title;
        return `<div class="fm-source"><strong>${link}</strong><span>${esc(source.authority||"")} · ${esc(source.scope||"")}</span></div>`;
    }).join("")}</section>`;
}

function card(item){
    const runtime=item.runtime||{};
    const evidence=runtime.evidence||{};
    const action=runtime.action_gate||{};
    const blockers=Array.isArray(action.blocked_by)?action.blocked_by:[];
    const callout=calloutFor(item,evidence);
    const disruptiveLabel=String(item.code||"").startsWith("storage.")
        ?"Destructive storage action"
        :"Disruptive action";
    return `<article class="fm-card" data-guidance-code="${esc(item.code)}" data-guidance-severity="${esc(item.severity||"caution")}">
        <div class="fm-card-head">
            <div><span class="fm-kicker">${esc(item.code)}</span><h3>${esc(item.title||"Operator guidance")}</h3></div>
            <span class="fm-phase">${esc(phaseText(runtime.phase))}</span>
        </div>
        <p class="fm-summary">${esc(item.summary||"")}</p>
        <div class="fm-callout ${callout.className}"><strong>${esc(callout.headline)}</strong><span>${esc(callout.detail)}</span></div>
        ${steps("Immediate actions",item.immediate_actions)}
        <details class="fm-tech">
            <summary>Technical evidence &amp; readiness gates</summary>
            <div class="fm-grid">
                <section><h4>Verified evidence</h4><div class="fm-evidence">${evidenceRows(evidence)}</div></section>
                <section><h4>Action gates</h4><div class="fm-gates">
                    ${gate("Safe diagnostics",action.safe_checks)}
                    ${gate("Physical service",action.physical_service_ready)}
                    ${gate(disruptiveLabel,action.destructive_actions_ready)}
                </div>${blockers.length?`<div class="fm-blockers"><strong>Blocked by</strong>${blockers.map(item=>`<span>${esc(label(item))}</span>`).join("")}</div>`:""}</section>
            </div>
        </details>
        ${steps("Diagnosis",item.diagnosis)}
        ${steps("Remediation",item.remediation)}
        ${steps("Verification",item.verification)}
        ${item.escalation?`<section class="fm-section"><h4>Escalation</h4><p>${esc(item.escalation)}</p></section>`:""}
        ${sources(item.sources)}
    </article>`;
}

function installCockpitLayout(panel){
    const grid=document.querySelector("main .grid");
    if(!grid||document.getElementById("cockpitOverview")) return;

    const health=document.querySelector(".health-command");
    const advisory=document.getElementById("healthAdvisory");
    const preflight=document.getElementById("preflightPanel");
    const cpu=document.getElementById("cpu")?.closest("article");
    const memory=document.getElementById("ram")?.closest("article");
    const storage=document.getElementById("pools")?.closest("article");
    const temperatures=document.getElementById("temps")?.closest("article");
    const network=document.getElementById("network")?.closest("article");

    if(!health||!preflight||!cpu||!memory||!storage||!temperatures||!network) return;

    const style=document.createElement("style");
    style.textContent=`
.cockpit-overview{grid-column:1/-1;display:grid;gap:1rem}.cockpit-zone-label{color:var(--muted);font-size:.66rem;font-weight:850;letter-spacing:.16em;text-transform:uppercase}.cockpit-command-row{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr);gap:1rem;align-items:stretch}.cockpit-command-row>.card{height:100%;margin:0}.cockpit-command-row .health-command,.cockpit-command-row .preflight-panel{grid-column:auto}.cockpit-overview>.health-advisory{grid-column:auto;margin:0}.cockpit-overview>#flightManualPanel{grid-column:auto;margin:0}.cockpit-overview .preflight-sections{grid-template-columns:repeat(2,minmax(0,1fr))}.cockpit-overview .preflight-section:last-child{grid-column:1/-1}.cockpit-telemetry-zone{grid-column:1/-1;display:grid;gap:.55rem}.cockpit-telemetry-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(190px,.72fr);gap:1rem;align-items:stretch}.cockpit-telemetry-grid>.card{margin:0;min-width:0;height:100%}.cockpit-resource-stack{display:grid;grid-template-rows:repeat(2,minmax(0,1fr));gap:1rem}.cockpit-resource-stack>.card{margin:0;min-width:0}.cockpit-resource-stack .metric{font-size:1.55rem}@media(max-width:980px){.cockpit-command-row{grid-template-columns:1fr}.cockpit-telemetry-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cockpit-resource-stack{grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:auto}}@media(max-width:640px){.cockpit-telemetry-grid,.cockpit-resource-stack{grid-template-columns:1fr}.cockpit-resource-stack{grid-column:auto}}
`;
    document.head.appendChild(style);

    health.dataset.cockpitRole="system-health";
    preflight.dataset.cockpitRole="preflight";
    cpu.dataset.cockpitRole="cpu";
    memory.dataset.cockpitRole="memory";
    storage.dataset.cockpitRole="storage";
    temperatures.dataset.cockpitRole="drive-temperatures";
    network.dataset.cockpitRole="network";
    if(advisory) advisory.dataset.cockpitRole="advisory";
    if(panel) panel.dataset.cockpitRole="flight-manual";

    const overview=document.createElement("section");
    overview.id="cockpitOverview";
    overview.className="cockpit-overview";
    overview.setAttribute("aria-label","Mission Control command status");

    const commandLabel=document.createElement("div");
    commandLabel.className="cockpit-zone-label";
    commandLabel.textContent="Command Status";

    const commandRow=document.createElement("div");
    commandRow.className="cockpit-command-row";
    commandRow.append(health,preflight);

    overview.append(commandLabel,commandRow);
    if(advisory) overview.append(advisory);
    if(panel) overview.append(panel);
    grid.prepend(overview);

    const telemetry=document.createElement("section");
    telemetry.id="cockpitTelemetry";
    telemetry.className="cockpit-telemetry-zone";
    telemetry.setAttribute("aria-label","Operations telemetry");

    const telemetryLabel=document.createElement("div");
    telemetryLabel.className="cockpit-zone-label";
    telemetryLabel.textContent="Operations Telemetry";

    const telemetryGrid=document.createElement("div");
    telemetryGrid.className="cockpit-telemetry-grid";

    const resourceStack=document.createElement("div");
    resourceStack.className="cockpit-resource-stack";
    resourceStack.append(cpu,memory);

    telemetryGrid.append(temperatures,network,resourceStack);
    telemetry.append(telemetryLabel,telemetryGrid);
    storage.insertAdjacentElement("afterend",telemetry);

    document.body.classList.add("cockpit-layout");
}

function install(){
    if(document.getElementById("flightManualPanel")) return;
    const button=document.getElementById("openFlightManual");
    if(!button) return;

    const style=document.createElement("style");
    style.textContent=`
#flightManualPanel{display:none;grid-column:1/-1;border:1px solid color-mix(in srgb,var(--accent) 38%,transparent);border-radius:14px;padding:1.35rem;background:linear-gradient(145deg,color-mix(in srgb,var(--panel-solid) 66%,transparent),color-mix(in srgb,var(--panel-solid) 66%,transparent));scroll-margin-top:1rem}
#flightManualPanel.show{display:block}.fm-shell-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;margin-bottom:1rem}.fm-shell-head h2{margin:.2rem 0;font-size:1.3rem}.fm-kicker{color:var(--accent);font-size:.68rem;font-weight:850;letter-spacing:.12em;text-transform:uppercase}.fm-readonly{border:1px solid var(--edge);border-radius:999px;padding:.4rem .65rem;color:var(--muted);font-size:.72rem;font-weight:800}.fm-card{margin-top:1rem;padding:1rem;border:1px solid var(--edge);border-radius:12px;background:color-mix(in srgb,var(--panel-solid) 55%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.fm-card-head{display:flex;justify-content:space-between;gap:1rem}.fm-card h3{margin:.25rem 0 0;font-size:1.15rem}.fm-phase{color:var(--warn);font-size:.72rem;font-weight:850;letter-spacing:.08em}.fm-summary,.fm-section p{color:var(--muted);font-size:.84rem;line-height:1.5}.fm-callout{display:grid;gap:.3rem;margin:.9rem 0;padding:.8rem;border-radius:9px}.fm-callout span{font-size:.8rem}.fm-callout.danger{border:1px solid color-mix(in srgb,var(--bad) 55%,transparent);background:color-mix(in srgb,var(--bad) 30%,transparent)}.fm-callout.caution{border:1px solid color-mix(in srgb,var(--warn) 45%,transparent);background:color-mix(in srgb,var(--warn) 28%,transparent)}.fm-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.fm-grid h4,.fm-section h4{margin:.7rem 0;color:var(--muted);font-size:.72rem;letter-spacing:.1em;text-transform:uppercase}.fm-evidence-row{display:flex;justify-content:space-between;gap:1rem;padding:.42rem 0;border-bottom:1px solid color-mix(in srgb,var(--edge) 12%,transparent);font-size:.78rem}.fm-evidence-row span{color:var(--muted)}.fm-evidence-row strong{text-align:right}.fm-empty{color:var(--muted);font-size:.78rem}.fm-gates{display:grid;gap:.45rem}.fm-gate{display:grid;grid-template-columns:72px 1fr;gap:.5rem;padding:.55rem;border:1px solid var(--edge);border-radius:8px;font-size:.78rem}.fm-gate span{font-weight:900}.fm-gate.ready span{color:var(--good)}.fm-gate.locked span{color:var(--bad)}.fm-blockers{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.7rem;font-size:.7rem}.fm-blockers strong{width:100%;color:var(--muted);text-transform:uppercase}.fm-blockers span{padding:.28rem .4rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted)}.fm-section{margin-top:1rem;padding-top:.5rem;border-top:1px solid color-mix(in srgb,var(--edge) 14%,transparent)}.fm-step{padding:.7rem 0;border-bottom:1px solid color-mix(in srgb,var(--edge) 10%,transparent)}.fm-step-head{display:flex;justify-content:space-between;gap:.7rem;align-items:flex-start;font-size:.82rem}.fm-step p{margin:.35rem 0 0}.fm-chip{display:inline-block;margin-left:.3rem;padding:.2rem .35rem;border:1px solid var(--edge);border-radius:999px;font-size:.58rem;font-weight:900;white-space:nowrap}.fm-chip.safe{color:var(--good)}.fm-chip.caution{color:var(--warn)}.fm-chip.danger{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 50%,transparent)}.fm-source{display:grid;gap:.15rem;padding:.45rem 0;font-size:.76rem}.fm-source a{color:var(--accent)}.fm-source span{color:var(--muted)}.fm-status{color:var(--muted);font-size:.8rem}@media(max-width:760px){.fm-grid{grid-template-columns:1fr}.fm-card-head,.fm-step-head,.fm-shell-head{display:block}.fm-phase,.fm-readonly{display:inline-block;margin-top:.5rem}}
#flightManualPanel{backdrop-filter:blur(22px) saturate(180%);-webkit-backdrop-filter:blur(22px) saturate(180%)}
.fm-card{backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%);box-shadow:var(--shadow,0 1px 2px rgba(0,0,0,.06))}
.fm-callout{position:relative;padding:1rem 1.1rem 1rem 1.2rem;font-size:.95rem}
.fm-callout strong{font-size:1.05rem;display:block;margin-bottom:.2rem}
.fm-callout::before{content:"Diagnosis";display:block;margin-bottom:.35rem;font-size:.64rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;opacity:.75}
.fm-section-immediate-actions{margin-top:1.1rem;padding:.9rem 1rem 1rem;border:1px solid color-mix(in srgb,var(--good) 35%,var(--edge));border-radius:12px;background:color-mix(in srgb,var(--good) 8%,transparent)}
.fm-section-immediate-actions h4{color:var(--good);font-size:.7rem;letter-spacing:.1em}
.fm-section-immediate-actions h4::before{content:"✓ ";}
.fm-section-immediate-actions .fm-step{border-bottom-color:color-mix(in srgb,var(--good) 18%,transparent)}
.fm-section-immediate-actions .fm-step:last-child{border-bottom:0;padding-bottom:0}
.fm-section-immediate-actions .fm-step-head strong{font-size:.92rem}
details.fm-tech{margin-top:1.1rem;padding:0 .9rem;border:1px solid var(--edge);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 32%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}
details.fm-tech>summary{padding:.75rem 0;cursor:pointer;list-style:none;color:var(--muted);font-size:.74rem;font-weight:700;letter-spacing:.04em}
details.fm-tech>summary::-webkit-details-marker{display:none}
details.fm-tech>summary::before{content:"›";display:inline-block;margin-right:.5rem;transition:transform .15s ease}
details.fm-tech[open]>summary::before{transform:rotate(90deg)}
details.fm-tech[open]>summary{border-bottom:1px solid var(--edge);margin-bottom:.15rem}
details.fm-tech .fm-grid{margin:.85rem 0 1rem;opacity:.92}
details.fm-tech .fm-evidence-row,details.fm-tech .fm-gate{font-size:.74rem}
.fm-section:not(.fm-section-immediate-actions) h4{opacity:.85}
`;
    document.head.appendChild(style);

    const panel=document.createElement("article");
    panel.id="flightManualPanel";
    panel.setAttribute("aria-live","polite");
    panel.innerHTML='<div class="fm-shell-head"><div><span class="fm-kicker">Project Kobayashi</span><h2>Flight Manual · Guided Recovery</h2><div class="fm-status">Waiting for operator-guidance telemetry.</div></div><span class="fm-readonly">READ-ONLY GUIDANCE</span></div><div id="flightManualCards"></div>';
    const advisory=document.getElementById("healthAdvisory");
    if(advisory&&advisory.parentNode) advisory.insertAdjacentElement("afterend",panel);
    else document.querySelector("main")?.prepend(panel);

    installCockpitLayout(panel);

    button.addEventListener("click",()=>{
        panel.classList.add("show");
        panel.scrollIntoView({behavior:"smooth",block:"start"});
    });

    let renderedCards=null;

    async function refresh(){
        try{
            const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
            if(!response.ok) throw new Error(`status ${response.status}`);
            const payload=await response.json();
            const guidance=Array.isArray(payload.operator_guidance)?payload.operator_guidance.slice():[];
            guidance.sort((a,b)=>(PRIORITY[a.code]??99)-(PRIORITY[b.code]??99));
            button.disabled=guidance.length===0;
            button.textContent=guidance.length?`Open Flight Manual (${guidance.length})`:"Open Flight Manual";
            const status=panel.querySelector(".fm-status");
            const cards=panel.querySelector("#flightManualCards");
            if(!guidance.length){
                status.textContent="No active guided-recovery procedure is required.";
                if(renderedCards!==""){
                    cards.innerHTML="";
                    renderedCards="";
                }
                panel.classList.remove("show");
                return;
            }
            status.textContent=`${guidance.length} active recovery procedure${guidance.length===1?"":"s"}. Safe diagnostic guidance is available; locked actions remain unavailable.`;

            const nextCards=guidance.map(card).join("");
            if(nextCards!==renderedCards){
                const scrollX=window.scrollX;
                const scrollY=window.scrollY;

                cards.innerHTML=nextCards;
                renderedCards=nextCards;

                if(panel.classList.contains("show")){
                    window.requestAnimationFrame(
                        ()=>window.scrollTo(scrollX,scrollY)
                    );
                }
            }
        }catch(_error){
            button.disabled=true;
            panel.querySelector(".fm-status").textContent="Flight Manual telemetry is temporarily unavailable.";
        }
    }

    refresh();
    window.setInterval(refresh,POLL_MS);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();