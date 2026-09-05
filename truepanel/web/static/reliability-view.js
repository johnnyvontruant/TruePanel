(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
const title=value=>String(value||"")
    .replaceAll("_"," ")
    .replace(/\b\w/g,char=>char.toUpperCase());

function signalRows(items){
    const signals=Array.isArray(items)?items.slice(0,6):[];
    if(!signals.length) return '<div class="ag-empty">No abnormal supporting signals.</div>';
    return signals.map(item=>{
        const value=item?.value===undefined||item?.value===null?"":` · ${item.value}`;
        return `<div class="ag-signal"><span>${esc(item?.source||"evidence")}</span><strong>${esc(title(item?.signal||"signal"))}${esc(value)}</strong><small>${esc(title(item?.state||"observed"))}</small></div>`;
    }).join("");
}

function gapRows(matrix){
    const entries=Array.isArray(matrix?.entries)?matrix.entries:[];
    const gaps=entries.filter(item=>item?.coverage_state!=="TRUSTED");
    if(!gaps.length) return '<div class="ag-gap-clear">All actionable alert paths are covered and rehearsed.</div>';
    return gaps.map(item=>`<div class="ag-gap"><strong>${esc(item?.code||"unknown")}</strong><span>${esc((item?.gaps||[]).join(" · ")||"Coverage incomplete")}</span></div>`).join("");
}

function evidenceGateRows(gate){
    const measurements=gate?.measurements||{};
    const gaps=Array.isArray(gate?.gaps)?gate.gaps:[];
    const metrics=`95% FPR upper ${Math.round(Number(measurements.false_positive_rate_wilson_upper||0)*10000)/100}% · recall lower ${Math.round(Number(measurements.recall_wilson_lower||0)*100)}%`;
    const gapList=gaps.slice(0,4).map(item=>`<div class="ag-gap"><strong>HOLD</strong><span>${esc(item)}</span></div>`).join("");
    return `<div class="ag-evidence-metric">${esc(metrics)}</div>${gapList}${gaps.length>4?`<div class="ag-gap"><strong>HOLD</strong><span>${gaps.length-4} additional evidence gaps</span></div>`:""}`;
}

function fieldWorkflowRows(workflow){
    const stages=Array.isArray(workflow?.stages)?workflow.stages:[];
    const state=title(workflow?.state||"not started");
    const stageList=stages.map(item=>`<span>${esc(title(item))}</span>`).join("");
    return `<div class="ag-workflow-state"><strong>${esc(state)}</strong><small>${esc(workflow?.next_action||"Awaiting explicit operator consent")}</small></div><div class="ag-workflow-steps">${stageList}</div>`;
}

function airworthinessView(assurance){
    if(!assurance?.status) return "";
    const status=String(assurance.status).toUpperCase();
    const tone=status==="CURRENT"?"ready":(status==="REVIEW"?"review":"hold");
    const conditions=(Array.isArray(assurance.conditions)?assurance.conditions:[]).map(item=>{
        const state=item?.status==="True"?"PASS":(item?.status==="False"?"HOLD":"REVIEW");
        return `<article class="ag-assurance-condition ${state.toLowerCase()}"><span>${esc(state)}</span><strong>${esc(title(item?.type||"condition"))}</strong><small>${esc(item?.message||"")}</small></article>`;
    }).join("");
    const witness=assurance.platform_witness||{};
    const witnessAge=Number.isFinite(Number(witness.age_seconds))?`${Math.round(Number(witness.age_seconds))}s old`:"age unavailable";
    return `<section class="ag-assurance ${tone}" aria-label="AEGIS airworthiness envelope">
        <div><span class="ag-kicker">Project AIRWORTHINESS</span><strong>${esc(title(status))}</strong><p>${esc(assurance.message||"Acceptance-envelope status unavailable.")}</p></div>
        <div class="ag-assurance-scope"><small>VALIDATED SCOPE</small><strong>${esc(assurance.platform_scope||"Unknown platform")}</strong><span>Witness ${esc(witness.status||"UNBOUND")} · ${esc(witness.source||"no source")} · ${esc(witnessAge)}</span><span>Review by ${esc(assurance.expires_at||"unknown")}</span></div>
        <details><summary>Validation envelope · ${esc(String(assurance.envelope_id||"").replaceAll("-"," "))}</summary><div class="ag-assurance-grid">${conditions}</div><small>Raw alerts and recovery guidance remain visible in every state. Control authority false.</small></details>
    </section>`;
}

function storageFlightDirectorView(flight){
    const identity=flight?.identity||{};
    const topology=flight?.topology||{};
    const gate=flight?.action_gate||{};
    const verification=flight?.verification_signature||{};
    const evidence=flight?.evidence||{};
    const clearance=flight?.pre_service_clearance||{};
    const evidenceLedger=clearance?.evidence_ledger||{};
    const clearanceReady=clearance?.status==="READY_FOR_OPERATOR_REVIEW";
    const clearanceGates=(Array.isArray(clearance?.gates)?clearance.gates:[]).map(item=>`<article class="fd-clearance-gate ${item?.satisfied?"ready":"hold"}"><span>${item?.satisfied?"PASS":"HOLD"}</span><strong>${esc(title(item?.code||"unknown gate"))}</strong><small>${esc(item?.detail||"")}</small></article>`).join("");
    const acceptedAttestations=(Array.isArray(evidenceLedger?.accepted)?evidenceLedger.accepted:[]).map(item=>`<article><span>ACCEPTED</span><strong>${esc(title(item?.kind||"evidence"))}</strong><small>${esc(item?.provider?.id||"provider unknown")} · ${esc(title(item?.provider?.mode||"mode unknown"))}</small></article>`).join("");
    const rejectedAttestations=(Array.isArray(evidenceLedger?.rejected)?evidenceLedger.rejected:[]).map(item=>`<article class="hold"><span>HOLD</span><strong>${esc(title(item?.kind||"evidence"))}</strong><small>${esc((item?.errors||[]).join(" · ")||"Evidence rejected")}</small></article>`).join("");
    const missingAttestations=(Array.isArray(evidenceLedger?.missing_kinds)?evidenceLedger.missing_kinds:[]).map(kind=>`<article class="hold"><span>MISSING</span><strong>${esc(title(kind))}</strong><small>No acceptable incident-bound provider statement.</small></article>`).join("");
    const identityLabel=`Bay ${identity.bay??"unknown"} · ${identity.device||"device unknown"} · ${identity.model||"model unknown"} · …${identity.serial_last4||"serial unknown"}`;
    const smartLabel=`${Number(evidence.reallocated||0).toLocaleString()} reallocated · ${Number(evidence.pending||0).toLocaleString()} pending · ${Number(evidence.offline_uncorrectable||0).toLocaleString()} offline uncorrectable`;
    const blockers=Array.isArray(gate.blocked_by)?gate.blocked_by:[];
    const aborts=Array.isArray(flight.abort_conditions)?flight.abort_conditions:[];
    const rehearsals=(Array.isArray(flight.rehearsals)?flight.rehearsals:[]).map(item=>`<article><strong>${esc(title(item.choice))}</strong><span>${esc(title(item.outcome))}</span><small>${esc(item.reason)}</small></article>`).join("");
    return `<section class="fd-shell" aria-label="CHECKRIDE live storage flight plan">
        <div class="fd-head"><div><span class="ag-kicker">Project CHECKRIDE · Live Storage Flight Plan</span><h3>Now / Next / Why / Proof</h3></div><span class="fd-hold">ADVISORY · PHYSICAL SERVICE HOLD</span></div>
        <div class="fd-command">
            <article><small>NOW</small><strong>${esc(identityLabel)}</strong><span>Incident-bound passive identity</span></article>
            <article><small>NEXT</small><strong>Keep the drive installed</strong><span>${esc(flight.safest_action)}</span></article>
            <article><small>WHY</small><strong>Critical raw SMART evidence</strong><span>${esc(smartLabel)} while ZFS reports ${esc(topology.zfs_state||"unknown")}</span></article>
            <article><small>PROOF</small><strong>${esc(title(verification.status||"pending"))}</strong><span>Recovery requires the machine-verifiable post-repair signature.</span></article>
        </div>
        <div class="fd-instruments">
            <article><h4>Identity</h4><strong>${esc(identityLabel)}</strong><span>${identity.verified_from_passive_evidence?"Physical and logical fields present":"Identity gaps remain"}</span></article>
            <article><h4>Safety margin</h4><strong>${esc(topology.pool||"pool unknown")} · ${esc(topology.vdev||"VDEV unknown")}</strong><span>${esc(topology.vdev_topology||"topology unknown")} · redundancy ${esc(topology.remaining_redundancy??"unknown")} · backup ${flight.backup_context?.independent_backup_confirmed?"confirmed":"confirmation required"}</span></article>
            <article><h4>Action gate</h4><strong class="fd-number ${clearanceReady?"ready":""}">${clearanceReady?"REVIEW READY":"HOLD"}</strong><span>${esc(blockers.length?blockers.map(title).join(" · "):"Evidence complete · external service only · execution locked")}</span></article>
        </div>
        <section class="fd-clearance" aria-label="Pre-service clearance">
            <div><h4>Pre-service clearance</h4><strong class="${clearanceReady?"ready":"hold"}">${esc(title(clearance?.status||"hold"))}</strong><span>${clearanceReady?"Evidence is complete for an operator to review the external service plan. TruePanel still has no physical-service or storage-write authority.":"Missing or stale evidence keeps the drive installed and the service plan on hold."}</span></div>
            <div class="fd-clearance-gates">${clearanceGates}</div>
            <small>Receipt ${esc(String(clearance?.receipt_sha256||"").slice(0,16))}… · expires after ${esc(clearance?.expires_after_seconds??"unknown")} seconds · control authority false</small>
        </section>
        <section class="fd-attestations" aria-label="Recovery evidence provenance">
            <div><h4>Ground Truth Evidence</h4><strong class="${evidenceLedger?.status==="EVIDENCE_READY"?"ready":"hold"}">${esc(title(evidenceLedger?.status||"hold"))}</strong><span>Freshness, incident binding, provider provenance, subject identity, and digest integrity are checked independently.</span></div>
            <div class="fd-attestation-grid">${acceptedAttestations}${rejectedAttestations}${missingAttestations}</div>
            <small>Ledger ${esc(String(evidenceLedger?.ledger_sha256||"").slice(0,16))}… · ${esc(title(evidenceLedger?.evidence_maturity||"unknown maturity"))} · digest authenticates provider: NO</small>
        </section>
        <div class="fd-aborts"><h4>Abort conditions</h4><ul>${aborts.map(item=>`<li>${esc(item)}</li>`).join("")}</ul></div>
        <div class="fd-rehearsals"><h4>HoloDeck Recovery Rehearsals</h4><div>${rehearsals}</div></div>
        <p class="ag-safety">Evidence maturity: passive live diagnosis; repair not yet field validated · Control authority false · SHA-256 ${esc(String(flight.evidence_sha256||"").slice(0,16))}…</p>
    </section>`;
}

function flightDirectorView(flight,activeIncident){
    if(!flight?.scenario) return "";
    const activeIncidentId=activeIncident?.incident_id||"";
    const boundIncidentId=flight?.incident_id||"";
    const appliesToActiveIncident=flight?.presentation_scope==="active_incident"
        && flight?.applies_to_active_incident===true
        && Boolean(activeIncidentId)
        && boundIncidentId===activeIncidentId;
    if(!appliesToActiveIncident){
        return `<details class="fd-shell fd-reference">
            <summary><span><strong>HoloDeck reference rehearsal</strong><small>Not this incident</small></span><span class="fd-hold">LAB FIXTURE · CONTROL AUTHORITY FALSE</span></summary>
            <p>The ${esc(title(flight.scenario))} scenario is preserved for training and regression coverage. It does not explain or guide the active incident.</p>
            <p class="ag-safety">Evidence maturity: ${esc(title(flight.evidence_maturity||"deterministic lab fixture"))}, not field or production validation · SHA-256 ${esc(String(flight.evidence_sha256||"").slice(0,16))}…</p>
        </details>`;
    }
    if(flight?.domain==="storage") return storageFlightDirectorView(flight);
    const incident=flight.incident||{};
    const forecast=flight.forecast||{};
    const measurements=flight.measurements||{};
    const timeline=(Array.isArray(flight.timeline)?flight.timeline:[]).map(item=>`<li><strong>${esc(item.sample)}</strong><span>${esc(item.event)}</span></li>`).join("");
    const unknowns=(Array.isArray(flight.topology?.nodes)?flight.topology.nodes:[]).filter(item=>item?.certainty==="unknown");
    const rehearsals=(Array.isArray(flight.rehearsals)?flight.rehearsals:[]).map(item=>`<article><strong>${esc(title(item.choice))}</strong><span>${esc(item.result)}</span><small>${item.projected_threshold_crossing_sample===null?"no crossing in window":`crossing sample ${esc(item.projected_threshold_crossing_sample)}`}</small></article>`).join("");
    const observations=Array.isArray(flight.recovery_plan?.expected_recovery_observations)?flight.recovery_plan.expected_recovery_observations:[];
    return `<section class="fd-shell" aria-label="Flight Director lab proof">
        <div class="fd-head"><div><span class="ag-kicker">Project Flight Director · Lab Proof</span><h3>Now / Next / Why / Proof</h3></div><span class="fd-hold">SIMULATION · CONTROL AUTHORITY FALSE</span></div>
        <div class="fd-command">
            <article><small>NOW</small><strong>${esc(incident.likely_cause||"Shared cooling proof")}</strong><span>Detected ${esc(measurements.detection_lead_samples||0)} samples before isolated thresholds.</span></article>
            <article><small>NEXT</small><strong>Verify identity and external airflow</strong><span>${esc(flight.recovery_plan?.safest_action||"")}</span></article>
            <article><small>WHY</small><strong>Independent fan + thermal evidence</strong><span>${esc(measurements.timeline_clarity||"")}</span></article>
            <article><small>PROOF</small><strong>${esc(title(flight.verification?.outcome||"pending"))}</strong><span>${esc(observations.join(" · "))}</span></article>
        </div>
        <div class="fd-instruments">
            <article><h4>Incident Time Machine</h4><ol class="fd-timeline">${timeline}</ol></article>
            <article><h4>Safe Operating Envelope</h4><strong class="fd-number">${esc(forecast.estimated_crossing_sample??"—")}</strong><span>estimated warning sample · ±${esc(forecast.uncertainty_samples??"—")} lab samples</span><small>${esc(forecast.precision_disclosure||"")}</small></article>
            <article><h4>Causal Hardware Map</h4><strong class="fd-number">${esc(flight.topology?.nodes?.length||0)}</strong><span>nodes · ${unknowns.length} identity gaps explicitly unknown</span><small>No bay, drive, VDEV, pool, or fan channel is inferred.</small></article>
        </div>
        <div class="fd-rehearsals"><h4>HoloDeck What-If Rehearsals</h4><div>${rehearsals}</div></div>
        <p class="ag-safety">Evidence maturity: deterministic lab fixture, not field or production validation · SHA-256 ${esc(String(flight.evidence_sha256||"").slice(0,16))}…</p>
    </section>`;
}

function render(view,payload){
    const reliability=payload?.reliability||{};
    const incident=reliability?.active_incident||null;
    const matrix=reliability?.coverage_matrix||{};
    const summary=reliability?.coverage_summary||{};
    const policy=reliability?.correlation_policy||{};
    const calibration=policy?.calibration||{};
    const evidenceGate=calibration?.evidence_gate||{};
    const fieldWorkflow=calibration?.field_workflow||{};
    const flightDirector=reliability?.flight_director||{};
    const passiveEvidence=reliability?.passive_evidence||{};
    const airworthiness=reliability?.airworthiness||{};
    const oracleConfidence=Number(reliability?.oracle?.confidence||0);
    const confidence=Math.round(Number(incident?.confidence??oracleConfidence)*100);
    const state=incident
        ?"CORRELATED INCIDENT"
        :(oracleConfidence<1?"LEARNING BASELINE":"NO ACTIVE INCIDENT");
    const cause=incident?.likely_cause||"No probable shared cause is active";
    const hypothesis=incident?.hypothesis||"AEGIS is watching for related telemetry that should be handled as one incident.";
    const action=incident?.safest_next_action||"Continue passive monitoring; no recovery action is currently required.";
    const verification=incident?.verification_state||"not required";
    const trusted=Number(summary.trusted||0);
    const total=Number(summary.total||0);
    const gaps=Number(summary.gaps||0);
    const roleGate=passiveEvidence.role_verification||{};
    const receiptStore=passiveEvidence.receipt_store||{};
    const passiveCache=passiveEvidence.cache||{};
    const cacheAge=Number(passiveCache.last_age_seconds);
    const hasCacheAge=passiveCache.last_age_seconds!==null&&passiveCache.last_age_seconds!==undefined&&Number.isFinite(cacheAge);
    const passivePanel=Object.keys(passiveEvidence).length?`<details class="ag-coverage ag-passive-evidence"><summary>Passive TrueNAS Evidence <span>${passiveEvidence.restore_verified?"restore verified":"HOLD"}</span></summary><div class="ag-evidence-metric"><strong>${esc(passiveEvidence.successful_tasks??0)} successful protection task(s)</strong><br>${esc(passiveEvidence.restore_verified?"A separate restore-verification receipt matched the active incident.":passiveEvidence.hold_reason||"No governed restore verification is available.")}<br>Role gate: ${esc(roleGate.status||"not checked")} · ${esc(roleGate.reason||"No session-role evidence.")}<br>Receipt store: ${receiptStore.governed===true?"GOVERNED":"HOLD"} · ${esc(receiptStore.reason||"Not configured.")}<br>Cache: ${esc(passiveCache.last_source||"inactive")}${hasCacheAge?` · ${Math.round(cacheAge)}s old`:""} · TTL ${esc(passiveCache.ttl_seconds??"unknown")}s<br>Read-only: ${passiveEvidence.read_only===true?"YES":"UNKNOWN"} · Control authority: ${passiveEvidence.control_authority===false?"NO":"UNKNOWN"}</div></details>`:"";

    view.classList.toggle("incident",Boolean(incident));
    view.innerHTML=`
        <div class="ag-head">
            <div><span class="ag-kicker">Project AEGIS · Reliability Engineer</span><h2>Reliability</h2></div>
            <div class="ag-badges"><span>READ-ONLY</span><span>${esc(policy?.policy_id||"AEGIS POLICY")}</span><span class="${calibration?.production_validated?"trusted":"lab"}">${calibration?.production_validated?"FIELD VALIDATED":"LAB CALIBRATED · NOT LIVE VALIDATED"}</span><span class="${gaps?"gap":"trusted"}">${trusted}/${total} TRUSTED</span></div>
        </div>
        <div class="ag-hero">
            <div><span class="ag-state">${esc(state)}</span><h3>${esc(cause)}</h3><p>${esc(hypothesis)}</p></div>
            <div class="ag-confidence"><strong>${confidence}%</strong><span>${incident?"hypothesis confidence":"baseline confidence"}</span></div>
        </div>
        <div class="ag-grid">
            <section><h4>Supporting signals</h4><div class="ag-signals">${signalRows(incident?.supporting_signals)}</div></section>
            <section><h4>Safest next action</h4><p class="ag-action">${esc(action)}</p><div class="ag-verify"><span>Verification</span><strong>${esc(title(verification))}</strong></div></section>
        </div>
        ${airworthinessView(airworthiness)}
        ${flightDirectorView(flightDirector,incident)}
        <details class="ag-coverage"><summary>Recovery Coverage Matrix <span>${gaps?`${gaps} gap${gaps===1?"":"s"}`:"complete"}</span></summary>${gapRows(matrix)}</details>
        <details class="ag-coverage ag-evidence"><summary>Evidence Promotion Gate <span>${evidenceGate?.eligible_for_field_validation?"field candidate":`${Number(evidenceGate?.gaps?.length||0)} holds`}</span></summary>${evidenceGateRows(evidenceGate)}</details>
        <details class="ag-coverage ag-field-workflow"><summary>Field Evidence Workflow <span>${esc(title(fieldWorkflow?.state||"not started"))}</span></summary>${fieldWorkflowRows(fieldWorkflow)}</details>
        ${passivePanel}
        <p class="ag-safety">Correlation uses ${esc(policy?.semantics||"evidence grouping")}; it retains raw alerts, grants no control authority, and performs no repair.</p>
    `;
}

async function refreshFallback(view){
    try{
        const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
        if(!response.ok) throw new Error(`status ${response.status}`);
        render(view,await response.json());
    }catch(_error){
        view.querySelector(".ag-safety")?.replaceChildren("Reliability telemetry is temporarily unavailable. No state or hardware was changed.");
    }
}

function install(){
    const cockpit=document.getElementById("cockpitOverview");
    const grid=document.querySelector("main .grid");
    if(!cockpit&&!grid){window.setTimeout(install,50);return;}
    if(document.getElementById("aegisReliabilityView")) return;

    const style=document.createElement("style");
    style.textContent=`
#aegisReliabilityView{grid-column:1/-1;padding:1.15rem 1.25rem;border-color:color-mix(in srgb,var(--good) 34%,transparent);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 64%,transparent),color-mix(in srgb,var(--panel-solid) 70%,transparent) 62%);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}#aegisReliabilityView.incident{border-color:color-mix(in srgb,var(--warn) 50%,transparent);background:linear-gradient(120deg,color-mix(in srgb,var(--panel-solid) 38%,transparent),color-mix(in srgb,var(--panel-solid) 68%,transparent) 62%);backdrop-filter:blur(16px) saturate(180%);-webkit-backdrop-filter:blur(16px) saturate(180%)}.ag-head,.ag-hero,.fd-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.ag-head h2,.fd-head h3{margin:.2rem 0 0}.ag-kicker{color:var(--good);font-size:.65rem;font-weight:900;letter-spacing:.13em;text-transform:uppercase}.incident .ag-kicker{color:var(--warn)}.ag-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.4rem}.ag-badges span,.fd-hold{padding:.3rem .48rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted);font-size:.6rem;font-weight:900}.ag-badges .trusted{color:var(--good);border-color:color-mix(in srgb,var(--good) 35%,transparent)}.ag-badges .lab,.fd-hold{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 35%,transparent)}.ag-badges .gap{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,transparent)}.ag-hero{margin-top:1rem;padding:1rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 42%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.ag-state{color:var(--good);font-size:.65rem;font-weight:900;letter-spacing:.12em}.incident .ag-state{color:var(--warn)}.ag-hero h3{margin:.3rem 0;font-size:1.25rem}.ag-hero p{max-width:760px;margin:0;color:var(--muted);font-size:.82rem;line-height:1.5}.ag-confidence{text-align:right}.ag-confidence strong{display:block;color:var(--good);font-size:1.75rem}.incident .ag-confidence strong{color:var(--warn)}.ag-confidence span{color:var(--muted);font-size:.64rem}.ag-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:.8rem;margin-top:.8rem}.ag-grid section{padding:.8rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:10px}.ag-grid h4,.fd-shell h4{margin:0 0 .55rem;color:var(--muted);font-size:.67rem;letter-spacing:.1em;text-transform:uppercase}.ag-signals{display:grid;gap:.3rem}.ag-signal{display:grid;grid-template-columns:80px minmax(0,1fr) auto;gap:.45rem;font-size:.7rem}.ag-signal span,.ag-signal small{color:var(--muted)}.ag-signal span{font-size:.58rem;font-weight:900;text-transform:uppercase}.ag-action{margin:.1rem 0 .8rem;font-size:.82rem;line-height:1.5}.ag-verify{display:flex;justify-content:space-between;gap:.6rem;padding-top:.6rem;border-top:1px solid color-mix(in srgb,var(--edge) 14%,transparent);font-size:.7rem}.ag-verify span{color:var(--muted)}.ag-verify strong{color:var(--good)}.fd-shell{margin-top:.9rem;padding:.85rem;border:1px solid color-mix(in srgb,var(--accent) 24%,transparent);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 68%,transparent);backdrop-filter:blur(18px) saturate(180%);-webkit-backdrop-filter:blur(18px) saturate(180%)}.fd-reference summary{display:flex;align-items:center;justify-content:space-between;gap:.75rem;cursor:pointer}.fd-reference summary>span:first-child{display:grid;gap:.2rem}.fd-reference summary small,.fd-reference p{color:var(--muted);font-size:.68rem}.fd-reference p{max-width:760px;line-height:1.5}.fd-command,.fd-instruments{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.5rem;margin-top:.75rem}.fd-instruments{grid-template-columns:repeat(3,minmax(0,1fr))}.fd-command article,.fd-instruments article,.fd-rehearsals article{display:grid;align-content:start;gap:.3rem;padding:.7rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:8px}.fd-command small,.fd-instruments small,.fd-rehearsals small,.fd-command span,.fd-instruments span,.fd-rehearsals span{color:var(--muted);font-size:.65rem;line-height:1.45}.fd-number{color:var(--warn);font-size:1.45rem}.fd-number.ready{color:var(--good)}.fd-timeline{display:grid;gap:.35rem;margin:0;padding:0;list-style:none}.fd-timeline li{display:grid;grid-template-columns:28px 1fr;gap:.4rem;font-size:.66rem}.fd-timeline strong{color:var(--warn)}.fd-clearance,.fd-attestations{display:grid;gap:.6rem;margin-top:.75rem;padding:.7rem;border:1px solid color-mix(in srgb,var(--edge) 20%,transparent);border-radius:8px}.fd-clearance>div:first-child,.fd-attestations>div:first-child{display:grid;gap:.25rem}.fd-clearance>div:first-child>span,.fd-clearance>small,.fd-attestations>div:first-child>span,.fd-attestations>small{color:var(--muted);font-size:.66rem;line-height:1.45}.fd-clearance strong.ready,.fd-clearance-gate.ready>span,.fd-attestations strong.ready,.fd-attestation-grid article>span{color:var(--good)}.fd-clearance strong.hold,.fd-clearance-gate.hold>span,.fd-attestations strong.hold,.fd-attestation-grid article.hold>span{color:var(--warn)}.fd-clearance-gates{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem}.fd-clearance-gate{display:grid;gap:.2rem;padding:.55rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:7px}.fd-clearance-gate>span{font-size:.58rem;font-weight:900}.fd-clearance-gate>small{color:var(--muted);font-size:.62rem;line-height:1.4}.fd-attestation-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem}.fd-attestation-grid article{display:grid;gap:.2rem;padding:.55rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:7px}.fd-attestation-grid article>span{font-size:.58rem;font-weight:900}.fd-attestation-grid article>small{color:var(--muted);font-size:.62rem;line-height:1.4}.fd-aborts{margin-top:.75rem;padding:.7rem;border:1px solid color-mix(in srgb,var(--warn) 25%,transparent);border-radius:8px}.fd-aborts ul{display:grid;gap:.3rem;margin:0;padding-left:1.1rem;color:var(--muted);font-size:.68rem;line-height:1.45}.fd-rehearsals{margin-top:.75rem}.fd-rehearsals>div{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}.ag-coverage{margin-top:.8rem;padding:.65rem .8rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:8px}.ag-coverage summary{cursor:pointer;font-size:.72rem;font-weight:800}.ag-coverage summary span{float:right;color:var(--muted)}.ag-evidence-metric{padding:.55rem 0;color:var(--muted);font-size:.7rem}.ag-workflow-state{display:grid;gap:.2rem;padding:.65rem 0}.ag-workflow-state small{color:var(--muted)}.ag-workflow-steps{display:flex;flex-wrap:wrap;gap:.35rem}.ag-workflow-steps span{padding:.3rem .45rem;border:1px solid color-mix(in srgb,var(--edge) 20%,transparent);border-radius:999px;color:var(--muted);font-size:.62rem}.ag-gap,.ag-gap-clear{display:grid;gap:.2rem;padding:.55rem 0;border-bottom:1px solid color-mix(in srgb,var(--edge) 10%,transparent);font-size:.7rem}.ag-gap span{color:var(--muted)}.ag-gap-clear{color:var(--good)}.ag-empty,.ag-safety{color:var(--muted);font-size:.68rem}.ag-safety{margin:.7rem 0 0;line-height:1.45}@media(max-width:760px){#aegisReliabilityView{padding:1rem}.ag-head,.ag-hero,.fd-head{display:block}.ag-badges{justify-content:flex-start;margin-top:.6rem}.fd-hold{display:inline-block;margin-top:.6rem}.ag-confidence{margin-top:.7rem;text-align:left}.ag-grid,.fd-command,.fd-instruments,.fd-clearance-gates,.fd-attestation-grid,.fd-rehearsals>div{grid-template-columns:1fr}.ag-signal{grid-template-columns:70px minmax(0,1fr)}.ag-signal small{grid-column:2}.fd-reference summary{align-items:flex-start}.ag-coverage summary span{display:block;float:none;margin-top:.25rem}.ag-workflow-steps{display:grid;grid-template-columns:1fr 1fr}.ag-workflow-steps span:last-child{grid-column:1/-1}}

`;
    style.textContent+=`
.ag-assurance{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.8rem;margin-top:.8rem;padding:.8rem;border:1px solid color-mix(in srgb,var(--good) 34%,transparent);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 42%,transparent)}
.ag-assurance.review{border-color:color-mix(in srgb,var(--warn) 38%,transparent)}.ag-assurance.hold{border-color:color-mix(in srgb,var(--bad) 42%,transparent)}
.ag-assurance>div:first-child{display:grid;gap:.2rem}.ag-assurance>div:first-child>strong{font-size:1rem}.ag-assurance p,.ag-assurance span,.ag-assurance small{margin:0;color:var(--muted);font-size:.66rem;line-height:1.45}
.ag-assurance-scope{display:grid;align-content:start;gap:.2rem;text-align:right}.ag-assurance-scope strong{font-size:.72rem}
.ag-assurance details{grid-column:1/-1;padding-top:.55rem;border-top:1px solid color-mix(in srgb,var(--edge) 14%,transparent)}.ag-assurance summary{cursor:pointer;font-size:.68rem;font-weight:800;min-height:44px;display:flex;align-items:center}
.ag-assurance-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.4rem;margin:.6rem 0}.ag-assurance-condition{display:grid;gap:.18rem;padding:.5rem;border:1px solid color-mix(in srgb,var(--edge) 14%,transparent);border-radius:7px}
.ag-assurance-condition span{font-size:.56rem;font-weight:900}.ag-assurance-condition.pass span{color:var(--good)}.ag-assurance-condition.review span{color:var(--warn)}.ag-assurance-condition.hold span{color:var(--bad)}.ag-assurance-condition small{overflow-wrap:anywhere}
@media(max-width:760px){.ag-assurance,.ag-assurance-grid{grid-template-columns:1fr}.ag-assurance-scope{text-align:left}}
`;
    document.head.appendChild(style);

    const view=document.createElement("article");
    view.id="aegisReliabilityView";
    view.className="card";
    view.setAttribute("aria-live","polite");
    view.innerHTML='<p class="ag-safety">Waiting for the first reliability snapshot.</p>';
    const host=cockpit||grid;
    const health=host.querySelector(".health-command");
    if(health) health.insertAdjacentElement("afterend",view);
    else host.prepend(view);

    let receivedSharedStatus=false;
    window.addEventListener("truepanel:status",event=>{
        const payload=event?.detail;
        if(!payload||typeof payload!=="object") return;
        receivedSharedStatus=true;
        render(view,payload);
    });

    window.setTimeout(()=>{
        if(!receivedSharedStatus) refreshFallback(view);
    },500);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
