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

function installStyles(){
    if(document.getElementById("lifelineStyles")) return;
    const style=document.createElement("style");
    style.id="lifelineStyles";
    style.textContent=`
.ll-session{margin-top:1rem;padding:1rem;border:1px solid rgba(90,220,170,.35);border-radius:12px;background:rgba(5,20,18,.34)}.ll-session.complete{border-color:rgba(90,220,170,.65);background:rgba(8,46,34,.3)}.ll-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.ll-head h4{margin:.2rem 0;font-size:1rem}.ll-kicker{color:var(--good);font-size:.62rem;font-weight:900;letter-spacing:.12em}.ll-mode{padding:.28rem .5rem;border:1px solid var(--edge);border-radius:999px;color:var(--muted);font-size:.62rem;font-weight:900}.ll-session.complete .ll-mode{color:var(--good);border-color:rgba(90,220,170,.4)}.ll-progress{margin:.8rem 0}.ll-progress-line{display:flex;justify-content:space-between;font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.ll-track{height:6px;margin-top:.4rem;border-radius:999px;background:rgba(143,164,184,.14);overflow:hidden}.ll-track span{display:block;height:100%;background:var(--good)}.ll-session>p{color:var(--muted);font-size:.82rem;line-height:1.45}.ll-target{display:grid;gap:.2rem;margin:.8rem 0;padding:.7rem;border:1px solid var(--edge);border-radius:8px}.ll-target span,.ll-session h5{color:var(--muted);font-size:.66rem;letter-spacing:.09em;text-transform:uppercase}.ll-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.ll-gates{display:grid;gap:.4rem}.ll-gate{display:grid;grid-template-columns:52px 1fr;gap:.55rem;padding:.5rem;border:1px solid var(--edge);border-radius:8px}.ll-gate>span{font-size:.65rem;font-weight:900}.ll-gate.ok>span{color:var(--good)}.ll-gate.hold>span{color:var(--bad)}.ll-gate strong{display:block;font-size:.76rem}.ll-gate small{display:block;margin-top:.15rem;color:var(--muted);font-size:.68rem;line-height:1.35}.ll-replacement,.ll-authority{display:grid;gap:.25rem;padding:.65rem;border:1px solid var(--edge);border-radius:8px;font-size:.75rem}.ll-replacement span,.ll-authority span{color:var(--muted);line-height:1.4}.ll-replacement.ok{border-color:rgba(90,220,170,.35)}.ll-replacement.hold,.ll-authority.locked{border-color:rgba(255,93,115,.35)}.ll-replacement em{display:inline-block;margin:.3rem .25rem 0 0;padding:.2rem .35rem;border:1px solid var(--edge);border-radius:999px;color:var(--bad);font-size:.6rem;font-style:normal}.ll-authority{margin-top:.6rem}.ll-authority.ready strong{color:var(--warn)}.ll-authority.locked strong{color:var(--bad)}.ll-warnings{display:grid;gap:.3rem;margin:.65rem 0}.ll-warnings div{padding:.45rem .55rem;border:1px solid rgba(255,200,87,.3);border-radius:7px;background:rgba(76,52,11,.18);color:var(--warn);font-size:.72rem}.ll-verify{margin:.6rem 0;padding:.45rem .55rem;border:1px solid rgba(57,167,255,.25);border-radius:7px;color:var(--muted);font-size:.72rem}.ll-ledger{margin-top:1rem;padding-top:.6rem;border-top:1px solid rgba(143,164,184,.14)}.ll-ledger-title{display:flex;justify-content:space-between;gap:1rem;align-items:center}.ll-ledger-title h3{margin:.3rem 0}.ll-ledger-title span{color:var(--muted);font-size:.7rem}@media(max-width:760px){.ll-grid{grid-template-columns:1fr}.ll-head,.ll-ledger-title{display:block}.ll-mode{display:inline-block;margin-top:.4rem}}
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
        // Flight Manual already owns the unavailable state. Lifeline remains
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
