(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const POLL_MS=5000;

const stableInnerMarkup=new WeakMap();
const checklistMarkupByCard=new WeakMap();
const lifelineMarkupByCard=new WeakMap();

function setStableInnerHTML(node,markup){
    if(stableInnerMarkup.get(node)===markup) return false;
    node.innerHTML=markup;
    stableInnerMarkup.set(node,markup);
    return true;
}

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
    const index=Math.max(1,Number(session.phase_index||1));
    const count=Math.max(1,Number(session.phase_count||1));
    const pct=Math.max(0,Math.min(100,index/count*100));
    return `<div class="ll-progress"><div class="ll-progress-line"><span>${esc(label(session.phase))}</span><strong>Step ${esc(index)} of ${esc(count)}</strong></div><div class="ll-track"><span style="width:${pct}%"></span></div></div>`;
}

function gateRows(gates){
    if(!Array.isArray(gates)||!gates.length) return "";
    return `<div class="ll-gates">${gates.map(item=>{
        const ok=item.satisfied===true;
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
    const identity=[
        replacement.device?`/dev/${esc(replacement.device)}`:"Unknown device",
        replacement.model?esc(replacement.model):"",
    ].filter(Boolean).join(" · ");
    return `<div class="ll-replacement ${replacement.valid?"ok":"hold"}"><strong>${replacement.valid?"Replacement candidate valid":"Replacement candidate blocked"}</strong><span>${identity}</span>${replacement.minimum_capacity_bytes!=null?`<span>Minimum capacity: ${esc(replacement.minimum_capacity_bytes)} bytes</span>`:""}${reasons.length?`<div>${reasons.map(reason=>`<em>${esc(label(reason))}</em>`).join("")}</div>`:""}</div>`;
}

function warnings(items,className="ll-warnings"){
    if(!Array.isArray(items)||!items.length) return "";
    return `<div class="${className}">${items.map(item=>`<div>⚠ ${esc(String(item))}</div>`).join("")}</div>`;
}

function sessionCard(session,{ledgerStatus=null,healthyObservations=null}={}){
    const target=session.target||{};
    const canWrite=session.can_execute_replacement===true;
    const completed=ledgerStatus==="completed"||session.phase==="complete";
    const targetBits=[];
    if(target.pool) targetBits.push(esc(target.pool));
    if(target.vdev) targetBits.push(esc(target.vdev));
    if(target.bay) targetBits.push(`Bay ${esc(target.bay)}`);
    if(target.device) targetBits.push(`/dev/${esc(target.device)}`);
    return `<section class="ll-session ${completed?"complete":""}">
        <div class="ll-head"><div><span class="ll-kicker">PROJECT LIFELINE</span><h4>${esc(session.title||"Guided repair session")}</h4></div><span class="ll-mode">${completed?"REPAIR VERIFIED":"PLANNING ONLY"}</span></div>
        ${phaseBar(session)}
        <p>${esc(session.summary||"")}</p>
        <div class="ll-target"><span>Target</span><strong>${targetBits.join(" · ")||"Unknown target"}</strong></div>
        ${healthyObservations!=null&&!completed?`<div class="ll-verify">Recovery verification samples: <strong>${esc(healthyObservations)} / 3 healthy</strong></div>`:""}
        ${warnings(session.warnings)}
        <div class="ll-grid"><section><h5>Repair prerequisites</h5>${gateRows(session.gates)}</section><section><h5>Replacement media</h5>${replacementPanel(session.replacement)}<div class="ll-authority ${canWrite?"ready":"locked"}"><strong>${canWrite?"Planning gates complete":"Storage write authority locked"}</strong><span>${canWrite?"All planning prerequisites are satisfied, but this Lifeline slice still exposes no storage-write endpoint.":"TruePanel will not offline, replace, wipe, or remove storage from this interface."}</span></div></section></div>
    </section>`;
}

function checklistStatus(checklist){
    const status=String(checklist.status||"hold");
    if(status==="complete") return {className:"verified",label:"VERIFIED COMPLETE",detail:"Machine verification confirms the recovery is complete."};
    if(status==="monitor") return {className:"monitor",label:"MONITOR",detail:"Recovery is in progress. Hold additional service until telemetry verifies completion."};
    if(status==="authority_hold") return {className:"authority",label:"AUTHORITY HOLD",detail:"Planning prerequisites are complete, but execution authority remains intentionally absent."};
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
    const fan=evidence.fan_label;
    const network=evidence.label||evidence.interface;
    if(pool) bits.push(String(pool));
    if(vdev) bits.push(String(vdev));
    if(bay) bits.push(`Bay ${bay}`);
    if(device) bits.push(`/dev/${device}`);
    if(!bits.length&&fan) bits.push(String(fan));
    if(!bits.length&&network) bits.push(String(network));
    return bits.join(" · ")||"Subsystem target defined by current evidence";
}

function checklistProgress(checklist){
    const progress=checklist.progress||{};
    const verified=Number(progress.verified||0);
    const total=Number(progress.total||0);
    const phaseIndex=Number(checklist.phase_index||0);
    const phaseCount=Number(checklist.phase_count||0);
    if(total>0){
        return {pct:Math.max(0,Math.min(100,verified/total*100)),text:`${verified} of ${total} machine-verifiable gates satisfied`};
    }
    if(phaseIndex>0&&phaseCount>0){
        return {pct:Math.max(0,Math.min(100,phaseIndex/phaseCount*100)),text:`Recovery phase ${phaseIndex} of ${phaseCount}`};
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
    const destructive=step.destructive===true||String(step.risk||"")==="destructive";
    const state=destructive?{className:"blocked",label:"AUTHORITY LOCKED"}:checklistState(step);
    const chips=[];
    if(destructive) chips.push('<em class="cl-chip blocked">DESTRUCTIVE</em>');
    else if(step.risk&&step.risk!=="safe") chips.push(`<em class="cl-chip hold">${esc(String(step.risk).toUpperCase())}</em>`);
    else chips.push('<em class="cl-chip verified">SAFE PROCEDURE</em>');
    if(step.requires_shutdown) chips.push('<em class="cl-chip hold">SHUTDOWN REQUIRED</em>');
    return `<div class="cl-step ${state.className}" data-checklist-state="${esc(state.className)}"><div class="cl-step-head"><span>${esc(state.label)}</span><div>${chips.join("")}</div></div><strong>${esc(step.title||"Procedure step")}</strong><p>${esc(step.detail||"")}</p></div>`;
}

function checklistSections(sections){
    if(!Array.isArray(sections)||!sections.length) return "";
    return `<div class="cl-procedures">${sections.map((section,index)=>{
        const steps=Array.isArray(section.steps)?section.steps:[];
        if(!steps.length) return "";
        return `<details class="cl-procedure" ${index===0?"open":""}><summary><span>${esc(section.title||label(section.key))}</span><strong>${esc(steps.length)} step${steps.length===1?"":"s"}</strong></summary><div>${steps.map(checklistStep).join("")}</div></details>`;
    }).join("")}</div>`;
}

function capabilityRows(checklist){
    if(String(checklist.recovery_kind||"generic")!=="drive_replacement"){
        return [["Safe diagnostics",true],["Disruptive execution",false]];
    }
    const caps=checklist.capabilities||{};
    return [
        ["Bay identify",caps.can_identify_bay],
        ["Physical service",caps.can_begin_physical_service],
        ["Replacement prepared",caps.can_prepare_replacement],
        ["Write preconditions",caps.write_preconditions_complete],
        ["Storage execution",caps.can_execute_replacement],
    ];
}

function checklistCapabilities(checklist){
    return `<div class="cl-capabilities">${capabilityRows(checklist).map(([name,ready])=>`<div class="${ready?"verified":"blocked"}"><span>${esc(name)}</span><strong>${ready?"AVAILABLE":"LOCKED"}</strong></div>`).join("")}</div>`;
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
        ${warnings(checklist.warnings,"cl-warnings")}
        <div class="cl-grid"><section><h5>Machine-verified preflight</h5>${checklistPreflight(checklist.preflight)}</section><section><h5>Recovery capability locks</h5>${checklistCapabilities(checklist)}</section></div>
        ${checklistSections(checklist.sections)}
        <div class="cl-boundary"><strong>No manual PASS or Resolve controls</strong><span>CHECKLIST advances only from observed telemetry, Lifeline evidence, or explicit guarded acknowledgements. Destructive storage execution is not available from this interface.</span></div>
    </section>`;
}

