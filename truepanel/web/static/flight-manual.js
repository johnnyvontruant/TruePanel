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
        prepare_repair:"PREPARE REPAIR",
        monitor_recovery:"MONITOR RECOVERY",
    })[phase]||String(phase||"REVIEW").replaceAll("_"," ").toUpperCase();
}

function phaseNote(item){
    const runtime=item.runtime||{};
    const evidence=runtime.evidence||{};
    if(runtime.phase==="monitor_recovery"){
        const resilver=evidence.resilver_state||{};
        const progress=resilver.percent!=null?` ${esc(resilver.percent)}% complete.`:"";
        const remaining=resilver.remaining?` ${esc(resilver.remaining)}.`:"";
        return `Recovery is already in progress.${progress}${remaining} Do not replace another member until redundancy is restored.`;
    }
    if(item.code==="storage.disk_faulted"){
        const bay=evidence.bay?`Bay ${esc(evidence.bay)}`:"the physical bay";
        const device=evidence.device?` /dev/${esc(evidence.device)}`:"";
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
        const display=evidenceDisplay(key,value);
        rows.push(`<div class="fm-evidence-row"><span>${esc(title)}</span><strong>${esc(display)}</strong></div>`);
    }
    return rows.join("")||'<div class="fm-empty">No fault-specific evidence is verified yet.</div>';
}

