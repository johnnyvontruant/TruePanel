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

function healthTarget(label){
    const key=String(label||"").trim().toLowerCase();
    const targets={
        cooling:document.getElementById("fanActiveProfile")?.closest("article"),
        thermal:document.getElementById("fanThermalTemperature")?.closest("article"),
        storage:document.getElementById("pools")?.closest("article"),
        network:document.getElementById("network")?.closest("article"),
        "front panel":document.querySelector(".lcd-panel"),
        services:document.getElementById("configMode")?.closest("article"),
    };
    return targets[key]||null;
}

function installHealthAnnunciatorNavigation(){
    const topbar=document.querySelector(".topbar");
    const subsystems=document.getElementById("healthSubsystems");
    const healthCard=document.querySelector(".health-command");
    const connection=document.getElementById("connection");
    if(!topbar||!subsystems||!healthCard||!connection) return;
    if(subsystems.classList.contains("gc-health-annunciators")) return;

    subsystems.classList.add("gc-health-annunciators");
    subsystems.setAttribute("role","navigation");
    subsystems.setAttribute("aria-label","System health navigation");
    topbar.insertBefore(subsystems,connection);
    document.body.classList.add("gc-health-nav");
    healthCard.hidden=true;

    const annotate=()=>{
        [...subsystems.children].forEach(item=>{
            const label=String(item.querySelector(".health-name")?.textContent||"").trim();
            const state=String(item.querySelector("strong")?.textContent||"unknown").trim();
            if(!label) return;
            item.dataset.gcHealthTarget=label.toLowerCase();
            item.setAttribute("role","button");
            item.tabIndex=0;
            item.setAttribute("aria-label",`${label}: ${state}. Jump to ${label} details.`);
            item.title=`Open ${label} details`;
        });
    };

    const openDetailsAncestors=target=>{
        let parent=target?.parentElement;
        while(parent){
            if(parent.tagName==="DETAILS") parent.open=true;
            parent=parent.parentElement;
        }
    };

    const jump=item=>{
        const label=String(item?.querySelector(".health-name")?.textContent||"").trim();
        const target=healthTarget(label);
        if(!target) return;
        openDetailsAncestors(target);
        const reduced=window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches===true;
        target.classList.add("gc-health-target-focus");
        target.scrollIntoView({behavior:reduced?"auto":"smooth",block:"center"});
        window.setTimeout(()=>target.classList.remove("gc-health-target-focus"),1300);
    };

    subsystems.addEventListener("click",event=>{
        jump(event.target.closest(".health-subsystem"));
    });
    subsystems.addEventListener("keydown",event=>{
        if(event.key!=="Enter"&&event.key!==" ") return;
        const item=event.target.closest(".health-subsystem");
        if(!item) return;
        event.preventDefault();
        jump(item);
    });

    new MutationObserver(annotate).observe(subsystems,{
        childList:true,
        subtree:true,
        characterData:true,
    });
    annotate();
}

