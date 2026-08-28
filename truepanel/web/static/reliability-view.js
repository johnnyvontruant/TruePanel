(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
const title=value=>String(value||"")
    .replaceAll("_"," ")
    .replace(/\b\w/g,char=>char.toUpperCase());

function signalRows(items){
    const signals=Array.isArray(items)?items.slice(0,6):[];
    if(!signals.length) return '<div class="ag-empty">No abnormal supporting signals.</div>';
    return signals.map(item=>{
        const value=item?.value===undefined||item?.value===null?"":` · ${item.value}`;
        return `<div class="ag-signal"><span>${esc(item?.source||"evidence")}</span><strong>${esc(title(item?.signal||"signal"))}${esc(value)}</strong><small>${esc(title(item?.state||"observed"))}</small></div>`;
    }).join("");
}

function gapRows(matrix){
    const entries=Array.isArray(matrix?.entries)?matrix.entries:[];
    const gaps=entries.filter(item=>item?.coverage_state!=="TRUSTED");
    if(!gaps.length) return '<div class="ag-gap-clear">All actionable alert paths are covered and rehearsed.</div>';
    return gaps.map(item=>`<div class="ag-gap"><strong>${esc(item?.code||"unknown")}</strong><span>${esc((item?.gaps||[]).join(" · ")||"Coverage incomplete")}</span></div>`).join("");
}

function render(view,payload){
    const reliability=payload?.reliability||{};
    const incident=reliability?.active_incident||null;
    const matrix=reliability?.coverage_matrix||{};
    const summary=reliability?.coverage_summary||{};
    const policy=reliability?.correlation_policy||{};
    const oracleConfidence=Number(reliability?.oracle?.confidence||0);
    const confidence=Math.round(Number(incident?.confidence??oracleConfidence)*100);
    const state=incident
        ?"CORRELATED INCIDENT"
        :(oracleConfidence<1?"LEARNING BASELINE":"NO ACTIVE INCIDENT");
    const cause=incident?.likely_cause||"No probable shared cause is active";
    const hypothesis=incident?.hypothesis||"AEGIS is watching for related telemetry that should be handled as one incident.";
    const action=incident?.safest_next_action||"Continue passive monitoring; no recovery action is currently required.";
    const verification=incident?.verification_state||"not required";
    const trusted=Number(summary.trusted||0);
    const total=Number(summary.total||0);
    const gaps=Number(summary.gaps||0);

    view.classList.toggle("incident",Boolean(incident));
    view.innerHTML=`
        <div class="ag-head">
            <div><span class="ag-kicker">Project AEGIS · Reliability Engineer</span><h2>Reliability</h2></div>
            <div class="ag-badges"><span>READ-ONLY</span><span>${esc(policy?.policy_id||"AEGIS POLICY")}</span><span class="${gaps?"gap":"trusted"}">${trusted}/${total} TRUSTED</span></div>
        </div>
        <div class="ag-hero">
            <div><span class="ag-state">${esc(state)}</span><h3>${esc(cause)}</h3><p>${esc(hypothesis)}</p></div>
            <div class="ag-confidence"><strong>${confidence}%</strong><span>${incident?"hypothesis confidence":"baseline confidence"}</span></div>
        </div>
        <div class="ag-grid">
            <section><h4>Supporting signals</h4><div class="ag-signals">${signalRows(incident?.supporting_signals)}</div></section>
            <section><h4>Safest next action</h4><p class="ag-action">${esc(action)}</p><div class="ag-verify"><span>Verification</span><strong>${esc(title(verification))}</strong></div></section>
        </div>
        <details class="ag-coverage"><summary>Recovery Coverage Matrix <span>${gaps?`${gaps} gap${gaps===1?"":"s"}`:"complete"}</span></summary>${gapRows(matrix)}</details>
        <p class="ag-safety">Correlation uses ${esc(policy?.semantics||"evidence grouping")}; it retains raw alerts, grants no control authority, and performs no repair.</p>
    `;
}

async function refreshFallback(view){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) throw new Error(`status ${response.status}`);
        render(view,await response.json());
    }catch(_error){
        view.querySelector(".ag-safety")?.replaceChildren("Reliability telemetry is temporarily unavailable. No state or hardware was changed.");
    }
}

