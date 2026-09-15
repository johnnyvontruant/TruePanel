(()=>{
"use strict";

const BRIEF_URL="/api/v1/wingman/brief";
const VIEW_ID="wingmanAdvisory";
const STYLE_ID="wingmanAdvisoryStyles";

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

function sourceLabel(sourceId){
    const known={
        "status:reliability":"Mission Control Reliability",
        "status:operator_guidance":"Operator Guidance",
        "status:system":"System Status",
        "status:storage":"Storage",
        "status:fans":"Cooling",
        "status:network":"Network",
        "status:cargo":"Cargo",
        "status:sentinel":"SENTINEL",
        "status:lifeline":"LIFELINE",
        "status:preflight":"Preflight",
    };
    if(known[sourceId]) return known[sourceId];

    return String(sourceId||"source")
        .replace(/^status:/,"")
        .replaceAll("_"," ")
        .replace(/\b\w/g,char=>char.toUpperCase());
}

function sourceBadges(sourceIds){
    const ids=Array.isArray(sourceIds)
        ? [...new Set(sourceIds.filter(Boolean))]
        : [];

    if(!ids.length){
        return '<span class="wm-source none">NO SOURCE ID</span>';
    }

    return ids.map(sourceId=>`
        <span
            class="wm-source"
            title="${esc(sourceId)}"
        >${esc(sourceLabel(sourceId))}</span>
    `).join("");
}

function installStyle(){
    if(document.getElementById(STYLE_ID)) return;

    const style=document.createElement("style");
    style.id=STYLE_ID;
    style.textContent=`
#${VIEW_ID}{
    grid-column:1/-1;
    padding:1rem 1.15rem;
    border-color:color-mix(in srgb,var(--accent) 24%,var(--edge));
    background:
        linear-gradient(
            120deg,
            color-mix(in srgb,var(--panel-solid) 76%,transparent),
            color-mix(in srgb,var(--panel-solid) 68%,transparent)
        );
    backdrop-filter:blur(18px) saturate(180%);
    -webkit-backdrop-filter:blur(18px) saturate(180%);
}
.wm-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:1rem;
}
.wm-title small{
    display:block;
    color:var(--accent);
    font-size:.61rem;
    font-weight:900;
    letter-spacing:.15em;
}
.wm-title h3{
    margin:.16rem 0 0;
}
.wm-controls{
    display:flex;
    align-items:center;
    gap:.55rem;
    flex-wrap:wrap;
    justify-content:flex-end;
}
.wm-authority{
    display:inline-flex;
    align-items:center;
    min-height:30px;
    padding:.25rem .5rem;
    border:1px solid color-mix(in srgb,var(--edge) 32%,transparent);
    border-radius:999px;
    color:var(--muted);
    font-size:.6rem;
    font-weight:850;
    letter-spacing:.07em;
    white-space:nowrap;
}
.wm-brief{
    min-height:38px;
    padding:.48rem .8rem;
    border:1px solid color-mix(in srgb,var(--accent) 44%,transparent);
    border-radius:8px;
    background:color-mix(in srgb,var(--accent) 18%,var(--panel-solid));
    color:var(--text);
    font-size:.69rem;
    font-weight:900;
    letter-spacing:.07em;
    cursor:pointer;
}
.wm-brief:hover:not(:disabled){
    background:color-mix(in srgb,var(--accent) 25%,var(--panel-solid));
}
.wm-brief:disabled{
    opacity:.58;
    cursor:wait;
}
.wm-state{
    margin-top:.8rem;
    padding:.72rem .8rem;
    border:1px solid color-mix(in srgb,var(--edge) 20%,transparent);
    border-radius:8px;
}
.wm-state strong{
    display:block;
    font-size:.74rem;
}
.wm-state p{
    margin:.28rem 0 0;
    color:var(--muted);
    font-size:.69rem;
    line-height:1.45;
}
.wm-state.busy{
    border-color:color-mix(in srgb,var(--accent) 38%,transparent);
}
.wm-state.hold{
    border-color:color-mix(in srgb,var(--warn) 44%,transparent);
}
.wm-result{
    display:grid;
    gap:.75rem;
    margin-top:.8rem;
}
.wm-summary{
    margin:0;
    padding:.78rem .85rem;
    border-left:3px solid var(--accent);
    background:color-mix(in srgb,var(--panel-solid) 76%,transparent);
    line-height:1.5;
}
.wm-columns{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:.7rem;
}
.wm-panel{
    min-width:0;
    padding:.72rem;
    border:1px solid color-mix(in srgb,var(--edge) 22%,transparent);
    border-radius:8px;
}
.wm-panel h4{
    margin:0 0 .55rem;
    color:var(--muted);
    font-size:.64rem;
    font-weight:900;
    letter-spacing:.1em;
    text-transform:uppercase;
}
.wm-item{
    padding:.52rem 0;
    border-top:1px solid color-mix(in srgb,var(--edge) 13%,transparent);
}
.wm-item:first-of-type{
    padding-top:0;
    border-top:0;
}
.wm-item strong{
    display:block;
    font-size:.73rem;
    line-height:1.4;
}
.wm-item p{
    margin:.22rem 0 0;
    color:var(--muted);
    font-size:.67rem;
    line-height:1.4;
}
.wm-sources{
    display:flex;
    flex-wrap:wrap;
    gap:.32rem;
    margin-top:.42rem;
}
.wm-source{
    display:inline-flex;
    align-items:center;
    padding:.2rem .38rem;
    border:1px solid color-mix(in srgb,var(--accent) 28%,transparent);
    border-radius:999px;
    color:var(--muted);
    font-size:.58rem;
}
.wm-source.none{
    border-color:color-mix(in srgb,var(--warn) 32%,transparent);
}
.wm-uncertainty{
    margin:0;
    padding:.7rem .8rem;
    border:1px solid color-mix(in srgb,var(--warn) 25%,transparent);
    border-radius:8px;
    color:var(--muted);
    font-size:.67rem;
}
.wm-footer{
    display:flex;
    justify-content:space-between;
    gap:.8rem;
    flex-wrap:wrap;
    margin-top:.8rem;
    padding-top:.65rem;
    border-top:1px solid color-mix(in srgb,var(--edge) 16%,transparent);
    color:var(--muted);
    font-size:.61rem;
    font-weight:800;
    letter-spacing:.05em;
}
#${VIEW_ID} :focus-visible{
    outline:3px solid var(--warn);
    outline-offset:3px;
}
@media(max-width:760px){
    .wm-head{
        align-items:flex-start;
        display:grid;
    }
    .wm-controls{
        justify-content:flex-start;
    }
    .wm-columns{
        grid-template-columns:1fr;
    }
}
`;
    document.head.appendChild(style);
}

function standbyMarkup(){
    return `
        <div class="wm-state">
            <strong>STANDBY · ON-DEMAND ONLY</strong>
            <p>
                WINGMAN is dormant until you request a brief.
                Mission Control remains the source of truth.
            </p>
        </div>
    `;
}

function itemMarkup(item,{nextStep=false}={}){
    if(!item||typeof item!=="object") return "";

    const primary=nextStep
        ? item.step
        : item.text;

    const detail=nextStep
        ? item.why
        : "";

    return `
        <article class="wm-item">
            <strong>${esc(primary||"No statement returned.")}</strong>
            ${detail?`<p>${esc(detail)}</p>`:""}
            <div class="wm-sources">
                ${sourceBadges(item.source_ids)}
            </div>
        </article>
    `;
}

function advisoryMarkup(payload){
    const advisory=payload?.advisory||{};
    const observations=Array.isArray(advisory.observations)
        ? advisory.observations
        : [];
    const nextSteps=Array.isArray(advisory.next_steps)
        ? advisory.next_steps
        : [];
    const uncertainty=Array.isArray(advisory.uncertainty)
        ? advisory.uncertainty.filter(Boolean)
        : [];

    const observationMarkup=observations.length
        ? observations.map(item=>itemMarkup(item)).join("")
        : '<p class="wm-state">No observations returned.</p>';

    const stepMarkup=nextSteps.length
        ? nextSteps.map(item=>itemMarkup(item,{nextStep:true})).join("")
        : '<p class="wm-state">No next steps returned.</p>';

    const uncertaintyMarkup=uncertainty.length
        ? `
            <p class="wm-uncertainty">
                <strong>UNCERTAINTY · </strong>
                ${esc(uncertainty.join(" · "))}
            </p>
        `
        : "";

    return `
        <div class="wm-result">
            <p class="wm-summary">
                ${esc(advisory.summary||"No summary returned.")}
            </p>

            <div class="wm-sources">
                ${sourceBadges(advisory.summary_source_ids)}
            </div>

            <div class="wm-columns">
                <section class="wm-panel">
                    <h4>Observations</h4>
                    ${observationMarkup}
                </section>

                <section class="wm-panel">
                    <h4>Next Steps</h4>
                    ${stepMarkup}
                </section>
            </div>

            ${uncertaintyMarkup}
        </div>
    `;
}

function failureMessage(payload,responseStatus){
    const errors=Array.isArray(payload?.errors)
        ? payload.errors.filter(Boolean)
        : [];

    if(errors.length){
        return `WINGMAN unavailable · ${errors.join(" · ")}`;
    }

    if(payload?.status){
        return `WINGMAN unavailable · ${payload.status}`;
    }

    return `WINGMAN unavailable · HTTP ${responseStatus}`;
}

function install(){
    installStyle();

    if(document.getElementById(VIEW_ID)) return;

    const grid=document.querySelector("main .grid");
    if(!grid){
        window.setTimeout(install,50);
        return;
    }

    const situation=document.getElementById("glassCockpitSituation");
    if(!situation){
        window.setTimeout(install,50);
        return;
    }

    const view=document.createElement("article");
    view.id=VIEW_ID;
    view.className="card";
    view.setAttribute(
        "aria-label",
        "WINGMAN advisory copilot"
    );
    view.setAttribute("aria-live","polite");

    view.innerHTML=`
        <div class="wm-head">
            <div class="wm-title">
                <small>WINGMAN · ADVISORY COPILOT</small>
                <h3>Verified instrument brief</h3>
            </div>

            <div class="wm-controls">
                <span class="wm-authority">
                    ADVISORY ONLY · CONTROL AUTHORITY FALSE
                </span>
                <button
                    class="wm-brief"
                    type="button"
                >BRIEF ME</button>
            </div>
        </div>

        <div class="wm-body">
            ${standbyMarkup()}
        </div>

        <div class="wm-footer">
            <span>Operator triggered · no automatic inference</span>
            <span>Trusted Mission Control evidence only</span>
        </div>
    `;

    situation.insertAdjacentElement("afterend",view);

    const button=view.querySelector(".wm-brief");
    const body=view.querySelector(".wm-body");

    if(!button||!body) return;

    button.addEventListener("click",async()=>{
        if(button.disabled) return;

        button.disabled=true;
        button.setAttribute("aria-busy","true");
        button.textContent="BRIEFING…";

        body.innerHTML=`
            <div class="wm-state busy">
                <strong>WINGMAN · ANALYZING VERIFIED INSTRUMENTS</strong>
                <p>
                    Local advisory inference is running on demand.
                    Mission Control remains authoritative.
                </p>
            </div>
        `;

        try{
            const response=await fetch(
                BRIEF_URL,
                {
                    method:"POST",
                    cache:"no-store",
                    headers:{
                        Accept:"application/json",
                    },
                }
            );

            let payload={};

            try{
                payload=await response.json();
            }catch(_error){
                payload={};
            }

            if(
                !response.ok
                || payload?.status!=="EXPLAINED"
                || !payload?.advisory
            ){
                throw new Error(
                    failureMessage(payload,response.status)
                );
            }

            if(
                payload.control_authority!==false
                || payload.production_mutation!==false
                || payload.advisory_only!==true
            ){
                throw new Error(
                    "WINGMAN response failed advisory-only safety checks"
                );
            }

            body.innerHTML=advisoryMarkup(payload);

        }catch(error){
            body.innerHTML=`
                <div class="wm-state hold">
                    <strong>WINGMAN · UNAVAILABLE</strong>
                    <p>
                        ${esc(
                            error?.message
                            || "Local advisory inference did not complete."
                        )}
                    </p>
                    <p>
                        No state or hardware was changed.
                        Mission Control telemetry remains authoritative.
                    </p>
                </div>
            `;
        }finally{
            button.disabled=false;
            button.removeAttribute("aria-busy");
            button.textContent="BRIEF ME";
        }
    });
}

if(document.readyState==="loading"){
    document.addEventListener(
        "DOMContentLoaded",
        install,
        {once:true}
    );
}else{
    install();
}
})();
