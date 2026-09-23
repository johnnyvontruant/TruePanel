(()=>{
"use strict";

const BRIEF_URL="/api/v1/wingman/brief";
const OFFLINE_URL="/api/v1/wingman/offline-brief";
const READINESS_URL="/api/v1/wingman/readiness";
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
        "status:reliability":{
            full:"Mission Control Reliability",
            compact:"RELIABILITY",
        },
        "status:operator_guidance":{
            full:"Operator Guidance",
            compact:"GUIDANCE",
        },
        "status:system":{
            full:"System Status",
            compact:"SYSTEM",
        },
        "status:storage":{
            full:"Storage",
            compact:"STORAGE",
        },
        "status:fans":{
            full:"Cooling",
            compact:"COOLING",
        },
        "status:network":{
            full:"Network",
            compact:"NETWORK",
        },
        "status:cargo":{
            full:"Cargo",
            compact:"CARGO",
        },
        "status:sentinel":{
            full:"SENTINEL",
            compact:"SENTINEL",
        },
        "status:lifeline":{
            full:"LIFELINE",
            compact:"LIFELINE",
        },
        "status:preflight":{
            full:"Preflight",
            compact:"PREFLIGHT",
        },
    };

    if(known[sourceId]) return known[sourceId];

    const fallback=String(sourceId||"source")
        .replace(/^status:/,"")
        .replaceAll("_"," ")
        .replace(/\b\w/g,char=>char.toUpperCase());

    return {
        full:fallback,
        compact:fallback.toUpperCase(),
    };
}

function sourceBadges(sourceIds){
    const ids=Array.isArray(sourceIds)
        ? [...new Set(sourceIds.filter(Boolean))]
        : [];

    if(!ids.length){
        return '<span class="wm-source none">NO SOURCE ID</span>';
    }

    return ids.map(sourceId=>{
        const label=sourceLabel(sourceId);

        return `
            <span
                class="wm-source"
                title="${esc(`${label.full} · ${sourceId}`)}"
                data-source-id="${esc(sourceId)}"
                data-source-compact="${esc(label.compact)}"
            >
                <span class="wm-source-prefix">SOURCE · </span>
                <span class="wm-source-full">${esc(label.full)}</span>
                <span class="wm-source-compact">${esc(label.compact)}</span>
            </span>
        `;
    }).join("");
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
    font-weight:800;
    letter-spacing:.035em;
}
.wm-source-prefix{
    color:var(--accent);
}
.wm-source-compact{
    display:none;
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

/* Pilot mode keeps WINGMAN glanceable. Flight Engineer retains
   the complete advisory instrument. */
body[data-mission-mode="pilot"] #${VIEW_ID}{
    padding:.68rem .85rem;
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-head{
    min-height:40px;
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-title small{
    font-size:.58rem;
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-title h3{
    margin:.08rem 0 0;
    font-size:.78rem;
    color:var(--muted);
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-authority{
    display:none;
}
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="standby"] .wm-footer{
    display:none;
}
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="ready"] .wm-columns,
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="ready"] .wm-body .wm-uncertainty,
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="ready"] .wm-footer{
    display:none;
}
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="ready"] .wm-result{
    margin-top:.55rem;
    gap:.4rem;
}
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="ready"] .wm-summary{
    padding:.55rem .65rem;
    font-size:.72rem;
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-source-full{
    display:none;
}
body[data-mission-mode="pilot"] #${VIEW_ID} .wm-source-compact{
    display:inline;
}
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="busy"] .wm-footer,
body[data-mission-mode="pilot"] #${VIEW_ID}[data-wingman-state="hold"] .wm-footer{
    display:none;
}
.wm-elapsed{
    display:inline-block;
    margin-top:.35rem;
    color:var(--accent);
    font-size:.63rem;
    font-weight:850;
    letter-spacing:.05em;
}