function checklistIdentity(item){
    const target=item&&item.target&&typeof item.target==="object"?item.target:{};
    const evidence=item&&item.evidence&&typeof item.evidence==="object"?item.evidence:{};
    return [
        item&&item.code,
        item&&item.recovery_kind,
        target.pool||evidence.pool,
        target.vdev||evidence.vdev,
        target.device||evidence.device,
        target.bay||evidence.bay,
    ].map(value=>String(value??"")).join("|");
}

function dedupeChecklists(items){
    const seen=new Set();
    return (Array.isArray(items)?items:[]).filter(item=>{
        if(!item||item.active===false) return false;
        const key=checklistIdentity(item);
        if(seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

function checklistSummary(checklists){
    const panel=document.getElementById("flightManualPanel");
    if(!panel) return;
    let rail=document.getElementById("checklistStatusRail");
    if(!checklists.length){rail?.remove();return;}
    if(!rail){
        rail=document.createElement("section");
        rail.id="checklistStatusRail";
        rail.className="cl-status-rail";
        const head=panel.querySelector(".fm-shell-head");
        if(head) head.insertAdjacentElement("afterend",rail); else panel.prepend(rail);
    }
    const counts={hold:0,monitor:0,authority:0,verified:0,ready:0,active:0};
    for(const item of checklists){const key=checklistStatus(item).className;counts[key]=(counts[key]||0)+1;}
    const dominant=counts.hold?"hold":counts.monitor?"monitor":counts.authority?"authority":counts.verified===checklists.length?"verified":"active";
    rail.className=`cl-status-rail ${dominant}`;
    const markup=`<div><span class="cl-kicker">CHECKLIST STATUS</span><strong>${esc(checklists.length)} active procedure${checklists.length===1?"":"s"}</strong></div><div class="cl-rail-counts">${counts.hold?`<span class="hold">${counts.hold} HOLD</span>`:""}${counts.monitor?`<span class="monitor">${counts.monitor} MONITOR</span>`:""}${counts.authority?`<span class="authority">${counts.authority} AUTHORITY HOLD</span>`:""}${counts.ready?`<span class="ready">${counts.ready} READY</span>`:""}${counts.active?`<span class="active">${counts.active} ACTIVE</span>`:""}${counts.verified?`<span class="verified">${counts.verified} VERIFIED</span>`:""}</div>`;
    setStableInnerHTML(rail,markup);
}

function renderChecklists(payload){
    const checklists=dedupeChecklists(payload.operator_checklists);
    checklistSummary(checklists);

    const cards=[
        ...document.querySelectorAll(
            ".fm-card[data-guidance-code]"
        ),
    ];

    const buckets=new Map();

    for(const card of cards){
        const code=String(card.dataset.guidanceCode||"");
        if(!buckets.has(code)) buckets.set(code,[]);
        buckets.get(code).push(card);
    }

    const desired=new Map();

    for(const checklist of checklists){
        const cardsForCode=
            buckets.get(String(checklist.code||""))||[];
        const card=cardsForCode.shift();

        if(!card) continue;

        desired.set(
            card,
            checklistCard(checklist),
        );
    }

    for(const card of cards){
        const markup=desired.get(card)||"";

        if(checklistMarkupByCard.get(card)===markup){
            continue;
        }

        card.querySelectorAll(
            ".cl-panel"
        ).forEach(node=>node.remove());

        if(markup){
            const callout=card.querySelector(".fm-callout");

            if(callout){
                callout.insertAdjacentHTML(
                    "afterend",
                    markup,
                );
            }else{
                card.insertAdjacentHTML(
                    "afterbegin",
                    markup,
                );
            }
        }

        checklistMarkupByCard.set(
            card,
            markup,
        );
    }
}

function ledgerIdentity(item){
    if(item&&item.id) return `id:${item.id}`;
    const session=item&&item.last_session&&typeof item.last_session==="object"?item.last_session:{};
    const target=session.target&&typeof session.target==="object"?session.target:{};
    return ["fallback",item&&item.fault_key,item&&item.attempt,target.pool,target.vdev,target.device,target.bay].map(value=>String(value??"")).join("|");
}

function dedupeLedger(items){
    const seen=new Set();
    const result=[];
    for(const item of Array.isArray(items)?items:[]){
        if(!item||typeof item!=="object") continue;
        const key=ledgerIdentity(item);
        if(seen.has(key)) continue;
        seen.add(key);
        result.push(item);
    }
    return result;
}

function ledgerTarget(item){
    const session=item&&item.last_session&&typeof item.last_session==="object"?item.last_session:{};
    const target=session.target&&typeof session.target==="object"?session.target:{};
    const bits=[];
    if(target.pool) bits.push(String(target.pool));
    if(target.vdev) bits.push(String(target.vdev));
    if(target.bay) bits.push(`Bay ${target.bay}`);
    if(target.device) bits.push(`/dev/${target.device}`);
    return bits.join(" · ")||"Target unavailable";
}

function ledgerRow(item){
    const session=item.last_session||{};
    const completed=item.status==="completed";
    const status=completed?"VERIFIED":"ACTIVE";
    const attempt=Number(item.attempt||0);
    return `<div class="ll-ledger-row ${completed?"complete":"active"}" data-lifeline-session-id="${esc(item.id||"")}"><div><span>${esc(status)}</span><strong>${esc(session.title||"Drive recovery")}</strong><small>${esc(ledgerTarget(item))}${attempt?` · Attempt ${esc(attempt)}`:""}</small></div><div><strong>${esc(label(session.phase||"unknown"))}</strong>${!completed&&item.healthy_observations!=null?`<small>${esc(item.healthy_observations)} / 3 recovery samples</small>`:""}</div></div>`;
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

function renderLifeline(payload){
    const guidance=Array.isArray(
        payload.operator_guidance
    )?payload.operator_guidance:[];

    const checklists=dedupeChecklists(
        payload.operator_checklists
    );

    const checklistCodes=new Set(
        checklists.map(
            item=>String(item.code||"")
        )
    );

    const cards=[
        ...document.querySelectorAll(
            ".fm-card[data-guidance-code]"
        ),
    ];

    const cardsByCode=new Map();

    for(const card of cards){
        const code=String(
            card.dataset.guidanceCode||""
        );

        if(!cardsByCode.has(code)){
            cardsByCode.set(code,[]);
        }

        cardsByCode.get(code).push(card);
    }

    /*
     * CHECKLIST is the primary current-recovery presentation.
     * Keep the legacy Lifeline full card only as a fallback
     * when no matching CHECKLIST exists.
     */
    const desiredFallback=new Map();
    const renderedFallback=new Set();

    for(
        const item of guidance.filter(
            entry=>entry&&entry.repair_session
        )
    ){
        const code=String(item.code||"");

        if(checklistCodes.has(code)||renderedFallback.has(code)) continue;

        const candidates=cardsByCode.get(code)||[];
        const card=candidates[0];

        if(!card) continue;

        desiredFallback.set(
            card,
            sessionCard(item.repair_session),
        );

        renderedFallback.add(code);
    }

    for(const card of cards){
        const markup=desiredFallback.get(card)||"";

        if(lifelineMarkupByCard.get(card)===markup){
            continue;
        }

        card.querySelectorAll(
            ".ll-session"
        ).forEach(node=>node.remove());

        if(markup){
            card.insertAdjacentHTML(
                "beforeend",
                markup,
            );
        }

        lifelineMarkupByCard.set(
            card,
            markup,
        );
    }

    const ledger=dedupeLedger(
        payload.lifeline&&payload.lifeline.sessions
    );

    const container=ledgerContainer();

    if(!container) return;

    if(!ledger.length){
        setStableInnerHTML(container,"");
        container.style.display="none";
        return;
    }

    const active=ledger.filter(
        item=>item.status==="active"
    );

    const completed=ledger.filter(
        item=>item.status==="completed"
    );

    const recentCompleted=
        completed.slice(-3).reverse();

    const markup=`
        <div class="ll-ledger-title"><div><span class="ll-kicker">REPAIR LEDGER</span><h3>Persistent repair sessions</h3></div><span>${esc(active.length)} active · ${esc(completed.length)} completed</span></div>
        ${active.length?`<div class="ll-ledger-note"><strong>Active recovery is presented once in Project CHECKLIST above.</strong><span>The ledger keeps identity and progress without opening another full recovery card.</span></div><div class="ll-ledger-rows">${active.map(ledgerRow).join("")}</div>`:""}
        ${recentCompleted.length?`<details class="ll-ledger-history"><summary>Recent repair history <strong>${esc(completed.length)} completed</strong></summary><div class="ll-ledger-rows">${recentCompleted.map(ledgerRow).join("")}</div></details>`:""}`;

    container.style.display="block";
    setStableInnerHTML(
        container,
        markup,
    );
}

function installStyles(){
    if(document.getElementById("lifelineStyles")) return;
    const style=document.createElement("style");
    style.id="lifelineStyles";
    style.textContent=`
.ll-session,.cl-panel{margin-top:1rem;padding:1rem;border:1px solid var(--edge);border-radius:12px;background:color-mix(in srgb,var(--panel-solid) 28%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}
.ll-session{border-color:color-mix(in srgb,var(--good) 35%,transparent)}.ll-session.complete,.cl-panel.verified{border-color:color-mix(in srgb,var(--good) 60%,transparent)}.cl-panel.hold{border-color:color-mix(in srgb,var(--bad) 45%,transparent)}.cl-panel.monitor{border-color:color-mix(in srgb,var(--accent) 50%,transparent)}.cl-panel.authority{border-color:color-mix(in srgb,var(--warn) 48%,transparent)}
.ll-head,.cl-head,.ll-ledger-title,.cl-status-rail{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.ll-head h4,.cl-head h4{margin:.2rem 0;font-size:1rem}.ll-kicker,.cl-kicker{font-size:.62rem;font-weight:900;letter-spacing:.12em}.ll-kicker{color:var(--good)}.cl-kicker{color:var(--accent)}
.ll-mode,.cl-status,.cl-readonly,.cl-rail-counts span{display:inline-block;padding:.28rem .45rem;border:1px solid var(--edge);border-radius:999px;font-size:.6rem;font-weight:900}.ll-mode,.cl-readonly{color:var(--muted)}.cl-status.hold,.cl-rail-counts .hold{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 45%,transparent)}.cl-status.monitor,.cl-rail-counts .monitor,.cl-status.active,.cl-rail-counts .active{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 42%,transparent)}.cl-status.authority,.cl-rail-counts .authority{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 42%,transparent)}.cl-status.ready,.cl-status.verified,.cl-rail-counts .ready,.cl-rail-counts .verified{color:var(--good);border-color:color-mix(in srgb,var(--good) 42%,transparent)}
.ll-progress,.cl-progress{margin:.75rem 0}.ll-progress-line,.cl-progress>div:first-child{display:flex;justify-content:space-between;gap:1rem;color:var(--muted);font-size:.7rem}.ll-track,.cl-track{height:6px;margin-top:.35rem;border-radius:999px;background:color-mix(in srgb,var(--edge) 14%,transparent);overflow:hidden}.ll-track span,.cl-track span{display:block;height:100%;background:var(--accent)}.ll-track span{background:var(--good)}
.ll-session>p,.cl-summary{color:var(--muted);font-size:.8rem;line-height:1.45}.ll-target,.cl-state-note,.cl-boundary{display:grid;gap:.2rem;margin:.7rem 0;padding:.6rem;border:1px solid var(--edge);border-radius:8px}.ll-target span,.ll-session h5,.cl-panel h5,.cl-mission-rail span{color:var(--muted);font-size:.62rem;letter-spacing:.09em;text-transform:uppercase}.cl-state-note span,.cl-boundary span{color:var(--muted);font-size:.68rem;line-height:1.4}
.ll-grid,.cl-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.cl-grid{grid-template-columns:minmax(0,1.25fr) minmax(220px,.75fr);margin-top:.8rem}.ll-gates,.cl-preflight,.cl-capabilities,.cl-procedures{display:grid;gap:.4rem}.ll-gate,.cl-gate{display:grid;grid-template-columns:70px 1fr;gap:.55rem;padding:.5rem;border:1px solid var(--edge);border-radius:8px}.cl-gate{grid-template-columns:112px 1fr}.ll-gate>span,.cl-gate>span{font-size:.6rem;font-weight:900}.ll-gate.ok>span,.cl-gate.verified>span{color:var(--good)}.ll-gate.hold>span,.cl-gate.hold>span{color:var(--bad)}.cl-gate.monitor>span{color:var(--accent)}.cl-gate strong,.ll-gate strong{display:block;font-size:.74rem}.cl-gate small,.ll-gate small{display:block;margin-top:.12rem;color:var(--muted);font-size:.66rem;line-height:1.35}
.ll-replacement,.ll-authority{display:grid;gap:.25rem;padding:.65rem;border:1px solid var(--edge);border-radius:8px;font-size:.72rem}.ll-replacement span,.ll-authority span{color:var(--muted);line-height:1.4}.ll-replacement.ok{border-color:color-mix(in srgb,var(--good) 35%,transparent)}.ll-replacement.hold,.ll-authority.locked{border-color:color-mix(in srgb,var(--bad) 35%,transparent)}.ll-replacement em{display:inline-block;margin:.3rem .25rem 0 0;padding:.2rem .35rem;border:1px solid var(--edge);border-radius:999px;color:var(--bad);font-size:.6rem;font-style:normal}.ll-authority{margin-top:.6rem}.ll-authority.locked strong{color:var(--bad)}
.ll-warnings,.cl-warnings{display:grid;gap:.3rem;margin:.65rem 0}.ll-warnings div,.cl-warnings div{padding:.45rem .55rem;border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);border-radius:7px;background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn);font-size:.7rem}.ll-verify{margin:.6rem 0;padding:.45rem .55rem;border:1px solid color-mix(in srgb,var(--accent) 25%,transparent);border-radius:7px;color:var(--muted);font-size:.72rem}
.ll-ledger{margin-top:1rem;padding-top:.6rem;border-top:1px solid color-mix(in srgb,var(--edge) 14%,transparent)}.ll-ledger-title{align-items:center}.ll-ledger-title h3{margin:.3rem 0}.ll-ledger-title>span{color:var(--muted);font-size:.7rem}.ll-ledger-note{display:grid;gap:.18rem;margin:.6rem 0;padding:.55rem;border:1px solid color-mix(in srgb,var(--accent) 24%,transparent);border-radius:8px}.ll-ledger-note strong{font-size:.7rem}.ll-ledger-note span{color:var(--muted);font-size:.66rem}.ll-ledger-rows{display:grid;gap:.4rem}.ll-ledger-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(100px,.6fr);gap:.7rem;padding:.55rem;border:1px solid var(--edge);border-radius:8px}.ll-ledger-row>div{display:grid;gap:.12rem;min-width:0}.ll-ledger-row>div:last-child{text-align:right}.ll-ledger-row span{font-size:.58rem;font-weight:900;color:var(--accent)}.ll-ledger-row.complete span{color:var(--good)}.ll-ledger-row strong{font-size:.7rem;overflow-wrap:anywhere}.ll-ledger-row small{color:var(--muted);font-size:.62rem;line-height:1.35}.ll-ledger-history{margin-top:.6rem;border:1px solid var(--edge);border-radius:8px}.ll-ledger-history summary{display:flex;justify-content:space-between;gap:.6rem;padding:.55rem;cursor:pointer;font-size:.68rem}.ll-ledger-history>div{padding:0 .55rem .55rem}
.cl-status-rail{align-items:center;margin:.2rem 0 1rem;padding:.7rem .8rem;border:1px solid color-mix(in srgb,var(--accent) 26%,transparent);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 28%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.cl-status-rail>div:first-child{display:grid;gap:.15rem}.cl-rail-counts,.cl-head-badges{display:flex;gap:.35rem;flex-wrap:wrap;justify-content:flex-end}.cl-mission-rail{display:grid;grid-template-columns:minmax(130px,.55fr) minmax(0,1.4fr) minmax(150px,.65fr);gap:.5rem;margin:.75rem 0}.cl-mission-rail>div{display:grid;gap:.16rem;padding:.55rem;border:1px solid var(--edge);border-radius:8px;min-width:0}.cl-mission-rail strong{font-size:.76rem;overflow-wrap:anywhere}
.cl-empty{padding:.6rem;border:1px solid var(--edge);border-radius:8px;color:var(--muted);font-size:.7rem;line-height:1.4}.cl-capabilities>div{display:flex;justify-content:space-between;gap:.6rem;padding:.48rem .55rem;border:1px solid var(--edge);border-radius:8px;font-size:.68rem}.cl-capabilities span{color:var(--muted)}.cl-capabilities .verified strong{color:var(--good)}.cl-capabilities .blocked strong{color:var(--bad)}
.cl-procedure{border:1px solid var(--edge);border-radius:9px;overflow:hidden}.cl-procedure summary{display:flex;justify-content:space-between;gap:1rem;padding:.6rem .7rem;cursor:pointer;list-style:none;font-size:.72rem;font-weight:850}.cl-procedure summary::-webkit-details-marker{display:none}.cl-procedure summary strong{color:var(--muted);font-size:.64rem}.cl-procedure>div{padding:0 .7rem .35rem}.cl-step{padding:.65rem 0;border-top:1px solid color-mix(in srgb,var(--edge) 10%,transparent)}.cl-step-head{display:flex;justify-content:space-between;gap:.5rem;align-items:flex-start;margin-bottom:.28rem}.cl-step-head>span{font-size:.58rem;font-weight:900}.cl-step.verified .cl-step-head>span{color:var(--good)}.cl-step.hold .cl-step-head>span{color:var(--bad)}.cl-step.blocked .cl-step-head>span{color:var(--warn)}.cl-step.pending .cl-step-head>span{color:var(--muted)}.cl-step>strong{font-size:.76rem}.cl-step p{margin:.25rem 0 0;color:var(--muted);font-size:.7rem;line-height:1.4}.cl-chip{display:inline-block;margin-left:.25rem;padding:.17rem .3rem;border:1px solid var(--edge);border-radius:999px;font-size:.54rem;font-style:normal;font-weight:900}.cl-chip.verified{color:var(--good)}.cl-chip.hold{color:var(--warn)}.cl-chip.blocked{color:var(--bad)}.cl-boundary{border-style:dashed}
@media(max-width:760px){.ll-grid,.cl-grid,.cl-mission-rail{grid-template-columns:1fr}.ll-head,.ll-ledger-title,.cl-status-rail,.cl-head{display:block}.ll-mode{margin-top:.4rem}.cl-rail-counts,.cl-head-badges{justify-content:flex-start;margin-top:.5rem}.cl-gate{grid-template-columns:92px 1fr}.cl-step-head{display:block}.cl-step-head>div{margin-top:.25rem}.cl-chip{margin:.2rem .25rem 0 0}.cl-procedure summary{align-items:center}.ll-ledger-row{grid-template-columns:1fr}.ll-ledger-row>div:last-child{text-align:left}}
`;
    document.head.appendChild(style);
}

function apply(payload){
    renderChecklists(payload);
    renderLifeline(payload);
}

async function refresh(){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) return;
        apply(await response.json());
    }catch(_error){
        // Flight Manual owns the unavailable state. Lifeline and CHECKLIST stay
        // silent rather than inventing a second error surface.
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
