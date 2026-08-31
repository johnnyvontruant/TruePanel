(()=>{
"use strict";

const esc=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
const number=value=>Number.isFinite(Number(value))?Number(value):null;
const first=(...values)=>values.find(value=>value!==undefined&&value!==null&&value!=="");

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

function activity(payload){
    const block=payload?.activity;
    if(!block||typeof block!=="object"||block.unavailable===true){
        return {tone:"unavailable",label:"ACTIVITY UNAVAILABLE",detail:"OBSERVATORY evidence unavailable"};
    }
    const observations=Array.isArray(block.observations)?block.observations:[];
    if(!observations.length){
        return {tone:"idle",label:"NO OBSERVED ACTIVITY",detail:"No normalized workload evidence"};
    }
    const item=observations[0]||{};
    const progress=number(item.progress);
    const bounded=progress===null?null:Math.max(0,Math.min(1,progress));
    const progressText=bounded===null?"":` • ${Math.round(bounded*100)}%`;
    const extra=observations.length>1?` • +${observations.length-1} more`:"";
    return {
        tone:"active",
        label:`${first(item.title,item.kind,"Observed activity")}${progressText}${extra}`,
        detail:first(item.subtitle,item.source,"Normalized activity evidence"),
    };
}

function render(view,payload){
    const health=payload?.health||{};
    const incident=payload?.reliability?.active_incident||null;
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
    const move=incident?.safest_next_action||"Continue passive monitoring";
    const verify=incident?.verification_state||"not required";
    const currentActivity=activity(payload);
    view.innerHTML=`<div class="gc-now"><div><small>NOW</small><strong class="gc-state">${esc(overall)}</strong></div><div><small>WHY</small><strong>${esc(cause)}</strong></div><div><small>SAFEST MOVE</small><strong>${esc(move)}</strong></div><div><small>PROOF</small><strong>${esc(verify)}</strong></div></div><div class="gc-activity gc-activity-${esc(currentActivity.tone)}"><small>CURRENT ACTIVITY</small><strong>${esc(currentActivity.label)}</strong><span>${esc(currentActivity.detail)}</span></div><div class="gc-domains"><section><small>COOLING</small><strong>${fan===null?"RPM unknown":`${fan.toLocaleString()} RPM`}</strong>${spark(fanTrend,"Fan delivery")}</section><section><small>HOTTEST DRIVE</small><strong>${hottestValue===null?"Temperature unknown":`${hottestValue}°C`} · Bay ${esc(first(hottest?.bay,"unknown"))}</strong>${spark(driveTrend,"Hottest drive temperature")}</section><section><small>STORAGE</small><strong>${esc(first(pool?.name,"Pool unknown"))} · ${esc(first(pool?.health,pool?.status,"state unknown"))}</strong><span>Redundancy ${esc(first(pool?.redundancy,"unknown"))}</span></section></div><details><summary>Evidence, history, and advanced diagnostics</summary><p>Safety-critical incident, action, and proof remain outside this drawer. Trend graphics have text alternatives; unknown topology stays unknown.</p></details>`;
}

function install(){
    const grid=document.querySelector("main .grid");
    if(!grid){setTimeout(install,50);return;}
    if(document.getElementById("glassCockpitSituation")) return;
    const style=document.createElement("style");
    style.textContent=`:root{--gc-focus:var(--warn);--gc-panel:var(--panel-solid);--gc-border:color-mix(in srgb,var(--edge) 28%,transparent)}
/* gc-ambient-start: atmosphere only; semantic status colors are forbidden here */
:root{--gc-ambient-a:#eef0f5;--gc-ambient-b:#dfe2e9;--gc-ambient-haze:rgba(91,79,129,.08);--gc-ambient-vignette:rgba(35,37,49,.05);--gc-ambient-grid:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='104' height='60' viewBox='0 0 104 60'%3E%3Cpath d='M0 15L26 0L52 15L78 0L104 15M0 45L26 60L52 45L78 60L104 45M0 15V45M52 15V45M104 15V45' fill='none' stroke='%23786d95' stroke-opacity='.11' stroke-width='1'/%3E%3C/svg%3E")}
:root[data-theme="dark"]{--gc-ambient-a:#14151d;--gc-ambient-b:#08090f;--gc-ambient-haze:rgba(103,82,160,.11);--gc-ambient-vignette:rgba(0,0,0,.28)}
body{background:var(--gc-ambient-grid),radial-gradient(circle at 50% -12%,var(--gc-ambient-haze),transparent 46%),radial-gradient(ellipse at center,transparent 42%,var(--gc-ambient-vignette) 100%),linear-gradient(180deg,var(--gc-ambient-a),var(--gc-ambient-b))!important;background-size:156px 90px,auto,auto,auto!important;background-attachment:fixed,fixed,fixed,fixed!important}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--gc-ambient-a:#14151d;--gc-ambient-b:#08090f;--gc-ambient-haze:rgba(103,82,160,.11);--gc-ambient-vignette:rgba(0,0,0,.28)}}
/* gc-ambient-end */
#glassCockpitSituation{grid-column:1/-1;padding:1rem 1.15rem;border-color:var(--gc-border);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 72%,transparent),color-mix(in srgb,var(--panel-solid) 72%,transparent));backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.gc-now{display:grid;grid-template-columns:.55fr 1.2fr 1.4fr .75fr;gap:.7rem}.gc-now>div,.gc-domains section,.gc-activity{display:grid;align-content:start;gap:.3rem;min-width:0;padding:.7rem;border:1px solid var(--gc-border);border-radius:8px}.gc-now small,.gc-domains small,.gc-activity small{color:var(--muted);font-size:.62rem;font-weight:850;letter-spacing:.1em}.gc-now strong,.gc-domains strong,.gc-activity strong{overflow-wrap:anywhere}.gc-state{color:var(--warn)}.gc-activity{margin-top:.7rem;grid-template-columns:minmax(0,1fr);background:color-mix(in srgb,var(--panel-solid) 70%,transparent)}.gc-activity-active{background:color-mix(in srgb,var(--accent-soft) 36%,transparent)}.gc-activity-idle,.gc-activity-unavailable{border-color:color-mix(in srgb,var(--edge) 18%,transparent);background:color-mix(in srgb,var(--panel-solid) 48%,transparent)}.gc-activity span{color:var(--muted);font-size:.68rem}.gc-domains{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin-top:.7rem}.gc-domains span,.gc-trend{color:var(--muted);font-size:.68rem}.gc-domains svg{width:100%;height:30px}.gc-domains polyline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}#glassCockpitSituation details{margin-top:.65rem}#glassCockpitSituation summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted)}:focus-visible{outline:3px solid var(--gc-focus)!important;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}@media(max-width:760px){.gc-now,.gc-domains{grid-template-columns:1fr}.gc-now>div,.gc-domains section,.gc-activity{padding:.75rem}#glassCockpitSituation{padding:.85rem}}`;
    document.head.appendChild(style);
    const view=document.createElement("article");
    view.id="glassCockpitSituation"; view.className="card";
    view.setAttribute("aria-label","Mission Control situation summary");
    view.innerHTML="<p>Waiting for the shared status stream.</p>";
    const health=grid.querySelector(".health-command");
    (health||grid.firstElementChild)?.insertAdjacentElement("afterend",view);
    window.addEventListener("truepanel:status",event=>{
        if(event?.detail&&typeof event.detail==="object") render(view,event.detail);
    });
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true}); else install();
})();
