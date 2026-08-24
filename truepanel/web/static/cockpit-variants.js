(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const POLL_MS=5000;
let lastStatus=null;

const GLYPHS={
" ":["00000","00000","00000","00000","00000","00000","00000"],
"0":["01110","10001","10011","10101","11001","10001","01110"],
"1":["00100","01100","00100","00100","00100","00100","01110"],
"2":["01110","10001","00001","00010","00100","01000","11111"],
"3":["11110","00001","00001","01110","00001","00001","11110"],
"4":["00010","00110","01010","10010","11111","00010","00010"],
"5":["11111","10000","10000","11110","00001","00001","11110"],
"6":["01110","10000","10000","11110","10001","10001","01110"],
"7":["11111","00001","00010","00100","01000","01000","01000"],
"8":["01110","10001","10001","01110","10001","10001","01110"],
"9":["01110","10001","10001","01111","00001","00001","01110"],
"A":["01110","10001","10001","11111","10001","10001","10001"],
"B":["11110","10001","10001","11110","10001","10001","11110"],
"C":["01111","10000","10000","10000","10000","10000","01111"],
"D":["11110","10001","10001","10001","10001","10001","11110"],
"E":["11111","10000","10000","11110","10000","10000","11111"],
"F":["11111","10000","10000","11110","10000","10000","10000"],
"G":["01111","10000","10000","10111","10001","10001","01110"],
"H":["10001","10001","10001","11111","10001","10001","10001"],
"I":["01110","00100","00100","00100","00100","00100","01110"],
"J":["00111","00010","00010","00010","10010","10010","01100"],
"K":["10001","10010","10100","11000","10100","10010","10001"],
"L":["10000","10000","10000","10000","10000","10000","11111"],
"M":["10001","11011","10101","10101","10001","10001","10001"],
"N":["10001","11001","10101","10011","10001","10001","10001"],
"O":["01110","10001","10001","10001","10001","10001","01110"],
"P":["11110","10001","10001","11110","10000","10000","10000"],
"Q":["01110","10001","10001","10001","10101","10010","01101"],
"R":["11110","10001","10001","11110","10100","10010","10001"],
"S":["01111","10000","10000","01110","00001","00001","11110"],
"T":["11111","00100","00100","00100","00100","00100","00100"],
"U":["10001","10001","10001","10001","10001","10001","01110"],
"V":["10001","10001","10001","10001","10001","01010","00100"],
"W":["10001","10001","10001","10101","10101","10101","01010"],
"X":["10001","10001","01010","00100","01010","10001","10001"],
"Y":["10001","10001","01010","00100","00100","00100","00100"],
"Z":["11111","00001","00010","00100","01000","10000","11111"],
"-":["00000","00000","00000","11111","00000","00000","00000"],
"_":["00000","00000","00000","00000","00000","00000","11111"],
".":["00000","00000","00000","00000","00000","00110","00110"],
":":["00000","00110","00110","00000","00110","00110","00000"],
"/":["00001","00010","00010","00100","01000","01000","10000"],
"%":["11001","11010","00100","01000","10110","00110","00000"],
"?":["01110","10001","00001","00010","00100","00000","00100"],
"+":["00000","00100","00100","11111","00100","00100","00000"],
"=":["00000","11111","00000","11111","00000","00000","00000"],
"(":["00010","00100","01000","01000","01000","00100","00010"],
")":["01000","00100","00010","00010","00010","00100","01000"],
};

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

function installStyle(){
    if(document.getElementById("cockpitVariantStyle")) return;
    const style=document.createElement("style");
    style.id="cockpitVariantStyle";
    style.textContent=`
.cockpit-layout-switcher{max-width:1400px;margin:.75rem auto 0;padding:0 1.5rem;display:flex;align-items:center;gap:.55rem;color:var(--muted);font-size:.7rem}.cockpit-layout-switcher strong{margin-right:.2rem;color:var(--text);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase}.cockpit-layout-switcher button{padding:.42rem .65rem;font-size:.68rem}.cockpit-layout-switcher button.active{border-color:#39a7ff;background:#0d5f99;color:#fff}.cockpit-preview-note{margin-left:auto;font-size:.65rem;letter-spacing:.06em;text-transform:uppercase}
.lcd-screen.cockpit-matrix-active{padding:.95rem 1rem}.lcd-screen.cockpit-matrix-active>.lcd-row{position:absolute!important;width:1px!important;height:1px!important;margin:-1px!important;padding:0!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}.cockpit-lcd-matrix{position:relative;z-index:2;display:grid;gap:.42rem;width:100%;margin:0 auto}.cockpit-matrix-row{display:grid;grid-template-columns:repeat(16,minmax(0,1fr));gap:clamp(2px,.32vw,5px);align-items:center}.cockpit-matrix-glyph{display:grid;grid-template-columns:repeat(5,1fr);grid-template-rows:repeat(7,1fr);gap:1px;aspect-ratio:5/7;min-width:0}.cockpit-matrix-dot{display:block;border-radius:18%;background:rgba(238,247,255,.035)}.cockpit-matrix-dot.on{background:#f7fbff}.cockpit-bay-strip{max-width:920px;margin:.7rem auto 0;padding:.65rem .9rem;border:1px solid rgba(143,164,184,.18);border-radius:10px;background:rgba(3,8,13,.5)}.cockpit-bay-head{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.5rem}.cockpit-bay-title{color:var(--muted);font-size:.62rem;font-weight:850;letter-spacing:.13em;text-transform:uppercase}.cockpit-bay-source{color:var(--muted);font-size:.58rem}.cockpit-bays{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.55rem}.cockpit-bay{display:grid;justify-items:center;gap:.28rem;min-width:0}.cockpit-bay-led{width:.78rem;height:.78rem;border:1px solid rgba(255,255,255,.16);border-radius:50%;background:#10161d;box-shadow:inset 0 0 4px rgba(0,0,0,.8)}.cockpit-bay-led.online{border-color:rgba(80,216,144,.7);background:var(--good);box-shadow:0 0 8px rgba(80,216,144,.45)}.cockpit-bay-led.attention,.cockpit-bay-led.present{border-color:rgba(255,200,87,.72);background:var(--warn);box-shadow:0 0 8px rgba(255,200,87,.35)}.cockpit-bay-led.fault,.cockpit-bay-led.missing,.cockpit-bay-led.identify{border-color:rgba(255,93,115,.8);background:var(--bad);box-shadow:0 0 9px rgba(255,93,115,.5)}.cockpit-bay-number{color:var(--muted);font-size:.6rem;font-variant-numeric:tabular-nums}.cockpit-bay-state{max-width:100%;overflow:hidden;color:var(--muted);font-size:.52rem;text-overflow:ellipsis;text-transform:uppercase;white-space:nowrap}
.cockpit-pool-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.7rem}.cockpit-pool{min-width:0;padding:.72rem .8rem;border:1px solid rgba(143,164,184,.18);border-radius:10px;background:rgba(3,8,13,.48)}.cockpit-pool-head{display:flex;align-items:center;justify-content:space-between;gap:.75rem}.cockpit-pool-name{font-weight:800}.cockpit-pool-health{font-size:.68rem;font-weight:850;letter-spacing:.07em}.cockpit-pool-health.good{color:var(--good)}.cockpit-pool-health.warn{color:var(--warn)}.cockpit-pool-health.bad{color:var(--bad)}.cockpit-pool-meter{height:7px;margin:.58rem 0 .4rem;overflow:hidden;border:1px solid var(--edge);border-radius:999px;background:#09111a}.cockpit-pool-fill{display:block;height:100%;background:var(--accent)}.cockpit-pool-meta{display:flex;justify-content:space-between;gap:.7rem;color:var(--muted);font-size:.62rem}.cockpit-preflight-dock{grid-column:1/-1}.cockpit-preflight-dock>.preflight-panel{margin:0}.cockpit-layout-b .cockpit-command-row{grid-template-columns:1fr}.cockpit-layout-b .cockpit-command-row>.health-command{grid-column:1/-1}
@media(max-width:640px){.cockpit-layout-switcher{padding:0 1rem;flex-wrap:wrap}.cockpit-preview-note{width:100%;margin-left:0}.cockpit-bays{gap:.25rem}.cockpit-bay-state{display:none}.cockpit-pool-grid{grid-template-columns:1fr}.cockpit-matrix-row{gap:1px}.cockpit-matrix-glyph{gap:.5px}}
`;
    document.head.appendChild(style);
}

function normalizedLine(node){
    return String(node?.textContent||"")
        .toUpperCase()
        .slice(0,16)
        .padEnd(16," ");
}

function glyphPattern(char){
    return GLYPHS[char]||GLYPHS["?"];
}

function renderMatrixLine(text){
    const fragment=document.createDocumentFragment();
    for(const char of text){
        const glyph=document.createElement("span");
        glyph.className="cockpit-matrix-glyph";
        glyph.setAttribute("aria-hidden","true");
        for(const row of glyphPattern(char)){
            for(const bit of row){
                const dot=document.createElement("span");
                dot.className=`cockpit-matrix-dot${bit==="1"?" on":""}`;
                glyph.appendChild(dot);
            }
        }
        fragment.appendChild(glyph);
    }
    return fragment;
}

function installMatrixLcd(){
    const screen=document.getElementById("virtualLcdScreen");
    const line1=document.getElementById("virtualLcdLine1");
    const line2=document.getElementById("virtualLcdLine2");
    if(!screen||!line1||!line2||document.getElementById("cockpitLcdMatrix")) return;

    const matrix=document.createElement("div");
    matrix.id="cockpitLcdMatrix";
    matrix.className="cockpit-lcd-matrix";
    matrix.setAttribute("aria-hidden","true");
    const row1=document.createElement("div");
    const row2=document.createElement("div");
    row1.className="cockpit-matrix-row";
    row2.className="cockpit-matrix-row";
    matrix.append(row1,row2);
    screen.appendChild(matrix);
    screen.classList.add("cockpit-matrix-active");

    let previous1="";
    let previous2="";
    const refresh=()=>{
        const next1=normalizedLine(line1);
        const next2=normalizedLine(line2);
        if(next1!==previous1){
            row1.replaceChildren(renderMatrixLine(next1));
            previous1=next1;
        }
        if(next2!==previous2){
            row2.replaceChildren(renderMatrixLine(next2));
            previous2=next2;
        }
    };
    new MutationObserver(refresh).observe(line1,{childList:true,subtree:true,characterData:true});
    new MutationObserver(refresh).observe(line2,{childList:true,subtree:true,characterData:true});
    refresh();
}

function installBayStrip(){
    const faceplate=document.querySelector(".lcd-faceplate");
    if(!faceplate||document.getElementById("cockpitBayStrip")) return;
    const strip=document.createElement("section");
    strip.id="cockpitBayStrip";
    strip.className="cockpit-bay-strip";
    strip.innerHTML=`<div class="cockpit-bay-head"><span class="cockpit-bay-title">Drive Bays</span><span class="cockpit-bay-source" id="cockpitBaySource">Awaiting trusted bay telemetry</span></div><div class="cockpit-bays" id="cockpitBays"></div>`;
    faceplate.insertAdjacentElement("afterend",strip);

    const bays=strip.querySelector("#cockpitBays");
    for(let number=1;number<=6;number+=1){
        const item=document.createElement("div");
        item.className="cockpit-bay";
        item.dataset.bay=String(number);
        item.innerHTML=`<span class="cockpit-bay-led unknown"></span><span class="cockpit-bay-number">${number}</span><span class="cockpit-bay-state">UNKNOWN</span>`;
        bays.appendChild(item);
    }
}

function updateBayStrip(data){
    const mirror=data?.storage?.bay_mirror||{};
    const records=Array.isArray(mirror.bays)?mirror.bays:[];
    const byBay=new Map(records.map(item=>[Number(item?.bay),item]));
    for(let number=1;number<=6;number+=1){
        const element=document.querySelector(`.cockpit-bay[data-bay="${number}"]`);
        if(!element) continue;
        const record=byBay.get(number)||{};
        const state=String(record.state||"unknown").toLowerCase();
        const led=element.querySelector(".cockpit-bay-led");
        const stateNode=element.querySelector(".cockpit-bay-state");
        led.className=`cockpit-bay-led ${state}`;
        stateNode.textContent=state;
        const parts=[`Bay ${number}`,state];
        if(record.pool) parts.push(String(record.pool));
        if(record.zfs_state) parts.push(String(record.zfs_state));
        if(record.mapping_source) parts.push(String(record.mapping_source));
        element.title=parts.join(" · ");
        element.setAttribute("aria-label",parts.join(", "));
    }
    const source=document.getElementById("cockpitBaySource");
    if(source){
        source.textContent=mirror.available===true
            ?`${records.length} bays · read-only mirror`
            :"Bay identity unavailable · no inference";
    }
}

function poolPercent(pool){
    const raw=pool?.percent_used??pool?.used_percent??pool?.capacity;
    const numeric=Number.parseFloat(String(raw??"").replace("%",""));
    return Number.isFinite(numeric)?Math.max(0,Math.min(100,numeric)):null;
}

function poolTone(health){
    const value=String(health||"").toUpperCase();
    if(value==="ONLINE"||value==="HEALTHY") return "good";
    if(["FAULTED","OFFLINE","UNAVAIL","UNAVAILABLE"].includes(value)) return "bad";
    return "warn";
}

function updatePools(data){
    const target=document.getElementById("pools");
    if(!target) return;
    const pools=Array.isArray(data?.storage?.pools)?data.storage.pools:[];
    if(!pools.length){
        target.innerHTML='<div class="detail">No pool telemetry available</div>';
        return;
    }
    target.innerHTML=`<div class="cockpit-pool-grid">${pools.map(pool=>{
        const health=String(pool?.health||pool?.status||"UNKNOWN").toUpperCase();
        const percent=poolPercent(pool);
        const width=percent===null?0:percent;
        const used=String(pool?.used??"--");
        const free=String(pool?.free??"--");
        const size=String(pool?.size??"--");
        return `<div class="cockpit-pool"><div class="cockpit-pool-head"><span class="cockpit-pool-name">${esc(pool?.name||"Pool")}</span><span class="cockpit-pool-health ${poolTone(health)}">${esc(health)}</span></div><div class="cockpit-pool-meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent===null?0:percent}"><span class="cockpit-pool-fill" style="width:${width}%"></span></div><div class="cockpit-pool-meta"><span>${percent===null?"Usage unavailable":`${Math.round(percent)}% used`}</span><span>${esc(used)} / ${esc(size)} · ${esc(free)} free</span></div></div>`;
    }).join("")}</div>`;
}

function installPoolStabilityGuard(){
    const target=document.getElementById("pools");
    if(!target||target.dataset.cockpitPoolGuard==="true") return;
    target.dataset.cockpitPoolGuard="true";

    const restore=()=>{
        const pools=Array.isArray(lastStatus?.storage?.pools)
            ?lastStatus.storage.pools
            :[];
        if(!pools.length||target.querySelector(".cockpit-pool-grid")) return;
        updatePools(lastStatus);
    };

    new MutationObserver(restore).observe(target,{
        childList:true,
        subtree:false,
    });
}

function variantNodes(){
    return{
        grid:document.querySelector("main .grid"),
        overview:document.getElementById("cockpitOverview"),
        commandRow:document.querySelector(".cockpit-command-row"),
        health:document.querySelector(".health-command"),
        preflight:document.getElementById("preflightPanel"),
        vfp:document.querySelector(".lcd-panel"),
    };
}

function preflightDock(grid){
    let dock=document.getElementById("cockpitPreflightDock");
    if(!dock){
        dock=document.createElement("section");
        dock.id="cockpitPreflightDock";
        dock.className="cockpit-preflight-dock";
        dock.setAttribute("aria-label","Preflight readiness");
    }
    if(!dock.parentNode&&grid) grid.appendChild(dock);
    return dock;
}

function applyLayout(rawMode){
    const mode=["a","b","c"].includes(String(rawMode).toLowerCase())?String(rawMode).toLowerCase():"a";
    const {grid,overview,commandRow,health,preflight,vfp}=variantNodes();
    if(!grid||!overview||!commandRow||!health||!preflight||!vfp) return;
    document.body.classList.remove("cockpit-layout-a","cockpit-layout-b","cockpit-layout-c");
    document.body.classList.add(`cockpit-layout-${mode}`);
    document.body.dataset.cockpitVariant=mode;

    const dock=preflightDock(grid);
    if(mode==="b"){
        commandRow.appendChild(health);
        dock.appendChild(preflight);
        grid.prepend(overview);
        grid.insertBefore(vfp,overview.nextSibling);
        grid.insertBefore(dock,vfp.nextSibling);
    }else if(mode==="c"){
        commandRow.append(health,preflight);
        dock.remove();
        grid.prepend(vfp);
        grid.insertBefore(overview,vfp.nextSibling);
    }else{
        commandRow.append(health,preflight);
        dock.remove();
        grid.prepend(overview);
        grid.insertBefore(vfp,overview.nextSibling);
    }

    document.querySelectorAll("[data-cockpit-variant]").forEach(button=>{
        button.classList.toggle("active",button.dataset.cockpitVariant===mode);
        button.setAttribute("aria-pressed",button.dataset.cockpitVariant===mode?"true":"false");
    });
}

function installVariantSwitcher(){
    const params=new URLSearchParams(window.location.search);
    const preview=params.get("cockpit-preview")==="1"||params.has("layout");
    const initial=String(params.get("layout")||"a").toLowerCase();
    if(preview&&!document.getElementById("cockpitLayoutSwitcher")){
        const switcher=document.createElement("nav");
        switcher.id="cockpitLayoutSwitcher";
        switcher.className="cockpit-layout-switcher";
        switcher.setAttribute("aria-label","Cockpit layout preview variants");
        switcher.innerHTML='<strong>Layout Preview</strong><button type="button" data-cockpit-variant="a">A · Current</button><button type="button" data-cockpit-variant="b">B · LCD Near Top</button><button type="button" data-cockpit-variant="c">C · LCD First</button><span class="cockpit-preview-note">Local composition only</span>';
        document.querySelector("header")?.insertAdjacentElement("afterend",switcher);
        switcher.addEventListener("click",event=>{
            const button=event.target.closest("[data-cockpit-variant]");
            if(!button) return;
            const mode=button.dataset.cockpitVariant;
            const url=new URL(window.location.href);
            url.searchParams.set("cockpit-preview","1");
            url.searchParams.set("layout",mode);
            window.history.replaceState({},"",url);
            applyLayout(mode);
        });
    }
    window.requestAnimationFrame(()=>applyLayout(initial));
}

async function refreshStatus(){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) return;
        const data=await response.json();
        lastStatus=data;
        updateBayStrip(data);
        updatePools(data);
    }catch(_error){
        const source=document.getElementById("cockpitBaySource");
        if(source) source.textContent="Bay telemetry unavailable · no inference";
    }
}

function install(){
    installStyle();
    installMatrixLcd();
    installBayStrip();
    installVariantSwitcher();
    installPoolStabilityGuard();
    refreshStatus();
    window.setInterval(refreshStatus,POLL_MS);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
