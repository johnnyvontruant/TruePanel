(()=>{
"use strict";

const esc=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
const number=value=>Number.isFinite(Number(value))?Number(value):null;
const first=(...values)=>values.find(value=>value!==undefined&&value!==null&&value!=="");
const array=value=>Array.isArray(value)?value:[];

function trend(values){
    const points=(Array.isArray(values)?values:[]).map(number).filter(value=>value!==null).slice(-8);
    if(points.length<2) return {word:"trend unavailable",symbol:"—",points:""};
    const delta=points.at(-1)-points[0];
    const word=Math.abs(delta)<.5?"steady":delta>0?"rising":"falling";
    const symbol=word==="rising"?"↗":word==="falling"?"↘":"→";
    const low=Math.min(...points); const high=Math.max(...points); const span=Math.max(1,high-low);
    const plotted=points.map((value,index)=>`${index*100/(points.length-1)},${30-(value-low)*28/span}`).join(" ");
    return {word,symbol,points:plotted};
}

function spark(data,label){
    if(!data.points) return `<span class="gc-trend">${esc(data.symbol)} ${esc(data.word)}</span>`;
    return `<span class="gc-trend">${esc(data.symbol)} ${esc(data.word)}</span><svg viewBox="0 0 100 32" role="img" aria-label="${esc(label)}: ${esc(data.word)}"><polyline points="${data.points}"/></svg>`;
}

function render(view,payload){
    const health=payload?.health||{};
    const incident=payload?.reliability?.active_incident||null;
    const flight=payload?.reliability?.flight_director||{};
    const flightBound=flight?.presentation_scope==="active_incident"
        && flight?.applies_to_active_incident===true
        && Boolean(incident?.incident_id)
        && flight?.incident_id===incident?.incident_id;
    const thermal=payload?.thermal||payload?.cooling||{};
    const storage=payload?.storage||{};
    const drives=Array.isArray(storage.drives)?storage.drives:Array.isArray(storage.temperatures)?storage.temperatures:[];
    const hottest=drives.reduce((best,item)=>number(first(item?.temperature,item?.temperature_c,item?.temp))>(number(first(best?.temperature,best?.temperature_c,best?.temp))??-Infinity)?item:best,{});
    const hottestValue=number(first(hottest?.temperature,hottest?.temperature_c,hottest?.temp));
    const fan=number(first(thermal?.fan_rpm,thermal?.rpm,payload?.fans?.[0]?.rpm));
    const fanTrend=trend(first(thermal?.fan_history,thermal?.rpm_history,[]));
    const driveTrend=trend(first(hottest?.history,storage?.temperature_history,[]));
    const pools=Array.isArray(storage.pools)?storage.pools:[];
    const pool=pools[0]||{};
    const overall=String(first(health.overall,health.state,incident?"ATTENTION":"UNKNOWN")).toUpperCase();
    const cause=incident?.likely_cause||"No active correlated incident";
    const move=(flightBound&&flight?.safest_action)||incident?.safest_next_action||"Continue passive monitoring";
    const verify=(flightBound&&flight?.verification_signature?.status)||incident?.verification_state||"not required";
    view.innerHTML=`<div class="gc-now"><div><small>NOW</small><strong class="gc-state">${esc(overall)}</strong></div><div><small>WHY</small><strong>${esc(cause)}</strong></div><div><small>SAFEST MOVE</small><strong>${esc(move)}</strong></div><div><small>PROOF</small><strong>${esc(verify)}</strong></div></div><div class="gc-domains"><section><small>COOLING</small><strong>${fan===null?"RPM unknown":`${fan.toLocaleString()} RPM`}</strong>${spark(fanTrend,"Fan delivery")}</section><section><small>HOTTEST DRIVE</small><strong>${hottestValue===null?"Temperature unknown":`${hottestValue}°C`} · Bay ${esc(first(hottest?.bay,"unknown"))}</strong>${spark(driveTrend,"Hottest drive temperature")}</section><section><small>STORAGE</small><strong>${esc(first(pool?.name,"Pool unknown"))} · ${esc(first(pool?.health,pool?.status,"state unknown"))}</strong><span>Redundancy ${esc(first(pool?.redundancy,"unknown"))}</span></section></div><details><summary>Evidence, history, and advanced diagnostics</summary><p>Safety-critical incident, action, and proof remain outside this drawer. Trend graphics have text alternatives; unknown topology stays unknown.</p></details>`;
}

function pathMarkup(item){
    const path=array(item?.via);
    if(!path.length) return "";
    return `<code class="sentinel-path">${esc(path.join(" → "))}</code>`;
}

function impactMarkup(items){
    if(!items.length) return `<p class="sentinel-empty">No proved downstream objects in this explanation.</p>`;
    return `<ul class="sentinel-list">${items.map(item=>`<li><div><strong>${esc(item?.label||item?.node_id||"Unknown object")}</strong><span>${esc(String(item?.kind||"object").replaceAll("_"," "))}${item?.state?` · ${esc(item.state)}`:""}</span></div>${pathMarkup(item)}</li>`).join("")}</ul>`;
}

function protectedMarkup(items){
    if(!items.length) return `<p class="sentinel-empty">No verified independent backup evidence is in the proved path.</p>`;
    return `<ul class="sentinel-list">${items.map(item=>`<li><div><strong>${esc(item?.label||item?.node_id||"Backup evidence")}</strong><span>${esc(item?.statement||item?.state||"VERIFIED")}</span></div>${array(item?.provenance?.path).length?`<code class="sentinel-path">${esc(item.provenance.path.join(" → "))}</code>`:""}</li>`).join("")}</ul>`;
}

function unknownMarkup(items){
    if(!items.length) return `<p class="sentinel-empty">No additional unknowns were reported for this explanation.</p>`;
    return `<ul class="sentinel-unknowns">${items.map(item=>`<li>${esc(item)}</li>`).join("")}</ul>`;
}

function recoveryMarkup(recovery){
    const refs=array(recovery?.references);
    if(!recovery?.available||!refs.length){
        return `<p class="sentinel-empty">${esc(recovery?.reason||"No evidence-bound Pathfinder reference is available for this source device.")}</p>`;
    }
    return `<div class="sentinel-recovery-note">Reference only · no repair authority</div><ul class="sentinel-list">${refs.map(item=>{const verification=item?.verification||{};const gate=item?.action_gate||{};const blocked=array(gate?.blocked_by);return `<li><div><strong>${esc(item?.title||item?.code||"Pathfinder guidance")}</strong><span>${esc(item?.code||"")} · ${esc(item?.severity||"warning")}</span></div><p>${esc(item?.explanation||"Existing Pathfinder guidance is linked by exact device evidence.")}</p><div class="sentinel-reference-meta"><span>Verification: ${esc(verification?.strategy||"not specified")} · ${esc(verification?.status||"pending")}</span><span>Physical service ready: ${gate?.physical_service_ready===true?"yes":"no"}</span><span>Destructive actions ready: ${gate?.destructive_actions_ready===true?"yes":"no"}</span>${blocked.length?`<span>Blocked by: ${esc(blocked.join(", "))}</span>`:""}</div></li>`;}).join("")}</ul>`;
}

function explanationMarkup(explanation,index){
    const state=String(explanation?.state||"HOLD").toUpperCase();
    const impacts=array(explanation?.known_impact);
    const protectedItems=array(explanation?.protected_items);
    const unknowns=array(explanation?.unknowns);
    const recovery=explanation?.recovery||{};
    const recoveryRefs=array(recovery?.references);
    return `<section class="sentinel-explanation"><div class="sentinel-lead"><span class="sentinel-state sentinel-${esc(state.toLowerCase())}">${esc(state)}</span><div><strong>${esc(explanation?.headline||"SENTINEL impact explanation")}</strong><p>${esc(explanation?.summary||"Deterministic explanation unavailable.")}</p></div></div><div class="sentinel-counts" aria-label="Explanation evidence counts"><span><b>${impacts.length}</b> proved impact</span><span><b>${protectedItems.length}</b> verified backup</span><span><b>${unknowns.length}</b> unknown</span><span><b>${recoveryRefs.length}</b> recovery ref</span></div><details><summary>Evidence, provenance, and recovery references</summary><div class="sentinel-drawer"><h4>Known impact</h4>${impactMarkup(impacts)}<h4>Verified protection evidence</h4>${protectedMarkup(protectedItems)}<h4>Pathfinder recovery references</h4>${recoveryMarkup(recovery)}<h4>Unknowns</h4>${unknownMarkup(unknowns)}<p class="sentinel-guard">${esc(explanation?.language_guard||"Objects outside the proved blast radius remain unclassified.")}</p></div></details></section>`;
}

function renderSentinel(view,payload){
    const sentinel=payload?.sentinel||{};
    const explanations=array(sentinel?.explanations);
    const assessment=sentinel?.assessment||{};
    const assessmentState=String(assessment?.state||"STANDBY").toUpperCase();

    if(!explanations.length){
        const unknowns=array(assessment?.unknowns);
        view.innerHTML=`<header class="sentinel-header"><div><small>SENTINEL</small><h3>Flight Director</h3></div><span class="sentinel-state sentinel-standby">STANDBY</span></header><p class="sentinel-standby-copy">No active SENTINEL impact explanation is available. The evidence engine is standing by. This is not an all-clear assertion.</p>${unknowns.length?`<details><summary>Current evidence limits (${unknowns.length})</summary>${unknownMarkup(unknowns)}</details>`:""}`;
        return;
    }

    const proved=explanations.reduce((total,item)=>total+array(item?.known_impact).length,0);
    const recoveryRefs=explanations.reduce((total,item)=>total+array(item?.recovery?.references).length,0);
    const applications=explanations.reduce((total,item)=>total+array(item?.consequences?.applications).length,0);
    view.innerHTML=`<details class="sentinel-master"><summary class="sentinel-master-summary"><div class="sentinel-master-title"><span class="sentinel-state sentinel-${esc(assessmentState.toLowerCase())}">${esc(assessmentState)}</span><div><small>SENTINEL</small><strong>Flight Director</strong></div></div><div class="sentinel-master-counts"><span>${proved} proved</span><span>${applications} app${applications===1?"":"s"}</span><span>${recoveryRefs} recovery</span></div></summary><div class="sentinel-master-body"><header class="sentinel-header"><div><small>SENTINEL</small><h3>Flight Director</h3></div><div class="sentinel-header-state"><span>${explanations.length} active explanation${explanations.length===1?"":"s"}</span><span class="sentinel-assessment">Assessment ${esc(assessmentState)}</span></div></header>${explanations.map(explanationMarkup).join("")}</div></details>`;
}

function install(){
    const grid=document.querySelector("main .grid");
    if(!grid){setTimeout(install,50);return;}
    if(document.getElementById("glassCockpitSituation")) return;
    const style=document.createElement("style");
    style.textContent=`:root{--gc-focus:var(--warn);--gc-panel:var(--panel-solid);--gc-border:color-mix(in srgb,var(--edge) 28%,transparent)}#glassCockpitSituation,#sentinelFlightDirector{grid-column:1/-1;padding:1rem 1.15rem;border-color:var(--gc-border);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 72%,transparent),color-mix(in srgb,var(--panel-solid) 72%,transparent));backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.gc-now{display:grid;grid-template-columns:.55fr 1.2fr 1.4fr .75fr;gap:.7rem}.gc-now>div,.gc-domains section{display:grid;align-content:start;gap:.3rem;min-width:0;padding:.7rem;border:1px solid var(--gc-border);border-radius:8px}.gc-now small,.gc-domains small{color:var(--muted);font-size:.62rem;font-weight:850;letter-spacing:.1em}.gc-now strong,.gc-domains strong{overflow-wrap:anywhere}.gc-state{color:var(--warn)}.gc-domains{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin-top:.7rem}.gc-domains span,.gc-trend{color:var(--muted);font-size:.68rem}.gc-domains svg{width:100%;height:30px}.gc-domains polyline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}#glassCockpitSituation details,#sentinelFlightDirector details{margin-top:.65rem}#glassCockpitSituation summary,#sentinelFlightDirector summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted)}.sentinel-master{margin:0!important}.sentinel-master-summary{min-height:58px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:.8rem!important;padding:.15rem 0;cursor:pointer;color:var(--text)!important}.sentinel-master-summary::-webkit-details-marker{display:none}.sentinel-master-title{display:flex;align-items:center;gap:.65rem;min-width:0}.sentinel-master-title small{display:block;color:var(--accent);font-size:.6rem;font-weight:900;letter-spacing:.14em}.sentinel-master-title strong{display:block;margin-top:.08rem;overflow-wrap:anywhere}.sentinel-master-counts{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.35rem;color:var(--muted);font-size:.64rem}.sentinel-master-counts span{padding:.26rem .42rem;border:1px solid var(--gc-border);border-radius:6px}.sentinel-master-body{padding-top:.7rem;border-top:1px solid var(--gc-border)}.sentinel-header{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.75rem}.sentinel-header small{display:block;color:var(--accent);font-size:.62rem;font-weight:900;letter-spacing:.16em}.sentinel-header h3{margin:.15rem 0 0}.sentinel-header-state{display:flex;align-items:flex-end;flex-direction:column;gap:.2rem;color:var(--muted);font-size:.68rem}.sentinel-assessment{font-size:.62rem}.sentinel-explanation{padding:.8rem;border:1px solid var(--gc-border);border-radius:9px}.sentinel-explanation+.sentinel-explanation{margin-top:.7rem}.sentinel-lead{display:grid;grid-template-columns:auto minmax(0,1fr);gap:.75rem;align-items:start}.sentinel-lead p,.sentinel-standby-copy{margin:.3rem 0 0;color:var(--muted);line-height:1.45}.sentinel-state{display:inline-flex;align-items:center;justify-content:center;min-height:28px;padding:.2rem .55rem;border:1px solid var(--gc-border);border-radius:999px;font-size:.61rem;font-weight:900;letter-spacing:.08em}.sentinel-review,.sentinel-hold{color:var(--warn)}.sentinel-standby{color:var(--muted)}.sentinel-counts{display:flex;flex-wrap:wrap;gap:.45rem;margin:.75rem 0 0}.sentinel-counts span{padding:.32rem .5rem;border:1px solid var(--gc-border);border-radius:6px;color:var(--muted);font-size:.65rem}.sentinel-counts b{color:var(--text)}.sentinel-drawer h4{margin:.9rem 0 .35rem;font-size:.72rem}.sentinel-list,.sentinel-unknowns{display:grid;gap:.45rem;margin:.35rem 0;padding-left:1.15rem}.sentinel-list li{min-width:0}.sentinel-list li>div{display:flex;gap:.35rem .55rem;align-items:baseline;flex-wrap:wrap}.sentinel-list li p{margin:.25rem 0;color:var(--muted);font-size:.68rem}.sentinel-list li span,.sentinel-unknowns,.sentinel-empty,.sentinel-guard,.sentinel-reference-meta{color:var(--muted);font-size:.68rem}.sentinel-path{display:block;max-width:100%;margin-top:.2rem;padding:.28rem .4rem;border-radius:5px;background:color-mix(in srgb,var(--panel-solid) 82%,transparent);white-space:normal;overflow-wrap:anywhere;font-size:.62rem}.sentinel-reference-meta{display:grid;gap:.2rem;margin-top:.3rem}.sentinel-recovery-note{margin:.35rem 0;padding:.4rem .5rem;border:1px solid var(--gc-border);border-radius:6px;color:var(--warn);font-size:.64rem;font-weight:800;letter-spacing:.04em}.sentinel-guard{margin:.9rem 0 0;padding-top:.65rem;border-top:1px solid var(--gc-border)}:focus-visible{outline:3px solid var(--gc-focus)!important;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}@media(max-width:760px){.sentinel-master-summary{align-items:flex-start!important}.sentinel-master-counts{max-width:48%;}.gc-now,.gc-domains{grid-template-columns:1fr}.gc-now>div,.gc-domains section{padding:.75rem}#glassCockpitSituation,#sentinelFlightDirector{padding:.85rem}.sentinel-header{align-items:flex-start}.sentinel-header-state{align-items:flex-end;text-align:right}.sentinel-lead{grid-template-columns:1fr}.sentinel-state{justify-self:start}.sentinel-list li>div{display:grid}.sentinel-counts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.sentinel-counts span{text-align:center}}@media(max-width:480px){.sentinel-counts{grid-template-columns:1fr}.sentinel-header{display:grid}.sentinel-header-state{align-items:flex-start;text-align:left}}`;
    document.head.appendChild(style);
    const view=document.createElement("article");
    view.id="glassCockpitSituation"; view.className="card";
    view.setAttribute("aria-label","Mission Control situation summary");
    view.innerHTML="<p>Waiting for the shared status stream.</p>";
    const health=grid.querySelector(".health-command");
    (health||grid.firstElementChild)?.insertAdjacentElement("afterend",view);

    const sentinelView=document.createElement("article");
    sentinelView.id="sentinelFlightDirector"; sentinelView.className="card";
    sentinelView.setAttribute("aria-label","SENTINEL Flight Director explanation");
    sentinelView.innerHTML="<p>Waiting for SENTINEL evidence.</p>";
    view.insertAdjacentElement("afterend",sentinelView);

    window.addEventListener("truepanel:status",event=>{
        if(event?.detail&&typeof event.detail==="object"){
            render(view,event.detail);
            renderSentinel(sentinelView,event.detail);
        }
    });
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true}); else install();
})();
