(()=>{
"use strict";

const STATUS_URL="/api/v1/status";
const ACK_URL="/api/v1/lifeline/acknowledge";
const ACK_CONFIRMATION="ACKNOWLEDGE_BACKUP_STATE";
const IDENTIFY_URL="/api/v1/lifeline/identify";
const IDENTIFY_CONFIRMATION="IDENTIFY_FAILED_BAY";
const POLL_MS=5000;

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

function backupAcknowledged(session){
    const context=session&&session.context||{};
    const acknowledgements=context.acknowledgements||{};
    return acknowledgements.backup_state===true;
}

function targetText(session){
    const fault=session.original_fault||{};
    const bits=[];
    if(fault.pool) bits.push(String(fault.pool));
    if(fault.vdev) bits.push(String(fault.vdev));
    if(fault.bay) bits.push(`Bay ${fault.bay}`);
    if(fault.device) bits.push(`/dev/${fault.device}`);
    return bits.join(" · ")||session.id||"Repair session";
}

function canIdentify(payload,session){
    const profile=payload.lifeline&&payload.lifeline.service_profile||{};
    const repair=session&&session.last_session||{};
    return profile.selected_model==="TVS-671"&&repair.can_identify_bay===true;
}

function render(payload){
    const ledger=document.getElementById("lifelineLedger");
    if(!ledger) return;
    const sessions=payload.lifeline&&Array.isArray(payload.lifeline.sessions)
        ?payload.lifeline.sessions.filter(item=>item&&item.status==="active"):[];
    let panel=document.getElementById("lifelineActions");
    if(!sessions.length){
        panel?.remove();
        return;
    }
    if(!panel){
        panel=document.createElement("section");
        panel.id="lifelineActions";
        panel.className="ll-actions";
        ledger.insertBefore(panel,ledger.firstChild?.nextSibling||ledger.firstChild);
    }
    panel.innerHTML=`<h4>Operator checkpoints</h4>${sessions.map(session=>{
        const acknowledged=backupAcknowledged(session);
        const identify=canIdentify(payload,session);
        const bay=session.original_fault&&session.original_fault.bay;
        return `<div class="ll-action-row"><div><strong>${esc(targetText(session))}</strong><span>${acknowledged?"Backup state review acknowledged.":"Before physical service, review whether important data has a current independent backup. This acknowledgement records that the review occurred; it does not claim a backup exists."}</span></div><div class="ll-action-buttons">${identify?`<button type="button" class="ll-identify-bay" data-session-id="${esc(session.id)}">Identify${bay?` Bay ${esc(bay)}`:" failed bay"}</button>`:""}${acknowledged?'<span class="ll-ack-ok">BACKUP REVIEW ACKNOWLEDGED</span>':`<button type="button" class="ll-ack-backup" data-session-id="${esc(session.id)}">Acknowledge backup-state review</button>`}</div></div>`;
    }).join("")}`;
}

async function status(){
    const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
    if(!response.ok) throw new Error(`status ${response.status}`);
    return response.json();
}

async function refresh(){
    try{
        render(await status());
    }catch(_error){
        // The Flight Manual owns telemetry-unavailable messaging.
    }
}

async function acknowledge(button){
    const sessionId=button.dataset.sessionId||"";
    if(!sessionId) return;
    button.disabled=true;
    const original=button.textContent;
    button.textContent="Recording…";
    try{
        const response=await fetch(ACK_URL,{
            method:"POST",
            headers:{
                "Accept":"application/json",
                "Content-Type":"application/json",
                "X-TruePanel-Intent":"lifeline-backup-ack",
            },
            body:JSON.stringify({
                session_id:sessionId,
                acknowledgement:"backup_state",
                value:true,
                confirmation:ACK_CONFIRMATION,
            }),
        });
        if(!response.ok) throw new Error(`ack ${response.status}`);
        await refresh();
    }catch(_error){
        button.disabled=false;
        button.textContent="Acknowledgement failed · retry";
        window.setTimeout(()=>{button.textContent=original;},3000);
    }
}

async function identifyBay(button){
    const sessionId=button.dataset.sessionId||"";
    if(!sessionId) return;
    button.disabled=true;
    const original=button.textContent;
    button.textContent="Identifying…";
    try{
        const response=await fetch(IDENTIFY_URL,{
            method:"POST",
            headers:{
                "Accept":"application/json",
                "Content-Type":"application/json",
                "X-TruePanel-Intent":"lifeline-identify-bay",
            },
            body:JSON.stringify({
                session_id:sessionId,
                confirmation:IDENTIFY_CONFIRMATION,
            }),
        });
        if(!response.ok) throw new Error(`identify ${response.status}`);
        const payload=await response.json();
        const bay=payload.action&&payload.action.bay;
        const seconds=payload.action&&payload.action.duration_seconds;
        button.textContent=`Bay ${bay||"?"} flashing · ${seconds||15}s`;
        window.setTimeout(()=>{
            button.disabled=false;
            button.textContent=original;
        },3000);
    }catch(_error){
        button.disabled=false;
        button.textContent="Identify failed · retry";
        window.setTimeout(()=>{button.textContent=original;},3000);
    }
}

function install(){
    const style=document.createElement("style");
    style.textContent=`
.ll-actions{margin:.75rem 0;padding:.75rem;border:1px solid rgba(57,167,255,.28);border-radius:10px;background:rgba(8,22,38,.28)}.ll-actions h4{margin:0 0 .55rem;color:var(--muted);font-size:.67rem;letter-spacing:.1em;text-transform:uppercase}.ll-action-row{display:flex;justify-content:space-between;gap:1rem;align-items:center;padding:.55rem 0;border-top:1px solid rgba(143,164,184,.1)}.ll-action-row:first-of-type{border-top:0}.ll-action-row strong{display:block;font-size:.76rem}.ll-action-row span{display:block;margin-top:.15rem;color:var(--muted);font-size:.68rem;line-height:1.35}.ll-action-buttons{display:flex;gap:.45rem;align-items:center;justify-content:flex-end;flex-wrap:wrap}.ll-ack-backup,.ll-identify-bay{border:1px solid rgba(57,167,255,.42);border-radius:8px;padding:.48rem .65rem;background:rgba(20,67,100,.28);color:var(--accent);font-size:.68rem;font-weight:850;cursor:pointer}.ll-identify-bay{border-color:rgba(255,200,87,.4);background:rgba(76,52,11,.22);color:var(--warn)}.ll-ack-backup:disabled,.ll-identify-bay:disabled{opacity:.55;cursor:default}.ll-action-row .ll-ack-ok{color:var(--good);font-size:.65rem;font-weight:900}@media(max-width:760px){.ll-action-row{display:block}.ll-action-buttons{justify-content:flex-start;margin-top:.55rem}}
`;
    document.head.appendChild(style);
    document.addEventListener("click",event=>{
        const ack=event.target.closest?.(".ll-ack-backup");
        if(ack){acknowledge(ack);return;}
        const identify=event.target.closest?.(".ll-identify-bay");
        if(identify) identifyBay(identify);
    });
    refresh();
    window.setInterval(refresh,POLL_MS);
}

if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
else install();
})();
