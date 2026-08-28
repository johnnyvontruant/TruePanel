(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const POLL_MS=5000;

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

const label=value=>String(value||"")
    .replaceAll("_"," ")
    .replace(/\b\w/g,char=>char.toUpperCase());

function phaseBar(session){
    const index=Number(session.phase_index||1);
    const count=Number(session.phase_count||1);
    const pct=Math.max(0,Math.min(100,(index/count)*100));
    return `<div class="ll-progress"><div class="ll-progress-line"><span>${esc(label(session.phase))}</span><strong>Step ${esc(index)} of ${esc(count)}</strong></div><div class="ll-track"><span style="width:${pct}%"></span></div></div>`;
}

function gateRows(gates){
    if(!Array.isArray(gates)||!gates.length) return "";
    return `<div class="ll-gates">${gates.map(item=>{
        const ok=Boolean(item.satisfied);
        const risk=item.risk&&item.risk!=="safe"?` · ${esc(String(item.risk).toUpperCase())}`:"";
        return `<div class="ll-gate ${ok?"ok":"hold"}"><span>${ok?"PASS":"HOLD"}</span><div><strong>${esc(item.title||label(item.code))}</strong><small>${esc(item.detail||"")}${risk}</small></div></div>`;
    }).join("")}</div>`;
}

function replacementPanel(item){
    const replacement=item||{};
    const reasons=Array.isArray(replacement.reasons)?replacement.reasons:[];
    if(!replacement.detected){
        return '<div class="ll-replacement"><strong>No replacement candidate detected</strong><span>Lifeline will validate capacity, identity, pool membership, and preserved-data risk before a future replacement can proceed.</span></div>';
    }
    return `<div class="ll-replacement ${replacement.valid?"ok":"hold"}"><strong>${replacement.valid?"Replacement candidate valid":"Replacement candidate blocked"}</strong><span>${replacement.device?`/dev/${esc(replacement.device)}`:"Unknown device"}${replacement.model?` · ${esc(replacement.model)}`:""}</span>${replacement.minimum_capacity_bytes!=null?`<span>Minimum capacity: ${esc(replacement.minimum_capacity_bytes)} bytes</span>`:""}${reasons.length?`<div>${reasons.map(reason=>`<em>${esc(label(reason))}</em>`).join("")}</div>`:""}</div>`;
}

function warnings(items){
    if(!Array.isArray(items)||!items.length) return "";
    return `<div class="ll-warnings">${items.map(item=>`<div>⚠ ${esc(label(item))}</div>`).join("")}</div>`;
}

function sessionCard(session,{ledgerStatus=null,healthyObservations=null}={}){
    const target=session.target||{};
    const canWrite=Boolean(session.can_execute_replacement);
    const completed=ledgerStatus==="completed"||session.phase==="complete";
    return `<section class="ll-session ${completed?"complete":""}">
        <div class="ll-head"><div><span class="ll-kicker">PROJECT LIFELINE</span><h4>${esc(session.title||"Guided repair session")}</h4></div><span class="ll-mode">${completed?"REPAIR VERIFIED":"PLANNING ONLY"}</span></div>
        ${phaseBar(session)}
        <p>${esc(session.summary||"")}</p>
        <div class="ll-target"><span>Target</span><strong>${target.pool?esc(target.pool):"Unknown pool"}${target.vdev?` / ${esc(target.vdev)}`:""}${target.bay?` · Bay ${esc(target.bay)}`:""}${target.device?` · /dev/${esc(target.device)}`:""}</strong></div>
        ${healthyObservations!=null&&!completed?`<div class="ll-verify">Recovery verification samples: <strong>${esc(healthyObservations)} / 3 healthy</strong></div>`:""}
        ${warnings(session.warnings)}
        <div class="ll-grid"><section><h5>Repair prerequisites</h5>${gateRows(session.gates)}</section><section><h5>Replacement media</h5>${replacementPanel(session.replacement)}<div class="ll-authority ${canWrite?"ready":"locked"}"><strong>${canWrite?"Planning gates complete":"Storage write authority locked"}</strong><span>${canWrite?"All planning prerequisites are satisfied, but this Lifeline slice still exposes no storage-write endpoint.":"TruePanel will not offline, replace, wipe, or remove storage from this interface."}</span></div></section></div>
    </section>`;
}

function checklistStatus(checklist){
    const status=String(checklist.status||"hold");
    if(status==="complete"){
        return {className:"verified",label:"VERIFIED COMPLETE",detail:"Machine verification confirms the recovery is complete."};
    }
    if(status==="monitor"){
        return {className:"monitor",label:"MONITOR",detail:"Recovery is in progress. Hold additional service until telemetry verifies completion."};
    }
    if(status==="authority_hold"){
        return {className:"authority",label:"AUTHORITY HOLD",detail:"Planning prerequisites are complete, but execution authority remains intentionally absent."};
    }
    if(status==="ready"){
        if(Array.isArray(checklist.preflight)&&checklist.preflight.length){
            return {className:"ready",label:"PREFLIGHT READY",detail:"Current machine-verifiable prerequisites are satisfied."};
        }
        return {className:"active",label:"ACTIVE PROCEDURE",detail:"Follow the diagnostic procedure. Human actions are never auto-marked complete."};
    }
    return {className:"hold",label:"HOLD",detail:"One or more required recovery gates are not yet satisfied."};
}

function checklistTarget(checklist){
    const target=checklist.target&&typeof checklist.target==="object"?checklist.target:{};
    const evidence=checklist.evidence&&typeof checklist.evidence==="object"?checklist.evidence:{};
    const bits=[];
    const pool=target.pool||evidence.pool;
    const vdev=target.vdev||evidence.vdev;
    const bay=target.bay||evidence.bay;
    const device=target.device||evidence.device;
    if(pool) bits.push(String(pool));
    if(vdev) bits.push(String(vdev));
    if(bay) bits.push(`Bay ${bay}`);
    if(device) bits.push(`/dev/${device}`);
    return bits.join(" · ")||"Subsystem target defined by current evidence";
}

function checklistProgress(checklist){
    const progress=checklist.progress||{};
    const verified=Number(progress.verified||0);
    const total=Number(progress.total||0);
    const phaseIndex=Number(checklist.phase_index||0);
    const phaseCount=Number(checklist.phase_count||0);
    if(total>0){
        const pct=Math.max(0,Math.min(100,(verified/total)*100));
        return {
            pct,
            text:`${verified} of ${total} machine-verifiable gates satisfied`,
        };
    }
    if(phaseIndex>0&&phaseCount>0){
        const pct=Math.max(0,Math.min(100,(phaseIndex/phaseCount)*100));
        return {
            pct,
            text:`Recovery phase ${phaseIndex} of ${phaseCount}`,
        };
    }
    return {pct:0,text:"Procedure active · verification gates appear as telemetry becomes available"};
}

function checklistState(item){
    const state=String(item&&item.state||"pending");
    if(state==="verified") return {className:"verified",label:"MACHINE VERIFIED"};
    if(state==="monitor") return {className:"monitor",label:"MONITOR"};
    if(state==="blocked") return {className:"blocked",label:"BLOCKED"};
    if(state==="hold") return {className:"hold",label:"HOLD"};
    return {className:"pending",label:"PENDING"};
}

function checklistPreflight(items){
    if(!Array.isArray(items)||!items.length){
        return '<div class="cl-empty">No specialized machine-verifiable preflight gates apply to this procedure yet.</div>';
    }
    return `<div class="cl-preflight">${items.map(item=>{
        const state=checklistState(item);
        const risk=item.risk&&item.risk!=="safe"?` · ${esc(String(item.risk).toUpperCase())}`:"";
        return `<div class="cl-gate ${state.className}" data-checklist-state="${esc(state.className)}"><span>${esc(state.label)}</span><div><strong>${esc(item.title||label(item.key))}</strong><small>${esc(item.detail||"")}${risk}</small></div></div>`;
    }).join("")}</div>`;
}

function checklistStep(step){
    const destructive=Boolean(step.destructive)||String(step.risk||"")==="destructive";
    const displayState=destructive?{className:"blocked",label:"AUTHORITY LOCKED"}:checklistState(step);
    const chips=[];
    if(destructive) chips.push('<em class="cl-chip blocked">DESTRUCTIVE</em>');
    else if(step.risk&&step.risk!=="safe") chips.push(`<em class="cl-chip hold">${esc(String(step.risk).toUpperCase())}</em>`);
    else chips.push('<em class="cl-chip verified">SAFE PROCEDURE</em>');
    if(step.requires_shutdown) chips.push('<em class="cl-chip hold">SHUTDOWN REQUIRED</em>');
    return `<div class="cl-step ${displayState.className}" data-checklist-state="${esc(displayState.className)}"><div class="cl-step-head"><span>${esc(displayState.label)}</span><div>${chips.join("")}</div></div><strong>${esc(step.title||"Procedure step")}</strong><p>${esc(step.detail||"")}</p></div>`;
}

function checklistSections(sections){
    if(!Array.isArray(sections)||!sections.length) return "";
    return `<div class="cl-procedures">${sections.map((section,index)=>{
        const steps=Array.isArray(section.steps)?section.steps:[];
        if(!steps.length) return "";
        return `<details class="cl-procedure" ${index===0?"open":""}><summary><span>${esc(section.title||label(section.key))}</span><strong>${esc(steps.length)} step${steps.length===1?"":"s"}</strong></summary><div>${steps.map(checklistStep).join("")}</div></details>`;
    }).join("")}</div>`;
}

function checklistCapabilities(checklist){
    const caps=checklist.capabilities||{};
    const rows=[
        ["Bay identify",caps.can_identify_bay],
        ["Physical service",caps.can_begin_physical_service],
        ["Replacement prepared",caps.can_prepare_replacement],
        ["Write preconditions",caps.write_preconditions_complete],
        ["Storage execution",caps.can_execute_replacement],
    ];
    return `<div class="cl-capabilities">${rows.map(([name,ready])=>`<div class="${ready?"verified":"blocked"}"><span>${esc(name)}</span><strong>${ready?"AVAILABLE":"LOCKED"}</strong></div>`).join("")}</div>`;
}

function checklistWarnings(items){
    if(!Array.isArray(items)||!items.length) return "";
    return `<div class="cl-warnings">${items.map(item=>`<div>⚠ ${esc(String(item))}</div>`).join("")}</div>`;
}

function checklistCard(checklist){
    const status=checklistStatus(checklist);
    const progress=checklistProgress(checklist);
    const phase=label(checklist.phase||"diagnose").toUpperCase();
    const readOnly=checklist.read_only!==false;
    return `<section class="cl-panel ${status.className}" data-checklist-code="${esc(checklist.code||"")}" data-checklist-status="${esc(checklist.status||"")}">
        <div class="cl-head"><div><span class="cl-kicker">PROJECT CHECKLIST</span><h4>${esc(checklist.title||"Recovery checklist")}</h4></div><div class="cl-head-badges"><span class="cl-status ${status.className}">${esc(status.label)}</span>${readOnly?'<span class="cl-readonly">READ-ONLY PROCEDURE</span>':""}</div></div>
        <div class="cl-mission-rail"><div><span>Current phase</span><strong>${esc(phase)}</strong></div><div><span>Target</span><strong>${esc(checklistTarget(checklist))}</strong></div><div><span>Procedure state</span><strong>${esc(status.label)}</strong></div></div>
        <div class="cl-progress"><div><span>${esc(progress.text)}</span><strong>${Math.round(progress.pct)}%</strong></div><div class="cl-track"><span style="width:${progress.pct}%"></span></div></div>
        <p class="cl-summary">${esc(checklist.summary||status.detail)}</p>
        <div class="cl-state-note ${status.className}"><strong>${esc(status.label)}</strong><span>${esc(status.detail)}</span></div>
        ${checklistWarnings(checklist.warnings)}
        <div class="cl-grid"><section><h5>Machine-verified preflight</h5>${checklistPreflight(checklist.preflight)}</section><section><h5>Recovery capability locks</h5>${checklistCapabilities(checklist)}</section></div>
        ${checklistSections(checklist.sections)}
        <div class="cl-boundary"><strong>No manual PASS or Resolve controls</strong><span>CHECKLIST advances only from observed telemetry, Lifeline evidence, or explicit guarded acknowledgements. Destructive storage execution is not available from this interface.</span></div>
    </section>`;
}

function checklistSummary(checklists){
    const panel=document.getElementById("flightManualPanel");
    if(!panel) return;
    let rail=document.getElementById("checklistStatusRail");
    if(!Array.isArray(checklists)||!checklists.length){
        rail?.remove();
        return;
    }
    if(!rail){
        rail=document.createElement("section");
        rail.id="checklistStatusRail";
        rail.className="cl-status-rail";
        const head=panel.querySelector(".fm-shell-head");
        if(head) head.insertAdjacentElement("afterend",rail);
        else panel.prepend(rail);
    }
    const counts={hold:0,monitor:0,authority_hold:0,complete:0,ready:0};
    for(const item of checklists){
        const key=String(item&&item.status||"hold");
        counts[key]=(counts[key]||0)+1;
    }
    const dominant=counts.hold?"hold":counts.monitor?"monitor":counts.authority_hold?"authority":counts.complete===checklists.length?"verified":"active";
    rail.className=`cl-status-rail ${dominant}`;
    rail.innerHTML=`<div><span class="cl-kicker">CHECKLIST STATUS</span><strong>${esc(checklists.length)} active procedure${checklists.length===1?"":"s"}</strong></div><div class="cl-rail-counts">${counts.hold?`<span class="hold">${counts.hold} HOLD</span>`:""}${counts.monitor?`<span class="monitor">${counts.monitor} MONITOR</span>`:""}${counts.authority_hold?`<span class="authority">${counts.authority_hold} AUTHORITY HOLD</span>`:""}${counts.ready?`<span class="ready">${counts.ready} READY</span>`:""}${counts.complete?`<span class="verified">${counts.complete} VERIFIED</span>`:""}</div>`;
}

function renderChecklists(payload){
    const checklists=Array.isArray(payload.operator_checklists)?payload.operator_checklists.filter(item=>item&&item.active!==false):[];
    document.querySelectorAll(".fm-card .cl-panel").forEach(node=>node.remove());
    checklistSummary(checklists);
    if(!checklists.length) return;

    const buckets=new Map();
    document.querySelectorAll(".fm-card[data-guidance-code]").forEach(card=>{
        const code=String(card.dataset.guidanceCode||"");
        if(!buckets.has(code)) buckets.set(code,[]);
        buckets.get(code).push(card);
    });

    for(const checklist of checklists){
        const code=String(checklist.code||"");
        const cards=buckets.get(code)||[];
        const card=cards.shift();
        if(!card) continue;
        const callout=card.querySelector(".fm-callout");
        if(callout) callout.insertAdjacentHTML("afterend",checklistCard(checklist));
        else card.insertAdjacentHTML("afterbegin",checklistCard(checklist));
    }
}

function installStyles(){
    if(document.getElementById("lifelineStyles")) return;
    const style=document.createElement("style");
    style.id="lifelineStyles";
    style.textContent=`
.ll-session{margin-top:1rem;padding:1rem;border:1px solid rgba(90,220,170,.35);border-radius:12px;background:rgba(5,20,18,.34)}.ll-session.complete{border-color:rgba(90,220,170,.65);background:rgba(8,46,34,.3)}.ll-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.ll-head h4{margin:.2rem 0;font-size:1rem}.ll-kicker{color:var(--good);font-size:.62rem;font-weight:900;letter-spacing:.12em}.ll-mode{padding:.28rem .5rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted);font-size:.62rem;font-weight:900}.ll-session.complete .ll-mode{color:var(--good);border-color:rgba(90,220,170,.4)}.ll-progress{margin:.8rem 0}.ll-progress-line{display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.ll-track{height:6px;margin-top:.4rem;border-radius:999px;background:rgba(143,164,184,.14);overflow:hidden}.ll-track span{display:block;height:100%;background:var(--good)}.ll-session>p{color:var(--muted);font-size:.82rem;line-height:1.45}.ll-target{display:grid;gap:.2rem;margin:.8rem 0;padding:.7rem;border:1px solid var(--edge);border-radius:8px}.ll-target span,.ll-session h5{color:var(--muted);font-size:.66rem;letter-spacing:.09em;text-transform:uppercase}.ll-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.ll-gates{display:grid;gap:.4rem}.ll-gate{display:grid;grid-template-columns:52px 1fr;gap:.55rem;padding:.5rem;border:1px solid var(--edge);border-radius:8px}.ll-gate>span{font-size:.65rem;font-weight:900}.ll-gate.ok>span{color:var(--good)}.ll-gate.hold>span{color:var(--bad)}.ll-gate strong{display:block;font-size:.76rem}.ll-gate small{display:block;margin-top:.15rem;color:var(--muted);font-size:.68rem;line-height:1.35}.ll-replacement,.ll-authority{display:grid;gap:.25rem;padding:.65rem;border:1px solid var(--edge);border-radius:8px;font-size:.75rem}.ll-replacement span,.ll-authority span{color:var(--muted);line-height:1.4}.ll-replacement.ok{border-color:rgba(90,220,170,.35)}.ll-replacement.hold,.ll-authority.locked{border-color:rgba(255,93,115,.35)}.ll-replacement em{display:inline-block;margin:.3rem .25rem 0 0;padding:.2rem .35rem;border:1px solid var(--edge);border-radius:999px;color:var(--bad);font-size:.6rem;font-style:normal}.ll-authority{margin-top:.6rem}.ll-authority.ready strong{color:var(--warn)}.ll-authority.locked strong{color:var(--bad)}.ll-warnings{display:grid;gap:.3rem;margin:.65rem 0}.ll-warnings div{padding:.45rem .55rem;border:1px solid rgba(255,200,87,.3);border-radius:7px;background:rgba(76,52,11,.18);color:var(--warn);font-size:.72rem}.ll-verify{margin:.6rem 0;padding:.45rem .55rem;border:1px solid rgba(57,167,255,.25);border-radius:7px;color:var(--muted);font-size:.72rem}.ll-ledger{margin-top:1rem;padding-top:.6rem;border-top:1px solid rgba(143,164,184,.14)}.ll-ledger-title{display:flex;justify-content:space-between;gap:1rem;align-items:center}.ll-ledger-title h3{margin:.3rem 0}.ll-ledger-title span{color:var(--muted);font-size:.7rem}
.cl-status-rail{display:flex;justify-content:space-between;gap:1rem;align-items:center;margin:.2rem 0 1rem;padding:.7rem .8rem;border:1px solid rgba(57,167,255,.26);border-radius:10px;background:rgba(8,22,38,.28)}.cl-status-rail>div:first-child{display:grid;gap:.15rem}.cl-status-rail>div:first-child>strong{font-size:.86rem}.cl-rail-counts{display:flex;gap:.35rem;flex-wrap:wrap;justify-content:flex-end}.cl-rail-counts span,.cl-status,.cl-readonly{padding:.28rem .45rem;border:1px solid var(--edge);border-radius:999px;font-size:.6rem;font-weight:900;letter-spacing:.04em}.cl-rail-counts .hold,.cl-status.hold{color:var(--bad);border-color:rgba(255,93,115,.45)}.cl-rail-counts .monitor,.cl-status.monitor{color:var(--accent);border-color:rgba(57,167,255,.42)}.cl-rail-counts .authority,.cl-status.authority{color:var(--warn);border-color:rgba(255,200,87,.42)}.cl-rail-counts .verified,.cl-status.verified,.cl-rail-counts .ready,.cl-status.ready{color:var(--good);border-color:rgba(90,220,170,.4)}.cl-rail-counts .active,.cl-status.active{color:var(--accent);border-color:rgba(57,167,255,.42)}.cl-panel{margin:1rem 0;padding:1rem;border:1px solid rgba(57,167,255,.34);border-radius:12px;background:rgba(6,17,28,.5)}.cl-panel.hold{border-color:rgba(255,93,115,.42)}.cl-panel.monitor{border-color:rgba(57,167,255,.48)}.cl-panel.authority{border-color:rgba(255,200,87,.45)}.cl-panel.verified{border-color:rgba(90,220,170,.5)}.cl-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.cl-head h4{margin:.18rem 0;font-size:1.02rem}.cl-kicker{color:var(--accent);font-size:.62rem;font-weight:900;letter-spacing:.13em}.cl-head-badges{display:flex;gap:.35rem;justify-content:flex-end;flex-wrap:wrap}.cl-readonly{color:var(--muted)}.cl-mission-rail{display:grid;grid-template-columns:minmax(130px,.55fr) minmax(0,1.4fr) minmax(150px,.65fr);gap:.5rem;margin:.75rem 0}.cl-mission-rail>div{display:grid;gap:.16rem;padding:.55rem;border:1px solid var(--edge);border-radius:8px;min-width:0}.cl-mission-rail span,.cl-panel h5{color:var(--muted);font-size:.62rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}.cl-mission-rail strong{font-size:.76rem;overflow-wrap:anywhere}.cl-progress{margin:.7rem 0}.cl-progress>div:first-child{display:flex;justify-content:space-between;gap:1rem;color:var(--muted);font-size:.7rem}.cl-track{height:5px;margin-top:.35rem;border-radius:999px;background:rgba(143,164,184,.14);overflow:hidden}.cl-track span{display:block;height:100%;background:var(--accent)}.cl-summary{margin:.65rem 0;color:var(--muted);font-size:.8rem;line-height:1.45}.cl-state-note{display:grid;gap:.18rem;margin:.65rem 0;padding:.6rem;border:1px solid var(--edge);border-radius:8px}.cl-state-note strong{font-size:.72rem}.cl-state-note span{color:var(--muted);font-size:.72rem;line-height:1.4}.cl-state-note.hold{border-color:rgba(255,93,115,.35)}.cl-state-note.authority{border-color:rgba(255,200,87,.34)}.cl-state-note.verified{border-color:rgba(90,220,170,.34)}.cl-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(220px,.75fr);gap:1rem;margin-top:.85rem}.cl-panel h5{margin:.15rem 0 .5rem}.cl-preflight{display:grid;gap:.4rem}.cl-gate{display:grid;grid-template-columns:112px 1fr;gap:.55rem;padding:.5rem;border:1px solid var(--edge);border-radius:8px}.cl-gate>span{font-size:.6rem;font-weight:900}.cl-gate.verified>span{color:var(--good)}.cl-gate.hold>span{color:var(--bad)}.cl-gate.monitor>span{color:var(--accent)}.cl-gate.blocked>span{color:var(--warn)}.cl-gate strong{display:block;font-size:.74rem}.cl-gate small{display:block;margin-top:.12rem;color:var(--muted);font-size:.66rem;line-height:1.35}.cl-empty{padding:.6rem;border:1px solid var(--edge);border-radius:8px;color:var(--muted);font-size:.7rem;line-height:1.4}.cl-capabilities{display:grid;gap:.35rem}.cl-capabilities>div{display:flex;justify-content:space-between;gap:.6rem;padding:.48rem .55rem;border:1px solid var(--edge);border-radius:8px;font-size:.68rem}.cl-capabilities span{color:var(--muted)}.cl-capabilities .verified strong{color:var(--good)}.cl-capabilities .blocked strong{color:var(--bad)}.cl-warnings{display:grid;gap:.3rem;margin:.65rem 0}.cl-warnings div{padding:.45rem .55rem;border:1px solid rgba(255,200,87,.3);border-radius:7px;background:rgba(76,52,11,.18);color:var(--warn);font-size:.7rem}.cl-procedures{display:grid;gap:.5rem;margin-top:.85rem}.cl-procedure{border:1px solid var(--edge);border-radius:9px;overflow:hidden}.cl-procedure summary{display:flex;justify-content:space-between;gap:1rem;padding:.6rem .7rem;cursor:pointer;list-style:none;font-size:.72rem;font-weight:850}.cl-procedure summary::-webkit-details-marker{display:none}.cl-procedure summary strong{color:var(--muted);font-size:.64rem}.cl-procedure>div{padding:0 .7rem .35rem}.cl-step{padding:.65rem 0;border-top:1px solid rgba(143,164,184,.1)}.cl-step-head{display:flex;justify-content:space-between;gap:.5rem;align-items:flex-start;margin-bottom:.28rem}.cl-step-head>span{font-size:.58rem;font-weight:900}.cl-step.verified .cl-step-head>span{color:var(--good)}.cl-step.hold .cl-step-head>span{color:var(--bad)}.cl-step.blocked .cl-step-head>span{color:var(--warn)}.cl-step.pending .cl-step-head>span{color:var(--muted)}.cl-step>strong{font-size:.76rem}.cl-step p{margin:.25rem 0 0;color:var(--muted);font-size:.7rem;line-height:1.4}.cl-chip{display:inline-block;margin-left:.25rem;padding:.17rem .3rem;border:1px solid var(--edge);border-radius:999px;font-size:.54rem;font-style:normal;font-weight:900}.cl-chip.verified{color:var(--good)}.cl-chip.hold{color:var(--warn)}.cl-chip.blocked{color:var(--bad)}.cl-boundary{display:grid;gap:.18rem;margin-top:.8rem;padding:.6rem;border:1px dashed rgba(143,164,184,.28);border-radius:8px}.cl-boundary strong{font-size:.68rem}.cl-boundary span{color:var(--muted);font-size:.66rem;line-height:1.4}
@media(max-width:760px){.ll-grid{grid-template-columns:1fr}.ll-head,.ll-ledger-title{display:block}.ll-mode{display:inline-block;margin-top:.4rem}.cl-status-rail,.cl-head{display:block}.cl-rail-counts,.cl-head-badges{justify-content:flex-start;margin-top:.5rem}.cl-mission-rail,.cl-grid{grid-template-columns:1fr}.cl-gate{grid-template-columns:92px 1fr}.cl-step-head{display:block}.cl-step-head>div{margin-top:.25rem}.cl-chip{margin:.2rem .25rem 0 0}.cl-procedure summary{align-items:center}}
`;
    document.head.appendChild(style);
}

function ledgerContainer(){
    let node=document.getElementById("lifelineLedger");
    if(node) return node;
    const panel=document.getElementById("flightManualPanel");
    if(!panel) return null;
    node=document.createElement("section");
    node.id="lifelineLedger";
    node.className="ll-ledger";
    panel.appendChild(node);
    return node;
}

function apply(payload){
    renderChecklists(payload);

    const guidance=Array.isArray(payload.operator_guidance)?payload.operator_guidance:[];
    const current=guidance.filter(item=>item&&item.repair_session);
    document.querySelectorAll(".fm-card .ll-session").forEach(node=>node.remove());
    for(const item of current){
        const code=String(item.code||"").replaceAll('"','\\"');
        const card=document.querySelector(`.fm-card[data-guidance-code="${code}"]`);
        if(!card) continue;
        card.insertAdjacentHTML("beforeend",sessionCard(item.repair_session));
    }

    const ledger=payload.lifeline&&Array.isArray(payload.lifeline.sessions)
        ?payload.lifeline.sessions:[];
    const container=ledgerContainer();
    if(!container) return;
    if(!ledger.length){
        container.innerHTML="";
        container.style.display="none";
        return;
    }
    container.style.display="block";
    const active=ledger.filter(item=>item&&item.status==="active");
    const completed=ledger.filter(item=>item&&item.status==="completed");
    const visible=[...active,...completed.slice(-3)];
    container.innerHTML=`<div class="ll-ledger-title"><div><span class="ll-kicker">REPAIR LEDGER</span><h3>Persistent repair sessions</h3></div><span>${esc(active.length)} active · ${esc(completed.length)} completed</span></div>${visible.map(item=>item&&item.last_session?sessionCard(item.last_session,{ledgerStatus:item.status,healthyObservations:item.healthy_observations}):"").join("")}`;
}

async function refresh(){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) return;
        apply(await response.json());
    }catch(_error){
        // Flight Manual already owns the unavailable state. Lifeline and
        // CHECKLIST remain silent rather than inventing another error surface.
    }
}

function install(){
    installStyles();
    refresh();
    window.setInterval(refresh,POLL_MS);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
