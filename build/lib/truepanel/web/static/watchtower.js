(()=>{
"use strict";

const esc=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const title=value=>String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase());

const HOLD_GUIDANCE=[
  [/auth\.me.*unavailable|temporarily unavailable|unavailable/i,"TrueNAS evidence cannot be read right now.","Check the TrueNAS connection and API credential availability. AEGIS will stay on HOLD until a fresh read succeeds."],
  [/write-capable|unrestricted roles|forbidden role/i,"The AEGIS account has more permission than it should.","Remove write, delete, or unrestricted roles from the AEGIS account, then let the next fresh observation verify least privilege."],
  [/missing required read-only roles/i,"The AEGIS account cannot read all required recovery evidence.","Add only the missing read-only roles shown by the role gate. Do not grant administrator or write access."],
  [/receipt directory is unavailable|receipt root/i,"The restore-proof folder is not safely available.","Restore the governed receipt directory with the expected owner and permissions. Do not weaken its permissions to clear the HOLD."],
  [/owner does not match/i,"The restore-proof folder has the wrong owner.","Correct the receipt directory owner to the runtime account, then re-check AEGIS."],
  [/group- or world-writable/i,"The restore-proof folder can be changed by accounts AEGIS does not trust.","Remove group/world write permission from the receipt directory. AEGIS intentionally refuses unsafe proof storage."],
  [/backup task success is not a tested restore/i,"Backups exist, but recovery has not been proven.","Run the governed restore-verification procedure and preserve its incident-bound verification receipt."],
  [/restore verification receipt is invalid/i,"The saved restore proof does not match the current successful protection task.","Repeat the governed restore test for this incident and create a fresh matching receipt. Do not edit a failed receipt by hand."],
  [/stale cached evidence/i,"The last recovery evidence is too old to clear a HOLD.","Restore TrueNAS connectivity and wait for a fresh live observation. Cached evidence is display-only by design."],
];

function guidance(reason){
  const text=String(reason||"");
  for(const [pattern,headline,action] of HOLD_GUIDANCE){if(pattern.test(text)) return {headline,action};}
  return {headline:"Recovery proof is incomplete.",action:"Open the evidence details, correct the failed gate, and wait for a fresh read. AEGIS will not guess past missing evidence."};
}

function freshness(cache){
  const age=Number(cache?.last_age_seconds);
  const ttl=Number(cache?.ttl_seconds);
  const source=cache?.last_source||"none";
  if(source==="live_read") return {label:"Fresh live evidence",detail:"Read directly from TrueNAS",tone:"ready"};
  if(source==="cache"&&Number.isFinite(age)&&Number.isFinite(ttl)&&age<ttl) return {label:"Fresh cached evidence",detail:`${Math.round(age)}s old · within ${Math.round(ttl)}s freshness window`,tone:"ready"};
  if(source==="stale_cache") return {label:"Stale display-only evidence",detail:Number.isFinite(age)?`${Math.round(age)}s old · cannot clear recovery`:"Cannot clear recovery",tone:"hold"};
  return {label:"Fresh evidence unavailable",detail:"Waiting for a successful TrueNAS read",tone:"hold"};
}

function readiness(evidence){
  const cache=evidence?.cache||{};
  const role=evidence?.role_verification||{};
  const receipt=evidence?.receipt_store||{};
  const fresh=freshness(cache);
  const gates=[
    [role.least_privilege_verified===true,"Read-only access verified"],
    [(Number(evidence?.successful_tasks)||0)>0,"Successful protection task observed"],
    [receipt.governed===true&&receipt.receipt_present===true,"Restore proof safely stored"],
    [evidence?.restore_verified===true,"Tested restore verified"],
    [fresh.tone==="ready","Evidence is fresh"],
    [evidence?.control_authority===false&&receipt.runtime_writes_allowed===false,"Observer cannot change recovery state"],
  ];
  const passed=gates.filter(([ok])=>ok).length;
  const status=evidence?.runtime_status==="READY"&&passed===gates.length?"READY":"HOLD";
  return {status,gates,passed,total:gates.length,fresh};
}

function historyRows(history,evidence){
  const supplied=Array.isArray(history)?history:[];
  if(supplied.length){return supplied.slice(-12).reverse().map(item=>`<li><span>${esc(item?.observed_at||item?.time||"Observation")}</span><strong>${esc(title(item?.runtime_status||item?.status||"observed"))}</strong><small>${esc(item?.summary||item?.reason||"Recovery evidence observed")}</small></li>`).join("");}
  const status=evidence?.runtime_status||"HOLD";
  const reason=status==="READY"?"Current recovery evidence satisfies every required gate.":evidence?.hold_reason||"Recovery evidence is incomplete.";
  return `<li><span>Current snapshot</span><strong>${esc(status)}</strong><small>${esc(reason)}</small></li><li class="wt-muted"><span>History</span><strong>Waiting</strong><small>Flight Recorder is read-only. Earlier observations will appear when the status payload supplies sanitized history.</small></li>`;
}

function render(host,payload){
  const reliability=payload?.reliability||{};
  const evidence=reliability?.passive_evidence||{};
  if(!Object.keys(evidence).length){host.hidden=true;return;}
  host.hidden=false;
  const state=readiness(evidence);
  const guide=guidance(evidence?.hold_reason);
  const backup=evidence?.backup_context||{};
  const tasks=Number(evidence?.successful_tasks)||0;
  const ready=state.status==="READY";
  host.classList.toggle("wt-hold",!ready);
  host.innerHTML=`<div class="wt-head"><div><span class="wt-kicker">Project WATCHTOWER · Recovery Readiness</span><h3>${ready?"Recovery tested and verified":"Recovery needs attention"}</h3><p>${ready?"TruePanel can see successful protection and separate proof that a restore was actually tested.":esc(guide.headline)}</p></div><span class="wt-status ${ready?"ready":"hold"}">${state.status}</span></div>
  <div class="wt-summary">
    <article><small>BACKUP EVIDENCE</small><strong>${tasks>0?`${tasks} successful task${tasks===1?"":"s"}`:"Not proven"}</strong><span>${tasks>0?"TrueNAS reports successful protection activity.":"No successful protection task is visible."}</span></article>
    <article><small>TESTED RESTORE</small><strong>${evidence.restore_verified===true?"Verified":"Not verified"}</strong><span>${evidence.restore_verified===true?"A separate restore test matched the active evidence.":"Backup success alone does not prove recovery."}</span></article>
    <article><small>EVIDENCE FRESHNESS</small><strong>${esc(state.fresh.label)}</strong><span>${esc(state.fresh.detail)}</span></article>
    <article><small>SAFETY BOUNDARY</small><strong>${evidence.control_authority===false?"Read-only":"HOLD"}</strong><span>${evidence.control_authority===false?"AEGIS can observe, but cannot repair or alter storage.":"Expected zero control authority was not proven."}</span></article>
  </div>
  <div class="wt-gates"><div><h4>Why this verdict?</h4>${state.gates.map(([ok,label])=>`<p><span class="${ok?"pass":"fail"}">${ok?"PASS":"HOLD"}</span>${esc(label)}</p>`).join("")}<small>${state.passed}/${state.total} required facts currently proven. This is deliberately not converted into a percentage: missing safety gates are not partial credit.</small></div><div><h4>${ready?"What should I do?":"Safest next action"}</h4><p class="wt-action">${ready?"No recovery action is required. Keep protection jobs healthy and periodically repeat the governed restore test.":esc(guide.action)}</p><small>${backup?.verified_at?`Last restore proof recorded at ${esc(backup.verified_at)}.`:"No trusted restore timestamp is being displayed."}</small></div></div>
  <details class="wt-recorder"><summary>AEGIS Flight Recorder <span>read-only history</span></summary><ol>${historyRows(reliability?.passive_evidence_history,evidence)}</ol><p>Recorder entries intentionally omit credentials, usernames, dataset paths, receipt contents, and other sensitive internals.</p></details>`;
}

function install(){
  const anchor=document.getElementById("aegisReliabilityView");
  if(!anchor){window.setTimeout(install,60);return;}
  if(document.getElementById("watchtowerRecoveryReadiness")) return;
  const style=document.createElement("style");
  style.textContent=`#watchtowerRecoveryReadiness{grid-column:1/-1;margin-top:.8rem;padding:1rem;border:1px solid color-mix(in srgb,var(--good) 35%,transparent);border-radius:10px;background:color-mix(in srgb,var(--panel-solid) 62%,transparent)}#watchtowerRecoveryReadiness.wt-hold{border-color:color-mix(in srgb,var(--warn) 45%,transparent)}.wt-head{display:flex;justify-content:space-between;gap:1rem}.wt-head h3{margin:.2rem 0}.wt-head p{margin:0;color:var(--muted);font-size:.76rem}.wt-kicker{color:var(--good);font-size:.62rem;font-weight:900;letter-spacing:.12em;text-transform:uppercase}.wt-status{align-self:flex-start;padding:.35rem .65rem;border-radius:999px;border:1px solid}.wt-status.ready,.wt-gates .pass{color:var(--good)}.wt-status.hold,.wt-gates .fail{color:var(--warn)}.wt-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem;margin-top:.8rem}.wt-summary article,.wt-gates>div{display:grid;gap:.25rem;padding:.7rem;border:1px solid color-mix(in srgb,var(--edge) 16%,transparent);border-radius:8px}.wt-summary small,.wt-summary span,.wt-gates small,.wt-recorder small,.wt-recorder p{color:var(--muted);font-size:.63rem;line-height:1.4}.wt-summary strong{font-size:.82rem}.wt-gates{display:grid;grid-template-columns:1fr 1fr;gap:.55rem;margin-top:.55rem}.wt-gates h4{margin:0 0 .3rem;font-size:.67rem;text-transform:uppercase;letter-spacing:.08em}.wt-gates p{display:flex;gap:.45rem;margin:.15rem 0;font-size:.7rem}.wt-gates p span{min-width:34px;font-size:.57rem;font-weight:900}.wt-action{display:block!important;line-height:1.5!important}.wt-recorder{margin-top:.55rem;padding:.65rem .75rem;border:1px solid color-mix(in srgb,var(--edge) 16%,transparent);border-radius:8px}.wt-recorder summary{cursor:pointer;font-size:.7rem;font-weight:800}.wt-recorder summary span{float:right;color:var(--muted)}.wt-recorder ol{display:grid;gap:.35rem;padding:0;list-style:none}.wt-recorder li{display:grid;grid-template-columns:130px 65px 1fr;gap:.5rem;font-size:.66rem}.wt-recorder li span,.wt-recorder li small{color:var(--muted)}@media(max-width:760px){#watchtowerRecoveryReadiness{padding:.85rem}.wt-head{display:block}.wt-status{display:inline-block;margin-top:.55rem}.wt-summary,.wt-gates{grid-template-columns:1fr}.wt-recorder summary span{display:block;float:none;margin-top:.2rem}.wt-recorder li{grid-template-columns:1fr}.wt-recorder li strong{margin-top:-.2rem}}`;
  document.head.appendChild(style);
  const host=document.createElement("section");
  host.id="watchtowerRecoveryReadiness";
  host.hidden=true;
  anchor.insertAdjacentElement("afterend",host);
  window.addEventListener("truepanel:status",event=>{if(event?.detail) render(host,event.detail);});
}
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});else install();
})();
