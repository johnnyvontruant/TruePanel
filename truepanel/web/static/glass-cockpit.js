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

function install(){
    const grid=document.querySelector("main .grid");
    if(!grid){setTimeout(install,50);return;}
    if(document.getElementById("glassCockpitSituation")) return;
    const style=document.createElement("style");
    style.textContent=`:root{--gc-focus:var(--warn);--gc-panel:var(--panel-solid);--gc-border:color-mix(in srgb,var(--edge) 28%,transparent)}#glassCockpitSituation{grid-column:1/-1;padding:1rem 1.15rem;border-color:var(--gc-border);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 72%,transparent),color-mix(in srgb,var(--panel-solid) 72%,transparent));backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.gc-now{display:grid;grid-template-columns:.55fr 1.2fr 1.4fr .75fr;gap:.7rem}.gc-now>div,.gc-domains section{display:grid;align-content:start;gap:.3rem;min-width:0;padding:.7rem;border:1px solid var(--gc-border);border-radius:8px}.gc-now small,.gc-domains small{color:var(--muted);font-size:.62rem;font-weight:850;letter-spacing:.1em}.gc-now strong,.gc-domains strong{overflow-wrap:anywhere}.gc-state{color:var(--warn)}.gc-domains{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.7rem;margin-top:.7rem}.gc-domains span,.gc-trend{color:var(--muted);font-size:.68rem}.gc-domains svg{width:100%;height:30px}.gc-domains polyline{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}#glassCockpitSituation details{margin-top:.65rem}#glassCockpitSituation summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted)}:focus-visible{outline:3px solid var(--gc-focus)!important;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}@media(max-width:760px){.gc-now,.gc-domains{grid-template-columns:1fr}.gc-now>div,.gc-domains section{padding:.75rem}#glassCockpitSituation{padding:.85rem}}`;
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

(()=>{
"use strict";

const MISSION_MODE_KEY="truepanel.mission.mode.v1";
const PILOT="pilot";
const ENGINEER="engineer";
const STYLE_ID="missionModeStyles";
const SWITCH_ID="missionModeSwitch";

function normalizeMode(value){
    return value===ENGINEER?ENGINEER:PILOT;
}

function storedMode(){
    try{
        return normalizeMode(window.localStorage.getItem(MISSION_MODE_KEY));
    }catch(_error){
        return PILOT;
    }
}

function saveMode(mode){
    try{
        window.localStorage.setItem(MISSION_MODE_KEY,mode);
    }catch(_error){
        // Storage is a convenience only. Mission Control remains usable without it.
    }
}

function installModeStyle(){
    if(document.getElementById(STYLE_ID)) return;
    const style=document.createElement("style");
    style.id=STYLE_ID;
    style.textContent=`
.mission-mode-switch{display:inline-flex;align-items:center;gap:2px;padding:2px;border:1px solid var(--edge);border-radius:9px;background:color-mix(in srgb,var(--panel-solid) 66%,transparent)}
.mission-mode-switch button{min-height:36px;padding:.42rem .62rem;border:0;border-radius:7px;background:transparent;color:var(--muted);font-size:.68rem;font-weight:850;letter-spacing:.04em;white-space:nowrap}
.mission-mode-switch button:hover{border:0;background:color-mix(in srgb,var(--accent) 9%,transparent);color:var(--text)}
.mission-mode-switch button[aria-pressed="true"]{background:color-mix(in srgb,var(--accent) 22%,var(--panel-solid));color:var(--text);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 45%,transparent)}
body[data-mission-mode="pilot"] .temps-card,
body[data-mission-mode="pilot"] .fans-card,
body[data-mission-mode="pilot"] .events-card,
body[data-mission-mode="pilot"] #aegisReliabilityView,
body[data-mission-mode="pilot"] #cockpitMaintenance,
body[data-mission-mode="pilot"] #openFlightManual,
body[data-mission-mode="pilot"] #flightManualPanel,
body[data-mission-mode="pilot"] .cockpit-layout-switcher,
body[data-mission-mode="pilot"] #glassCockpitSituation>details{display:none!important}
@media(max-width:640px){.mission-mode-switch{order:-1}.mission-mode-switch button{min-height:40px;padding:.48rem .56rem;font-size:.64rem}}
`;
    document.head.appendChild(style);
}

function syncButtons(mode){
    document.querySelectorAll(`#${SWITCH_ID} button[data-mission-mode]`).forEach(button=>{
        const active=button.dataset.missionMode===mode;
        button.setAttribute("aria-pressed",active?"true":"false");
        button.classList.toggle("active",active);
    });
}

function applyMode(value,{persist=true,announce=true}={}){
    const mode=normalizeMode(value);
    if(document.body) document.body.dataset.missionMode=mode;
    if(persist) saveMode(mode);
    syncButtons(mode);

    if(mode===PILOT){
        document.getElementById("flightManualPanel")?.classList.remove("show");
    }

    if(announce){
        document.dispatchEvent(new CustomEvent("truepanel:mission-mode",{detail:{mode}}));
    }
    return mode;
}

function modeButton(mode,label,title){
    const button=document.createElement("button");
    button.type="button";
    button.dataset.missionMode=mode;
    button.textContent=label;
    button.title=title;
    button.setAttribute("aria-label",title);
    button.setAttribute("aria-pressed","false");
    button.addEventListener("click",()=>applyMode(mode));
    return button;
}

function installModeSwitch(){
    if(document.getElementById(SWITCH_ID)) return;
    const actions=document.querySelector(".actions");
    if(!actions) return;

    const group=document.createElement("div");
    group.id=SWITCH_ID;
    group.className="mission-mode-switch";
    group.setAttribute("role","group");
    group.setAttribute("aria-label","Mission Control operating mode");
    group.append(
        modeButton(PILOT,"Pilot","Pilot Mode · day-to-day system health and action items"),
        modeButton(ENGINEER,"Engineer","Flight Engineer Mode · troubleshooting, diagnostics, controls, and Flight Manual")
    );

    const manual=document.getElementById("openFlightManual");
    if(manual) actions.insertBefore(group,manual);
    else actions.prepend(group);
}

function installMissionModes(){
    installModeStyle();
    installModeSwitch();
    applyMode(storedMode(),{persist:false,announce:false});
}

installModeStyle();
if(document.body) document.body.dataset.missionMode=storedMode();

if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",installMissionModes,{once:true});
}else{
    installMissionModes();
}

window.TruePanelMissionMode={
    getMode:()=>normalizeMode(document.body?.dataset.missionMode||storedMode()),
    setMode:mode=>applyMode(mode),
};
})();
