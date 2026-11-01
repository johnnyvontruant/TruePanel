(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const TRANSITION_URL="/api/v1/recovery/transition";
const INTENT="pathfinder-recovery-transition";
const POLL_MS=5000;
const STATES=["detected","reviewing","diagnosing","repairing","verifying","resolved"];
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

const title=value=>String(value||"")
    .replaceAll("_"," ")
    .replace(/\b\w/g,char=>char.toUpperCase());

function stateIndex(value){
    const index=STATES.indexOf(String(value||"").toLowerCase());
    return index<0?0:index;
}

function activeCard(payload){
    const cards=Array.isArray(payload?.operator_guidance)
        ?payload.operator_guidance.filter(item=>item&&typeof item==="object"&&item.recovery)
        :[];
    cards.sort((a,b)=>(PRIORITY[a.code]??99)-(PRIORITY[b.code]??99));
    return cards.find(item=>String(item.recovery?.state||"")!=="resolved")||cards[0]||null;
}

function latestSession(payload){
    const sessions=Array.isArray(payload?.pathfinder_recovery?.sessions)
        ?payload.pathfinder_recovery.sessions
        :[];
    return sessions[0]||null;
}

function stages(state){
    const current=stateIndex(state);
    return STATES.map((name,index)=>{
        let className="upcoming";
        if(index<current) className="done";
        if(index===current) className="active";
        if(String(state)==="resolved") className="done";
        return `<div class="pf-stage ${className}"><span>${index+1}</span><strong>${esc(title(name))}</strong></div>`;
    }).join("");
}

function timelineRows(items){
    const events=Array.isArray(items)?items.slice(-5).reverse():[];
    if(!events.length) return '<div class="pf-empty">No recovery events recorded yet.</div>';
    return events.map(item=>{
        const automatic=item?.automated===true?"AUTO":"OPERATOR";
        return `<div class="pf-timeline-row"><span>${esc(automatic)}</span><strong>${esc(title(item?.event||"state changed"))}</strong><small>${esc(title(item?.state||""))}</small></div>`;
    }).join("");
}

function verificationText(card,session){
    const verification=card?.recovery?.verification||{};
    if(String(session?.state||card?.recovery?.state||"")==="resolved"){
        return "Machine verification passed. The recovery incident is resolved.";
    }
    if(verification.status==="passed"){
        return "The live verifier is satisfied. Mission Control is closing the incident.";
    }
    if(verification.criteria){
        return String(verification.criteria);
    }
    if(Number(session?.clear_observations||0)>0){
        return `Triggering guidance has cleared. Waiting for repeated NOMINAL health evidence (${session.clear_observations} confirmed).`;
    }
    return "Fresh telemetry remains authoritative. RESOLVED cannot be selected manually.";
}

function actionButtons(state){
    const actions={
        detected:[["begin_recovery","Begin Recovery"]],
        reviewing:[["begin_diagnosis","Start Diagnosis"]],
        diagnosing:[["begin_repair","Begin Repair"],["begin_verification","Verify Now"]],
        repairing:[["begin_verification","Begin Verification"]],
        verifying:[["return_to_diagnosis","Return to Diagnosis"]],
        resolved:[],
    }[state]||[];
    const buttons=actions.map(([action,label])=>`<button type="button" class="pf-action" data-pf-action="${esc(action)}">${esc(label)}</button>`).join("");
    return `${buttons}<button type="button" class="pf-action secondary" data-pf-recheck>Recheck Now</button>`;
}

function render(deck,payload){
    const card=activeCard(payload);
    const sessions=Array.isArray(payload?.pathfinder_recovery?.sessions)
        ?payload.pathfinder_recovery.sessions
        :[];
    const incidentId=String(card?.recovery?.incident_id||"");
    const session=incidentId
        ?sessions.find(item=>String(item?.incident_id||"")===incidentId)||null
        :latestSession(payload);
    if(!card&&!session){
        deck.hidden=true;
        deck.innerHTML="";
        return;
    }

    const recovery=card?.recovery||session||{};
    const state=String(session?.state||recovery.state||"detected").toLowerCase();
    const code=String(card?.code||session?.code||"recovery");
    const summary=String(card?.summary||recovery.explanation||title(code));
    const timeline=session?.timeline||recovery.timeline||[];
    const verification=verificationText(card,session);
    const resolved=state==="resolved";

    deck.hidden=false;
    deck.dataset.incidentId=String(recovery.incident_id||session?.incident_id||"");
    deck.innerHTML=`
        <div class="pf-head">
            <div>
                <span class="pf-kicker">Project Pathfinder · Recovery Command Deck</span>
                <h3>${esc(summary)}</h3>
                <div class="pf-code">${esc(code)} · ${esc(title(state))}</div>
            </div>
            <span class="pf-authority">WORKFLOW METADATA ONLY</span>
        </div>
        <div class="pf-progress" role="list" aria-label="Recovery progress">${stages(state)}</div>
        <div class="pf-grid">
            <section>
                <h4>Verification</h4>
                <p>${esc(verification)}</p>
                <div class="pf-verification ${resolved?"passed":"pending"}">${resolved?"VERIFIED RESOLVED":"MACHINE VERIFICATION REQUIRED"}</div>
            </section>
            <section>
                <h4>Recovery Timeline</h4>
                <div class="pf-timeline">${timelineRows(timeline)}</div>
            </section>
        </div>
        <div class="pf-actions">${actionButtons(state)}</div>
        <p class="pf-safety">These controls record recovery workflow only. They cannot offline a disk, mutate a pool, command hardware, weaken an action gate, or manually declare RESOLVED.</p>
    `;
}

async function transition(deck,action){
    const incidentId=String(deck.dataset.incidentId||"");
    if(!incidentId||!action) return;
    deck.querySelectorAll("button").forEach(button=>{button.disabled=true;});
    try{
        const response=await fetch(TRANSITION_URL,{
            method:"POST",
            cache:"no-store",
            headers:{
                "Accept":"application/json",
                "Content-Type":"application/json",
                "X-TruePanel-Intent":INTENT,
            },
            body:JSON.stringify({incident_id:incidentId,action}),
        });
        const result=await response.json().catch(()=>({}));
        if(!response.ok){
            throw new Error(result.message||`workflow status ${response.status}`);
        }
        await refresh(deck);
    }catch(error){
        const note=deck.querySelector(".pf-safety");
        if(note) note.textContent=`Workflow update failed: ${error.message}. No repair or hardware action was attempted.`;
        deck.querySelectorAll("button").forEach(button=>{button.disabled=false;});
    }
}

async function refresh(deck){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) throw new Error(`status ${response.status}`);
        render(deck,await response.json());
    }catch(_error){
        if(!deck.hidden){
            const note=deck.querySelector(".pf-safety");
            if(note) note.textContent="Recovery telemetry is temporarily unavailable. No workflow state or hardware state was changed.";
        }
    }
}