/* The plain-language AI panel is visible; deeper instruments are disclosed on demand. */
.wm-deep-dive{
    margin-top:.75rem;
    border:1px solid color-mix(in srgb,var(--edge) 28%,transparent);
    border-radius:8px;
    padding:.52rem .72rem;
}
.wm-deep-dive > summary{
    cursor:pointer;
    font-size:.7rem;
    font-weight:850;
    color:var(--muted);
}
.wm-deep-dive[open] > summary{
    margin-bottom:.65rem;
}
.wm-deep-dive .wm-controls{
    justify-content:flex-start;
}
.wm-offline-panel:not(:empty),
.wm-readiness-panel:not(:empty){
    margin-top:.65rem;
}
.wm-offline-panel .wm-result,
.wm-readiness-panel .wm-state{
    margin-top:0;
}
.wm-details{
    margin-top:.5rem;
    color:var(--muted);
    font-size:.67rem;
}
.wm-details summary{
    cursor:pointer;
    font-weight:850;
}
.wm-readiness-metrics{
    display:flex;
    gap:.8rem;
    flex-wrap:wrap;
    margin-top:.5rem;
    font-size:.68rem;
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
                Select AI BRIEF for a plain-language explanation of verified system evidence.
                AI runs only on request when a local model and resource checks are available.
                Instrument readings and readiness checks are under Engineer details.
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

function setWingmanState(view,state){
    view.dataset.wingmanState=state;
}


function isReadOnly(payload){
    return payload
        && payload.project==="WINGMAN"
        && payload.schema_version===1
        && payload.advisory_only===true
        && payload.control_authority===false
        && payload.production_mutation===false
        && payload.model_invoked===false;
}

function offlineMarkup(payload){
    const observations=Array.isArray(payload.observations)
        ? payload.observations : [];
    const uncertainty=Array.isArray(payload.uncertainty)
        ? payload.uncertainty : [];
    const evidence=observations.map(item=>
        "<article class='wm-item'><strong>"+esc(item.text||"")+"</strong>"
        +"<div class='wm-sources'>"+sourceBadges(item.source_ids)+"</div></article>"
    ).join("");
    const uncertaintyHtml=uncertainty.length
        ? "<p class='wm-uncertainty'><strong>UNCERTAINTY · </strong>"
          +esc(uncertainty.join(" · "))+"</p>"
        : "";
    return "<div class='wm-result' data-brief-kind='deterministic'>"
        +"<div class='wm-state'><strong>INSTRUMENT BRIEF · "
        +esc(payload.status)+" · NO MODEL</strong></div>"
        +"<p class='wm-summary'>"+esc(payload.summary||"No instrument evidence.")+"</p>"
        +"<div class='wm-sources'>"+sourceBadges(payload.source_ids)+"</div>"
        +uncertaintyHtml
        +(evidence
            ? "<details class='wm-details'><summary>View cited observations</summary>"
              +evidence+"</details>"
            : "")
        +"</div>";
}

const READINESS_REASONS={
    HOST_RESOURCES_UNAVAILABLE:"Host resource measurements are unavailable.",
    MEMORY_READING_INVALID:"Available-memory measurement is invalid.",
    LOAD_READING_INVALID:"CPU-load measurement is invalid.",
    MEMORY_BELOW_POLICY:"Available memory is below the inference threshold.",
    LOAD_ABOVE_POLICY:"CPU load is above the inference threshold.",
    LLAMA_SERVER_MISSING:"Local inference executable is unavailable.",
    MODEL_FILE_MISSING:"Local model file is unavailable.",
};

function readinessMarkup(payload){
    const ready=payload.status==="READY_FOR_RECHECK";
    const reasons=Array.isArray(payload.reason_codes)
        ? payload.reason_codes : [];
    const reasonHtml=reasons.map(code=>
        "<p>"+esc(READINESS_REASONS[code]||"Unrecognized readiness blocker.")+"</p>"
    ).join("");
    const mem=Number.isFinite(payload.available_memory_gib)
        ? esc(payload.available_memory_gib.toFixed(2))+" GiB"
        : "Unknown";
    const required=Number.isFinite(payload.minimum_memory_gib)
        ? esc(payload.minimum_memory_gib.toFixed(2))+" GiB" : "Unknown";
    const load=Number.isFinite(payload.load_1m)
        ? esc(payload.load_1m.toFixed(2)) : "Unknown";
    const maximum=Number.isFinite(payload.maximum_load_1m)
        ? esc(payload.maximum_load_1m.toFixed(2)) : "Unknown";
    return "<div class='wm-state "+(ready?"":"hold")+"' data-inference-readiness='"
        +esc(payload.status)+"'><strong>LOCAL AI · "
        +(ready?"READY FOR RECHECK":"RESOURCE HOLD")+"</strong>"
        +"<div class='wm-readiness-metrics'><span>Memory: "+mem+" / "+required
        +" required</span><span>Load: "+load+" / "+maximum+" maximum</span></div>"
        +reasonHtml
        +"<p>Readiness is observational, not launch authorization. "
        +"The runtime rechecks resources before starting.</p></div>";
}

async function requestReadiness(){
    const response=await fetch(READINESS_URL,{
        method:"GET",cache:"no-store",headers:{Accept:"application/json"},
    });
    if(!response.ok) throw new Error("Readiness endpoint unavailable.");
    const payload=await response.json();
    if(!isReadOnly(payload) || payload.launch_authorized!==false
        || !Array.isArray(payload.reason_codes)
        || (payload.status!=="HOLD" && payload.status!=="READY_FOR_RECHECK")
        || (payload.status==="READY_FOR_RECHECK" && payload.reason_codes.length)){
        throw new Error("Readiness response failed its read-only contract.");
    }
    return payload;
}

async function requestOffline(){
    const response=await fetch(OFFLINE_URL,{
        method:"GET",cache:"no-store",headers:{Accept:"application/json"},
    });
    if(!response.ok) throw new Error("Instrument brief endpoint unavailable.");
    const payload=await response.json();
    if(!isReadOnly(payload) || payload.mode!=="offline_brief"
        || !["OBSERVED","INSUFFICIENT_EVIDENCE"].includes(payload.status)
        || !Array.isArray(payload.source_ids)
        || !Array.isArray(payload.observations)
        || !Array.isArray(payload.uncertainty)){
        throw new Error("Instrument brief response failed its read-only contract.");
    }
    return payload;
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
    setWingmanState(view,"standby");
    view.setAttribute(
        "aria-label",
        "WINGMAN advisory copilot"
    );
    view.setAttribute("aria-live","polite");

    view.innerHTML=`
        <div class="wm-head">
            <div class="wm-title">
                <small>WINGMAN · ADVISORY COPILOT</small>
                <h3>Plain-language system brief</h3>
            </div>

            <div class="wm-controls">
                <span class="wm-authority">
                    ADVISORY ONLY · CONTROL AUTHORITY FALSE
                </span>
                <button class="wm-brief wm-ai" type="button">AI BRIEF</button>
            </div>
        </div>

        <div class="wm-body">
            ${standbyMarkup()}
        </div>
        <details class="wm-deep-dive">
            <summary>ENGINEER DETAILS · Instrument readings &amp; AI readiness</summary>
            <div class="wm-controls">
                <button class="wm-brief wm-offline" type="button">INSTRUMENT BRIEF</button>
                <button class="wm-brief wm-readiness" type="button">CHECK READINESS</button>
            </div>
            <div class="wm-offline-panel" aria-live="polite"></div>
            <div class="wm-readiness-panel" aria-live="polite"></div>
        </details>

        <div class="wm-footer">
            <span>Instrument brief: model free · AI: operator triggered</span>
            <span>Trusted Mission Control evidence only</span>
        </div>
    `;

    situation.insertAdjacentElement("afterend",view);

    const button=view.querySelector(".wm-ai");
    const offlineButton=view.querySelector(".wm-offline");
    const readinessButton=view.querySelector(".wm-readiness");
    const body=view.querySelector(".wm-body");
    const offlinePanel=view.querySelector(".wm-offline-panel");
    const readinessPanel=view.querySelector(".wm-readiness-panel");
    const deepDive=view.querySelector(".wm-deep-dive");

    if(!button||!body||!offlineButton||!readinessButton
        ||!offlinePanel||!readinessPanel) return;

    async function loadReadiness(){
        const payload=await requestReadiness();
        readinessPanel.innerHTML=readinessMarkup(payload);
        return payload;
    }

    offlineButton.addEventListener("click",async()=>{
        if(offlineButton.disabled) return;
        offlineButton.disabled=true;
        offlineButton.textContent="READING…";
        try{
            const payload=await requestOffline();
            offlinePanel.innerHTML=offlineMarkup(payload);
        }catch(_error){
            offlinePanel.innerHTML="<div class='wm-state hold'>"
                +"<strong>INSTRUMENT BRIEF UNAVAILABLE</strong>"
                +"<p>No verified offline briefing was returned. "
                +"Mission Control remains authoritative.</p></div>";
        }finally{
            offlineButton.disabled=false;
            offlineButton.textContent="INSTRUMENT BRIEF";
        }
    });

    readinessButton.addEventListener("click",async()=>{
        if(readinessButton.disabled) return;
        readinessButton.disabled=true;
        readinessButton.textContent="CHECKING…";
        try{
            await loadReadiness();
        }catch(_error){
            if(deepDive) deepDive.open=true;
            readinessPanel.innerHTML="<div class='wm-state hold'>"
                +"<strong>LOCAL AI · READINESS UNKNOWN</strong>"
                +"<p>Could not verify the inference gates. AI remains unavailable.</p>"
                +"</div>";
        }finally{
            readinessButton.disabled=false;
            readinessButton.textContent="CHECK READINESS";
        }
    });

    button.addEventListener("click",async()=>{
        if(button.disabled) return;

        button.disabled=true;
        try{
            const readiness=await loadReadiness();
            if(readiness.status!=="READY_FOR_RECHECK"){
                if(deepDive) deepDive.open=true;
                body.innerHTML="<div class='wm-state hold'>"
                    +"<strong>AI BRIEF · RESOURCE HOLD</strong>"
                    +"<p>Instrument briefs remain available without loading a model. "
                    +"Review the readiness report below.</p></div>";
                setWingmanState(view,"hold");
                return;
            }
        }catch(_error){
            readinessPanel.innerHTML="<div class='wm-state hold'>"
                +"<strong>LOCAL AI · READINESS UNKNOWN</strong>"
                +"<p>Unable to verify launch policy. AI remains unavailable.</p></div>";
            body.innerHTML="<div class='wm-state hold'>"
                +"<strong>AI BRIEF · SAFETY HOLD</strong>"
                +"<p>No model request was made. Instrument briefs remain available.</p>"
                +"</div>";
            setWingmanState(view,"hold");
            return;
        }finally{
            // The inference request below owns the button only after its
            // independent, fail-closed readiness check has completed.
            button.disabled=false;
        }

        button.disabled=true;
        button.setAttribute("aria-busy","true");
        button.textContent="BRIEFING…";

        setWingmanState(view,"busy");

        body.innerHTML=`
            <div class="wm-state busy">
                <strong>WINGMAN · REVIEWING VERIFIED INSTRUMENTS</strong>
                <p>
                    Local advisory inference is running on demand.
                    Mission Control remains authoritative.
                </p>
                <span class="wm-elapsed">0s elapsed</span>
            </div>
        `;

        const startedAt=performance.now();
        let elapsedTimerActive=true;

        const updateElapsed=()=>{
            if(!elapsedTimerActive) return;

            const elapsedNode=body.querySelector(".wm-elapsed");

            if(elapsedNode){
                const seconds=Math.floor(
                    (performance.now()-startedAt)/1000
                );

                elapsedNode.textContent=`${seconds}s elapsed`;
            }

            window.setTimeout(updateElapsed,1000);
        };

        updateElapsed();

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
            setWingmanState(view,"ready");

        }catch(error){
            setWingmanState(view,"hold");

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
            elapsedTimerActive=false;
            button.disabled=false;
            button.removeAttribute("aria-busy");
            button.textContent="AI BRIEF";
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