function install(){
    const cockpit=document.getElementById("cockpitOverview");
    const grid=document.querySelector("main .grid");
    if(!cockpit&&!grid){window.setTimeout(install,50);return;}
    if(document.getElementById("aegisReliabilityView")) return;

    const style=document.createElement("style");
    style.textContent=`
#aegisReliabilityView{grid-column:1/-1;padding:1.15rem 1.25rem;border-color:rgba(80,205,137,.34);background:linear-gradient(120deg,rgba(6,28,28,.95),rgba(7,14,22,.98) 62%)}#aegisReliabilityView.incident{border-color:rgba(255,200,87,.5);background:linear-gradient(120deg,rgba(58,40,9,.38),rgba(7,14,22,.98) 62%)}.ag-head,.ag-hero{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.ag-head h2{margin:.2rem 0 0}.ag-kicker{color:var(--good);font-size:.65rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase}.incident .ag-kicker{color:var(--warn)}.ag-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.4rem}.ag-badges span{padding:.3rem .48rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted);font-size:.6rem;font-weight:900}.ag-badges .trusted{color:var(--good);border-color:rgba(80,205,137,.35)}.ag-badges .gap{color:var(--warn);border-color:rgba(255,200,87,.4)}.ag-hero{margin-top:1rem;padding:1rem;border:1px solid rgba(143,164,184,.14);border-radius:10px;background:rgba(3,8,13,.42)}.ag-state{color:var(--good);font-size:.65rem;font-weight:900;letter-spacing:.12em}.incident .ag-state{color:var(--warn)}.ag-hero h3{margin:.3rem 0;font-size:1.25rem}.ag-hero p{max-width:760px;margin:0;color:var(--muted);font-size:.82rem;line-height:1.5}.ag-confidence{text-align:right}.ag-confidence strong{display:block;color:var(--good);font-size:1.75rem}.incident .ag-confidence strong{color:var(--warn)}.ag-confidence span{color:var(--muted);font-size:.64rem}.ag-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:.8rem;margin-top:.8rem}.ag-grid section{padding:.8rem;border:1px solid rgba(143,164,184,.14);border-radius:10px}.ag-grid h4{margin:0 0 .55rem;color:var(--muted);font-size:.67rem;letter-spacing:.1em;text-transform:uppercase}.ag-signals{display:grid;gap:.3rem}.ag-signal{display:grid;grid-template-columns:80px minmax(0,1fr) auto;gap:.45rem;font-size:.7rem}.ag-signal span,.ag-signal small{color:var(--muted)}.ag-signal span{font-size:.58rem;font-weight:900;text-transform:uppercase}.ag-action{margin:.1rem 0 .8rem;font-size:.82rem;line-height:1.5}.ag-verify{display:flex;justify-content:space-between;gap:.6rem;padding-top:.6rem;border-top:1px solid rgba(143,164,184,.14);font-size:.7rem}.ag-verify span{color:var(--muted)}.ag-verify strong{color:var(--good)}.ag-coverage{margin-top:.8rem;padding:.65rem .8rem;border:1px solid rgba(143,164,184,.14);border-radius:8px}.ag-coverage summary{cursor:pointer;font-size:.72rem;font-weight:800}.ag-coverage summary span{float:right;color:var(--muted)}.ag-gap,.ag-gap-clear{display:grid;gap:.2rem;padding:.55rem 0;border-bottom:1px solid rgba(143,164,184,.1);font-size:.7rem}.ag-gap span{color:var(--muted)}.ag-gap-clear{color:var(--good)}.ag-empty,.ag-safety{color:var(--muted);font-size:.68rem}.ag-safety{margin:.7rem 0 0;line-height:1.45}@media(max-width:760px){#aegisReliabilityView{padding:1rem}.ag-head,.ag-hero{display:block}.ag-badges{justify-content:flex-start;margin-top:.6rem}.ag-confidence{margin-top:.7rem;text-align:left}.ag-grid{grid-template-columns:1fr}.ag-signal{grid-template-columns:70px minmax(0,1fr)}.ag-signal small{grid-column:2}.ag-coverage summary span{display:block;float:none;margin-top:.25rem}}
`;
    document.head.appendChild(style);

    const view=document.createElement("article");
    view.id="aegisReliabilityView";
    view.className="card";
    view.setAttribute("aria-live","polite");
    view.innerHTML='<p class="ag-safety">Waiting for the first reliability snapshot.</p>';
    const host=cockpit||grid;
    const health=host.querySelector(".health-command");
    if(health) health.insertAdjacentElement("afterend",view);
    else host.prepend(view);

    let receivedSharedStatus=false;
    window.addEventListener("truepanel:status",event=>{
        const payload=event?.detail;
        if(!payload||typeof payload!=="object") return;
        receivedSharedStatus=true;
        render(view,payload);
    });

    window.setTimeout(()=>{
        if(!receivedSharedStatus) refreshFallback(view);
    },500);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