function install(){
    const panel=document.getElementById("flightManualPanel");
    const cards=document.getElementById("flightManualCards");
    if(!panel||!cards){
        window.setTimeout(install,50);
        return;
    }
    if(document.getElementById("pathfinderRecoveryDeck")) return;

    const style=document.createElement("style");
    style.textContent=`
#pathfinderRecoveryDeck{margin:1rem 0;padding:1rem;border:1px solid color-mix(in srgb,var(--accent) 50%,transparent);border-radius:12px;background:color-mix(in srgb,var(--panel-solid) 72%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}#pathfinderRecoveryDeck[hidden]{display:none}.pf-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.pf-head h3{margin:.25rem 0;font-size:1.08rem}.pf-kicker{color:var(--accent);font-size:.64rem;font-weight:900;letter-spacing:.11em;text-transform:uppercase}.pf-code{color:var(--muted);font-size:.72rem}.pf-authority{padding:.35rem .55rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted);font-size:.62rem;font-weight:850;white-space:nowrap}.pf-progress{display:flex;gap:.4rem;margin:1rem 0;overflow-x:auto;padding-bottom:.25rem}.pf-stage{display:flex;align-items:center;gap:.38rem;min-width:108px;padding:.45rem .55rem;border:1px solid var(--edge);border-radius:8px;color:var(--muted);font-size:.68rem}.pf-stage span{display:grid;place-items:center;width:20px;height:20px;border:1px solid currentColor;border-radius:50%;font-weight:900}.pf-stage.active{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 50%,transparent);background:color-mix(in srgb,var(--warn) 20%,transparent)}.pf-stage.done{color:var(--good);border-color:color-mix(in srgb,var(--good) 32%,transparent)}.pf-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem}.pf-grid section{padding:.75rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:9px}.pf-grid h4{margin:0 0 .5rem;color:var(--muted);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase}.pf-grid p{margin:.2rem 0 .7rem;color:var(--muted);font-size:.8rem;line-height:1.45}.pf-verification{display:inline-block;padding:.3rem .45rem;border-radius:6px;font-size:.62rem;font-weight:900}.pf-verification.pending{color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 35%,transparent)}.pf-verification.passed{color:var(--good);border:1px solid color-mix(in srgb,var(--good) 35%,transparent)}.pf-timeline{display:grid;gap:.35rem}.pf-timeline-row{display:grid;grid-template-columns:62px 1fr auto;gap:.45rem;align-items:center;font-size:.7rem}.pf-timeline-row span{color:var(--muted);font-size:.58rem;font-weight:900}.pf-timeline-row small{color:var(--muted)}.pf-empty{color:var(--muted);font-size:.72rem}.pf-actions{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:1rem}.pf-action{padding:.55rem .75rem;border:1px solid color-mix(in srgb,var(--accent) 50%,transparent);border-radius:8px;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--text);font:inherit;font-size:.75rem;font-weight:800;cursor:pointer}.pf-action.secondary{border-color:var(--edge);background:transparent;color:var(--muted)}.pf-action:disabled{opacity:.45;cursor:not-allowed}.pf-safety{margin:.8rem 0 0;color:var(--muted);font-size:.68rem;line-height:1.45}@media(max-width:760px){.pf-head{display:block}.pf-authority{display:inline-block;margin-top:.55rem}.pf-grid{grid-template-columns:1fr}.pf-progress{margin-right:-.25rem}.pf-stage{min-width:96px}.pf-actions{display:grid;grid-template-columns:1fr}.pf-action{width:100%}.pf-timeline-row{grid-template-columns:58px 1fr}.pf-timeline-row small{grid-column:2}}
`;
    document.head.appendChild(style);

    const deck=document.createElement("section");
    deck.id="pathfinderRecoveryDeck";
    deck.hidden=true;
    deck.setAttribute("aria-live","polite");
    cards.insertAdjacentElement("beforebegin",deck);

    deck.addEventListener("click",event=>{
        const button=event.target.closest("button");
        if(!button) return;
        if(button.hasAttribute("data-pf-recheck")){
            refresh(deck);
            return;
        }
        const action=button.dataset.pfAction;
        if(action) transition(deck,action);
    });

    refresh(deck);
    window.setInterval(()=>refresh(deck),POLL_MS);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