function calloutFor(item,evidence){
    const code=String(item.code||"");
    if(code.startsWith("storage.")){
        const exactBay=Boolean(evidence.bay&&evidence.device);
        return{
            className:exactBay?"caution":"danger",
            headline:exactBay
                ?"Physical identity has been correlated, but removal remains locked until the service gates are satisfied."
                :"DO NOT REMOVE A DISK. TruePanel has not verified an exact physical bay and device pair.",
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
    return `<section class="fm-section"><h4>${esc(title)}</h4>${items.map(step=>{
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
    return `<article class="fm-card" data-guidance-code="${esc(item.code)}">
        <div class="fm-card-head">
            <div><span class="fm-kicker">${esc(item.code)}</span><h3>${esc(item.title||"Operator guidance")}</h3></div>
            <span class="fm-phase">${esc(phaseText(runtime.phase))}</span>
        </div>
        <p class="fm-summary">${esc(item.summary||"")}</p>
        <div class="fm-callout ${callout.className}"><strong>${esc(callout.headline)}</strong><span>${esc(callout.detail)}</span></div>
        <div class="fm-grid">
            <section><h4>Verified evidence</h4><div class="fm-evidence">${evidenceRows(evidence)}</div></section>
            <section><h4>Action gates</h4><div class="fm-gates">
                ${gate("Safe diagnostics",action.safe_checks)}
                ${gate("Physical service",action.physical_service_ready)}
                ${gate(disruptiveLabel,action.destructive_actions_ready)}
            </div>${blockers.length?`<div class="fm-blockers"><strong>Blocked by</strong>${blockers.map(item=>`<span>${esc(label(item))}</span>`).join("")}</div>`:""}</section>
        </div>
        ${steps("Immediate actions",item.immediate_actions)}
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
    const network=document.getElementById("network")?.closest("article");

    if(!health||!preflight||!cpu||!memory||!network) return;

    const style=document.createElement("style");
    style.textContent=`
.cockpit-overview{grid-column:1/-1;display:grid;gap:1rem}.cockpit-zone-label{color:var(--muted);font-size:.66rem;font-weight:850;letter-spacing:.16em;text-transform:uppercase}.cockpit-command-row{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr);gap:1rem;align-items:stretch}.cockpit-command-row>.card{height:100%;margin:0}.cockpit-command-row .health-command,.cockpit-command-row .preflight-panel{grid-column:auto}.cockpit-instrument-strip{display:grid;grid-template-columns:minmax(170px,.6fr) minmax(170px,.6fr) minmax(320px,1.8fr);gap:1rem}.cockpit-instrument-strip>.card{min-width:0;margin:0}.cockpit-instrument-strip .metric{font-size:1.65rem}.cockpit-overview>.health-advisory{grid-column:auto;margin:0}.cockpit-overview>#flightManualPanel{grid-column:auto;margin:0}.cockpit-overview .preflight-sections{grid-template-columns:repeat(2,minmax(0,1fr))}.cockpit-overview .preflight-section:last-child{grid-column:1/-1}@media(max-width:980px){.cockpit-command-row{grid-template-columns:1fr}.cockpit-instrument-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.cockpit-instrument-strip>[data-cockpit-role="network"]{grid-column:1/-1}}@media(max-width:640px){.cockpit-instrument-strip{grid-template-columns:1fr}.cockpit-instrument-strip>[data-cockpit-role="network"]{grid-column:auto}}
`;
    document.head.appendChild(style);

    health.dataset.cockpitRole="system-health";
    preflight.dataset.cockpitRole="preflight";
    cpu.dataset.cockpitRole="cpu";
    memory.dataset.cockpitRole="memory";
    network.dataset.cockpitRole="network";
    if(advisory) advisory.dataset.cockpitRole="advisory";
    if(panel) panel.dataset.cockpitRole="flight-manual";

    const overview=document.createElement("section");
    overview.id="cockpitOverview";
    overview.className="cockpit-overview";
    overview.setAttribute("aria-label","Mission Control command deck");

    const commandLabel=document.createElement("div");
    commandLabel.className="cockpit-zone-label";
    commandLabel.textContent="Command Status";

    const commandRow=document.createElement("div");
    commandRow.className="cockpit-command-row";
    commandRow.append(health,preflight);

    const instrumentLabel=document.createElement("div");
    instrumentLabel.className="cockpit-zone-label";
    instrumentLabel.textContent="Live Instruments";

    const instruments=document.createElement("div");
    instruments.className="cockpit-instrument-strip";
    instruments.append(cpu,memory,network);

    overview.append(commandLabel,commandRow);
    if(advisory) overview.append(advisory);
    if(panel) overview.append(panel);
    overview.append(instrumentLabel,instruments);

    grid.prepend(overview);
    document.body.classList.add("cockpit-layout");
}

function install(){
    if(document.getElementById("flightManualPanel")) return;
    const button=document.getElementById("openFlightManual");
    if(!button) return;

    const style=document.createElement("style");
    style.textContent=`
#flightManualPanel{display:none;grid-column:1/-1;border:1px solid rgba(57,167,255,.38);border-radius:14px;padding:1.35rem;background:linear-gradient(145deg,rgba(11,22,34,.98),rgba(6,10,16,.98));scroll-margin-top:1rem}
#flightManualPanel.show{display:block}.fm-shell-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;margin-bottom:1rem}.fm-shell-head h2{margin:.2rem 0;font-size:1.3rem}.fm-kicker{color:var(--accent);font-size:.68rem;font-weight:850;letter-spacing:.12em;text-transform:uppercase}.fm-readonly{border:1px solid var(--edge);border-radius:999px;padding:.4rem .65rem;color:var(--muted);font-size:.72rem;font-weight:800}.fm-card{margin-top:1rem;padding:1rem;border:1px solid var(--edge);border-radius:12px;background:rgba(3,8,13,.55)}.fm-card-head{display:flex;justify-content:space-between;gap:1rem}.fm-card h3{margin:.25rem 0 0;font-size:1.15rem}.fm-phase{color:var(--warn);font-size:.72rem;font-weight:850;letter-spacing:.08em}.fm-summary,.fm-section p{color:var(--muted);font-size:.84rem;line-height:1.5}.fm-callout{display:grid;gap:.3rem;margin:.9rem 0;padding:.8rem;border-radius:9px}.fm-callout span{font-size:.8rem}.fm-callout.danger{border:1px solid rgba(255,93,115,.55);background:rgba(90,18,31,.3)}.fm-callout.caution{border:1px solid rgba(255,200,87,.45);background:rgba(76,52,11,.28)}.fm-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.fm-grid h4,.fm-section h4{margin:.7rem 0;color:var(--muted);font-size:.72rem;letter-spacing:.1em;text-transform:uppercase}.fm-evidence-row{display:flex;justify-content:space-between;gap:1rem;padding:.42rem 0;border-bottom:1px solid rgba(143,164,184,.12);font-size:.78rem}.fm-evidence-row span{color:var(--muted)}.fm-evidence-row strong{text-align:right}.fm-empty{color:var(--muted);font-size:.78rem}.fm-gates{display:grid;gap:.45rem}.fm-gate{display:grid;grid-template-columns:72px 1fr;gap:.5rem;padding:.55rem;border:1px solid var(--edge);border-radius:8px;font-size:.78rem}.fm-gate span{font-weight:900}.fm-gate.ready span{color:var(--good)}.fm-gate.locked span{color:var(--bad)}.fm-blockers{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.7rem;font-size:.7rem}.fm-blockers strong{width:100%;color:var(--muted);text-transform:uppercase}.fm-blockers span{padding:.28rem .4rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted)}.fm-section{margin-top:1rem;padding-top:.5rem;border-top:1px solid rgba(143,164,184,.14)}.fm-step{padding:.7rem 0;border-bottom:1px solid rgba(143,164,184,.1)}.fm-step-head{display:flex;justify-content:space-between;gap:.7rem;align-items:flex-start;font-size:.82rem}.fm-step p{margin:.35rem 0 0}.fm-chip{display:inline-block;margin-left:.3rem;padding:.2rem .35rem;border:1px solid var(--edge);border-radius:999px;font-size:.58rem;font-weight:900;white-space:nowrap}.fm-chip.safe{color:var(--good)}.fm-chip.caution{color:var(--warn)}.fm-chip.danger{color:var(--bad);border-color:rgba(255,93,115,.5)}.fm-source{display:grid;gap:.15rem;padding:.45rem 0;font-size:.76rem}.fm-source a{color:var(--accent)}.fm-source span{color:var(--muted)}.fm-status{color:var(--muted);font-size:.8rem}@media(max-width:760px){.fm-grid{grid-template-columns:1fr}.fm-card-head,.fm-step-head,.fm-shell-head{display:block}.fm-phase,.fm-readonly{display:inline-block;margin-top:.5rem}}
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
                cards.innerHTML="";
                panel.classList.remove("show");
                return;
            }
            status.textContent=`${guidance.length} active recovery procedure${guidance.length===1?"":"s"}. Safe diagnostic guidance is available; locked actions remain unavailable.`;
            cards.innerHTML=guidance.map(card).join("");
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