function install(){
    const grid=document.querySelector("main .grid");
    if(!grid){setTimeout(install,50);return;}
    if(document.getElementById("glassCockpitSituation")) return;
    const style=document.createElement("style");
    style.textContent=`:root{--gc-focus:var(--warn);--gc-panel:var(--panel-solid);--gc-border:color-mix(in srgb,var(--edge) 28%,transparent)}
/* gc-ambient-start: atmosphere only; semantic status colors are forbidden here */
:root{--gc-ambient-a:#e3e6ed;--gc-ambient-b:#cfd4de;--gc-ambient-haze:rgba(91,79,129,.12);--gc-ambient-vignette:rgba(35,37,49,.08);--gc-ambient-grid:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='104' height='60' viewBox='0 0 104 60'%3E%3Cpath d='M0 15L26 0L52 15L78 0L104 15M0 45L26 60L52 45L78 60L104 45M0 15V45M52 15V45M104 15V45' fill='none' stroke='%23786d95' stroke-opacity='.17' stroke-width='1'/%3E%3C/svg%3E")}
:root[data-theme="dark"]{--gc-ambient-a:#14151d;--gc-ambient-b:#08090f;--gc-ambient-haze:rgba(103,82,160,.14);--gc-ambient-vignette:rgba(0,0,0,.30)}
body{background:var(--gc-ambient-grid),radial-gradient(circle at 50% -12%,var(--gc-ambient-haze),transparent 46%),radial-gradient(ellipse at center,transparent 42%,var(--gc-ambient-vignette) 100%),linear-gradient(180deg,var(--gc-ambient-a),var(--gc-ambient-b))!important;background-size:144px 83px,auto,auto,auto!important;background-attachment:fixed,fixed,fixed,fixed!important}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--gc-ambient-a:#14151d;--gc-ambient-b:#08090f;--gc-ambient-haze:rgba(103,82,160,.14);--gc-ambient-vignette:rgba(0,0,0,.30)}}
/* gc-ambient-end */
/* gc-liquid-glass-start: optical material only; semantic status colors are forbidden here */
:root{--gc-glass-specular:rgba(255,255,255,.36);--gc-glass-side:rgba(255,255,255,.11);--gc-glass-rim:rgba(112,101,149,.13);--gc-glass-lower:rgba(42,45,60,.13);--gc-glass-shadow:rgba(31,35,48,.18);--gc-glass-wash:rgba(255,255,255,.065)}
:root[data-theme="dark"]{--gc-glass-specular:rgba(255,255,255,.14);--gc-glass-side:rgba(255,255,255,.045);--gc-glass-rim:rgba(112,94,160,.085);--gc-glass-lower:rgba(0,0,0,.24);--gc-glass-shadow:rgba(0,0,0,.26);--gc-glass-wash:rgba(255,255,255,.012)}
body.cockpit-polished .card,body.cockpit-polished .cockpit-drawer,body.cockpit-polished .cockpit-maintenance-drawer{position:relative;isolation:isolate;backdrop-filter:blur(32px) saturate(132%) contrast(103%);-webkit-backdrop-filter:blur(32px) saturate(132%) contrast(103%)}
body.cockpit-polished .card::after,body.cockpit-polished .cockpit-drawer::after,body.cockpit-polished .cockpit-maintenance-drawer::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;z-index:0;background:linear-gradient(var(--gc-glass-wash),var(--gc-glass-wash)),radial-gradient(120% 86% at 0% 0%,var(--gc-glass-specular),transparent 42%),linear-gradient(145deg,var(--gc-glass-side) 0,transparent 24%,transparent 76%,var(--gc-glass-rim) 100%);box-shadow:inset 0 1px 0 var(--gc-glass-specular),inset 1px 0 0 var(--gc-glass-side),inset 0 -1px 0 var(--gc-glass-lower),0 12px 28px var(--gc-glass-shadow)}
body.cockpit-polished .card>*,body.cockpit-polished .cockpit-drawer>*,body.cockpit-polished .cockpit-maintenance-drawer>*{position:relative;z-index:1}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){--gc-glass-specular:rgba(255,255,255,.14);--gc-glass-side:rgba(255,255,255,.045);--gc-glass-rim:rgba(112,94,160,.085);--gc-glass-lower:rgba(0,0,0,.24);--gc-glass-shadow:rgba(0,0,0,.26);--gc-glass-wash:rgba(255,255,255,.012)}}
@media(forced-colors:active){body.cockpit-polished .card::after,body.cockpit-polished .cockpit-drawer::after,body.cockpit-polished .cockpit-maintenance-drawer::after{display:none}}
/* gc-liquid-glass-end */
/* gc-health-nav-start: live Health Intelligence node, moved rather than duplicated */
body.gc-health-nav .topbar{gap:.65rem}
body.gc-health-nav .topbar-title{margin-right:0;flex:0 1 260px}
.gc-health-annunciators{display:flex;grid-template-columns:none;align-items:center;gap:.32rem;min-width:0;max-width:min(720px,56vw);margin:0 0 0 auto;overflow-x:auto;padding:0;scrollbar-width:none}
.gc-health-annunciators::-webkit-scrollbar{display:none}
.gc-health-annunciators .health-subsystem{display:inline-flex;align-items:center;gap:.32rem;flex:0 0 auto;min-width:max-content;margin:0;padding:.38rem .52rem;border-radius:999px;background:color-mix(in srgb,var(--panel-solid) 38%,transparent);cursor:pointer;backdrop-filter:blur(18px) saturate(120%);-webkit-backdrop-filter:blur(18px) saturate(120%)}
.gc-health-annunciators .health-subsystem .health-dot{grid-row:auto;width:.44rem;height:.44rem}
.gc-health-annunciators .health-name{font-size:.59rem;letter-spacing:.055em}
.gc-health-annunciators .health-subsystem strong{font-size:.61rem;line-height:1}
.gc-health-annunciators .health-subsystem:hover{background:color-mix(in srgb,var(--panel-solid) 58%,transparent);border-color:var(--edge-strong)}
.gc-health-annunciators .health-subsystem:focus-visible{outline:2px solid var(--text);outline-offset:2px}
.gc-health-target-focus{scroll-margin-top:8rem;outline:2px solid color-mix(in srgb,var(--text) 32%,transparent);outline-offset:3px;animation:gcHealthFocus 1.2s ease-out}
@keyframes gcHealthFocus{0%{box-shadow:0 0 0 5px color-mix(in srgb,var(--text) 12%,transparent),var(--shadow-lg)}100%{box-shadow:var(--shadow)}}
@media(prefers-reduced-motion:reduce){.gc-health-target-focus{animation:none}}
@media(max-width:760px){body.gc-health-nav .topbar{flex-wrap:wrap;gap:.45rem .6rem}body.gc-health-nav .topbar-title{flex:1 1 calc(100% - 8rem)}.gc-health-annunciators{order:4;flex:1 0 100%;max-width:none;margin-left:0;padding-bottom:.1rem}.gc-health-annunciators .health-subsystem{min-height:36px}}
/* gc-health-nav-end */
#glassCockpitSituation{grid-column:1/-1;padding:1rem 1.15rem;border-color:var(--gc-border);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 58%,transparent),color-mix(in srgb,var(--panel-solid) 58%,transparent));backdrop-filter:blur(32px) saturate(132%) contrast(103%);-webkit-backdrop-filter:blur(32px) saturate(132%) contrast(103%)}.gc-now{display:grid;grid-template-columns:.55fr 1.2fr 1.4fr .75fr;gap:.7rem}.gc-now>div,.gc-domains section,.gc-activity{display:grid;align-content:start;gap:.3rem;min-width:0;padding:.7rem;border:1px solid var(--gc-border);border-radius:8px}.gc-now small,.gc-domains small,.gc-activity small{color:var(--muted);font-size:.62rem;font-weight:850;letter-spacing:.1em}.gc-now strong,.gc-domains strong,.gc-activity strong{overflow-wrap:anywhere}.gc-state{color:var(--warn)}.gc-activity{margin-top:.7rem;grid-template-columns:minmax(0,1fr);background:color-mix(in srgb,var(--panel-solid) 70%,transparent)}.gc-activity-active{background:color-mix(in srgb,var(--accent-soft) 36%,transparent)}.gc-activity-idle,.gc-activity-unavailable{border-color:color-mix(in srgb,var(--edge) 18%,transparent);background:color-mix(in srgb,var(--panel-solid) 48%,transparent)}.gc-activity span{color:var(--muted);font-size:.68rem}.gc-domains{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin-top:.7rem}.gc-domains span,.gc-trend{color:var(--muted);font-size:.68rem}.gc-domains svg{width:100%;height:30px}.gc-domains polyline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}#glassCockpitSituation details{margin-top:.65rem}#glassCockpitSituation summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted)}:focus-visible{outline:3px solid var(--gc-focus)!important;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}@media(max-width:760px){.gc-now,.gc-domains{grid-template-columns:1fr}.gc-now>div,.gc-domains section,.gc-activity{padding:.75rem}#glassCockpitSituation{padding:.85rem}}`;
    document.head.appendChild(style);
    installHealthAnnunciatorNavigation();
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
