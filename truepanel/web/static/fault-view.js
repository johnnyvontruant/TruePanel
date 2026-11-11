(()=>{
"use strict";

/*
 * Friendly fault view.
 *
 * A plain-language front page for faults: what is wrong, what it affects,
 * what is protecting you, and a guided checklist backed by the TrueNAS and
 * QNAP procedures. Everything is derived from /api/v1/status.
 *
 * Authority boundaries are unchanged. This view:
 *   - never changes storage, fans, LCD or configuration;
 *   - calls only the two existing guarded Lifeline endpoints (backup-state
 *     acknowledgement and bay identify LED), with their existing intent
 *     headers and confirmation phrases, and only when TruePanel already allows
 *     them;
 *   - keeps "you marked this done" ticks in this browser only. A local tick
 *     never clears a Checkride, Lifeline or Pathfinder gate.
 * The engineering panels (System Health, Flight Director, AEGIS / Checkride,
 * Watchtower, the advisory banner) are moved into a Technical details drawer,
 * never deleted: their scripts keep writing to the same elements.
 */

const STATUS_URL="/api/v1/status";
const ACK_URL="/api/v1/lifeline/acknowledge";
const ACK_CONFIRMATION="ACKNOWLEDGE_BACKUP_STATE";
const IDENTIFY_URL="/api/v1/lifeline/identify";
const IDENTIFY_CONFIRMATION="IDENTIFY_FAILED_BAY";
const POLL_MS=5000;
const TICK_PREFIX="truepanel-fault-steps:";
const DRAWER_KEY="truepanel-technical-details-open";
const ADOPT_IDS=["glassCockpitSituation","sentinelFlightDirector","aegisReliabilityView","watchtowerRecoveryReadiness","healthAdvisory"];
const STORAGE_CODES=["storage.disk_faulted","storage.pool_degraded","storage.smart_warning"];

const TRUENAS_REPLACE={
    title:"TrueNAS: Replacing Disks",
    url:"https://www.truenas.com/docs/scale/25.10/scaletutorials/storage/disks/replacingdisks/",
};
const QNAP_MANUAL={
    title:"QNAP TVS-x71 Hardware Manual",
    url:"https://download.qnap.com/TechnicalDocument/QNAP_TVS-x71-QNAP_Turbo_NAS_Hardware_Manual_ENG_20150330.pdf",
};

const APP_NAMES={
    "adguard-home":"AdGuard Home",
    "calibre-web-automated":"Calibre",
    "dashcast":"Dashcast",
    "plex":"Plex",
    "prowlarr":"Prowlarr",
    "qbittorrent":"qBittorrent",
    "radarr":"Radarr",
    "sonarr":"Sonarr",
    "tailscale":"Tailscale",
    "home-assistant":"Home Assistant",
    "jellyfin":"Jellyfin",
    "nextcloud":"Nextcloud",
};
const FOLDER_NAMES={Shows:"TV Shows"};

const esc=value=>String(value??"")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");

const obj=value=>value&&typeof value==="object"&&!Array.isArray(value)?value:{};
const list=value=>Array.isArray(value)?value:[];
const num=value=>{const n=Number(value);return Number.isFinite(n)?n:0;};
const fmt=value=>Math.round(num(value)).toLocaleString("en-US");

function appName(id){
    const key=String(id||"");
    if(APP_NAMES[key]) return APP_NAMES[key];
    return key.replaceAll("-"," ").replace(/\b\w/g,c=>c.toUpperCase());
}

function friendlyModel(model){
    const m=String(model||"").trim();
    if(!m) return "";
    if(/^ST\d+N[ET]/i.test(m)) return "Seagate IronWolf Pro";
    if(/^ST\d+VN/i.test(m)) return "Seagate IronWolf";
    if(/^ST\d+NM/i.test(m)) return "Seagate Exos";
    if(/^WDC?\s?WD\d+EF[RZ]/i.test(m)) return "WD Red";
    if(/^WDC?\s?WD\d+EFPX/i.test(m)) return "WD Red Plus";
    if(/^WDC?\s?WD\d+FF/i.test(m)) return "WD Red Pro";
    return m;
}

function terabytes(bytes){
    const b=num(bytes);
    if(b<=0) return "";
    const tb=b/1e12;
    return tb>=1?`${Math.round(tb)} TB`:`${Math.round(b/1e9)} GB`;
}

function sizeLabel(text){
    return String(text||"").replace(/(\d)T$/,"$1 TB").replace(/(\d)G$/,"$1 GB");
}

function article(text){
    return /^(8|11|18)\b/.test(String(text))?"an":"a";
}

function gigabytes(bytes){
    const gb=num(bytes)/1e9;
    if(gb>=1000) return `${(gb/1000).toFixed(1)} TB`;
    return `${Math.round(gb)} GB`;
}

function scrubSummary(line){
    const text=String(line||"");
    const m=text.match(/scrub repaired .*? with (\d+) errors on \w{3}\s+(\w{3})\s+(\d{1,2})/);
    if(!m) return null;
    return {errors:Number(m[1]),date:`${m[2]} ${m[3]}`};
}

function activeGuidance(payload){
    return list(payload.operator_guidance).filter(card=>card&&obj(card.runtime).active!==false);
}

function checklistFor(payload,code){
    return list(payload.operator_checklists).find(item=>item&&item.code===code&&item.active!==false)||null;
}

function gateState(checklist,key){
    const gate=list(obj(checklist).preflight).find(item=>item&&item.key===key);
    return gate?String(gate.state||""):"";
}

function activeSession(payload){
    const sessions=list(obj(payload.lifeline).sessions).filter(item=>item&&item.status==="active");
    return sessions.find(item=>String(item.kind||"").includes("drive")||String(item.id||"").startsWith("drive:"))||sessions[0]||null;
}

function failedDrive(payload){
    const storage=obj(payload.storage);
    const session=activeSession(payload);
    const fault=obj(session&&session.original_fault);
    const context=obj(session&&session.context);
    const historical=obj(context.physical_identity||context.historical_media);
    const incident=obj(obj(payload.reliability).active_incident);
    const signal=obj(list(incident.supporting_signals)[0]);
    const evidence=obj(signal.evidence);
    const devices=list(storage.devices);
    const unhealthy=devices.find(d=>d&&["FAULTED","REMOVED","UNAVAIL","OFFLINE","DEGRADED"].includes(String(d.zfs_state||"").toUpperCase()));
    const mirrorBay=list(obj(storage.bay_mirror).bays).find(b=>b&&["fault","faulted","removed","missing"].includes(String(b.state||"").toLowerCase()));
    const bay=fault.bay??historical.bay??evidence.bay??obj(unhealthy).physical_bay??obj(mirrorBay).bay??null;
    const device=fault.device||evidence.device||obj(unhealthy).device||null;
    const smart=list(storage.smart).find(s=>s&&device&&s.drive===device)||{};
    const pool=fault.pool||evidence.pool||obj(unhealthy).pool||obj(mirrorBay).pool||"";
    return {
        bay,
        device,
        pool,
        model:fault.model||historical.model||evidence.model||obj(unhealthy).model||"",
        serial:fault.serial_last4||historical.serial_last4||evidence.serial_last4||obj(unhealthy).serial_last4||"",
        capacity:fault.capacity_bytes||historical.capacity_bytes||evidence.capacity_bytes||obj(unhealthy).capacity_bytes||0,
        present:obj(unhealthy).present!==false&&evidence.present!==false,
        zfsState:String(obj(unhealthy).zfs_state||evidence.zfs_state||"").toUpperCase(),
        readErrors:num(obj(unhealthy).read_errors??evidence.read_errors),
        checksumErrors:num(obj(unhealthy).checksum_errors??evidence.checksum_errors),
        redundancy:obj(unhealthy).remaining_redundancy??evidence.remaining_redundancy??fault.remaining_redundancy??null,
        reallocated:num(smart.reallocated),
        pending:num(smart.pending),
        uncorrectable:num(smart.offline_uncorrectable||smart.reported_uncorrect),
        sessionId:session&&session.id||"",
        backupAcknowledged:obj(context.acknowledgements).backup_state===true,
        canIdentify:obj(obj(payload.lifeline).service_profile).selected_model==="TVS-671"&&obj(session&&session.last_session).can_identify_bay===true,
        member:obj(unhealthy).member_id||evidence.member_id||fault.member_id||"",
    };
}

function poolInfo(payload,name){
    const pool=list(obj(payload.storage).pools).find(p=>p&&p.name===name)||{};
    const used=parseInt(String(pool.capacity||"").replace("%",""),10);
    return {name,size:pool.size||"",free:pool.free||"",percentUsed:Number.isFinite(used)?used:null,health:String(pool.health||"").toUpperCase()};
}

function poolContents(payload,poolName){
    const topology=obj(payload.sentinel_topology);
    const folders=[];
    for(const ds of list(topology.datasets)){
        const name=String(obj(ds).name||obj(ds).id||"");
        const parts=name.split("/");
        if(parts[0]!==poolName||parts.length!==2) continue;
        const folder=parts[1];
        if(/^(Applications|Plex|Media|truepanel-|\.)/.test(folder)) continue;
        folders.push(FOLDER_NAMES[folder]||folder);
    }
    const onPool=new Set();
    const onOther=new Set();
    for(const rel of list(topology.relationships)){
        const ds=String(obj(rel).dataset_id||"");
        if(ds.split("/")[0]===poolName) onPool.add(rel.application_id);
        else onOther.add(rel.application_id);
    }
    const apps=list(topology.applications);
    const running=id=>String(obj(apps.find(a=>a&&(a.id===id||a.name===id))).state||"").toUpperCase()==="RUNNING";
    const affected=[...onPool].filter(Boolean).map(id=>({name:appName(id),running:running(id)}));
    const unaffected=apps.map(a=>a&&(a.id||a.name)).filter(id=>id&&!onPool.has(id)).map(appName);
    return {
        folders:[...new Set(folders)],
        affected,
        unaffected,
        settingsElsewhere:[...onPool].some(id=>onOther.has(id)),
    };
}

function healthyPeers(payload,failed){
    const storage=obj(payload.storage);
    const peers=list(storage.devices).filter(d=>d&&d.pool===failed.pool&&String(d.zfs_state||"").toUpperCase()==="ONLINE");
    const clean=peers.filter(d=>!num(d.read_errors)&&!num(d.write_errors)&&!num(d.checksum_errors));
    const temps=list(storage.temperatures)
        .filter(t=>t&&peers.some(p=>p.device===t.drive))
        .map(t=>num(t.temp))
        .filter(t=>t>0);
    const range=temps.length?(Math.min(...temps)===Math.max(...temps)?`${Math.min(...temps)} °C`:`${Math.min(...temps)}–${Math.max(...temps)} °C`):"";
    return {count:peers.length,clean:clean.length===peers.length,range};
}

function backupStatus(payload){
    const backup=obj(obj(payload.cargo_bay).backup);
    const waiting=list(backup.items).filter(item=>item&&item.state==="AWAITING");
    const bytes=waiting.reduce((sum,item)=>sum+num(item.size_bytes),0);
    const drives=new Set();
    for(const item of waiting){
        const parts=String(item.current_path||"").split("/");
        if(parts.length>4) drives.add(parts[4]);
    }
    return {waiting:waiting.length,bytes,drives:[...drives]};
}

function loadTicks(incident){
    try{
        return JSON.parse(window.localStorage.getItem(TICK_PREFIX+incident)||"{}")||{};
    }catch(_error){
        return {};
    }
}

function saveTicks(incident,ticks){
    try{
        window.localStorage.setItem(TICK_PREFIX+incident,JSON.stringify(ticks));
    }catch(_error){
        // Ticks are a convenience; losing them changes nothing on the NAS.
    }
}

function driveSteps(payload,failed,checklist,ticks){
    const storage=obj(payload.storage);
    const activity=obj(storage.zfs_activity);
    const pool=poolInfo(payload,failed.pool);
    const backup=backupStatus(payload);
    const bay=failed.bay??"?";
    const sizeText=terabytes(failed.capacity)||"same size";
    const modelText=[friendlyModel(failed.model),terabytes(failed.capacity)].filter(Boolean).join(" ");
    const replacementInBay=list(storage.devices).find(d=>d&&d.physical_bay===failed.bay&&d.present!==false&&d.serial_last4&&d.serial_last4!==failed.serial);
    const resilvering=activity.resilver_running===true;
    const percent=activity.percent;
    const poolOnline=pool.health==="ONLINE";
    const machine={
        backup:failed.backupAcknowledged,
        replacement:gateState(checklist,"replacement_candidate")==="verified"||!!replacementInBay,
        bay:gateState(checklist,"physical_identity")==="verified",
        offline:["OFFLINE","REMOVED"].includes(failed.zfsState)||!!replacementInBay||resilvering||poolOnline,
        swapped:!!replacementInBay||resilvering||poolOnline,
        replaced:resilvering||poolOnline,
        rebuilt:poolOnline,
    };
    const backupBody=backup.waiting
        ?`Load Master has ${backup.waiting} new item${backup.waiting===1?"":"s"} (${gigabytes(backup.bytes)}) that ${backup.waiting===1?"isn't":"aren't"} on a USB drive yet${backup.drives.length?`. Plug in ${backup.drives.join(" and ")} and press Copy on the front of the NAS`:""}. Then confirm here.`
        :"Your Load Master USB copies are up to date. Confirm here once you've checked any other backups you rely on.";
    const steps=[
        {key:"hands_off",when:"Now",title:"Leave every other drive where it is",
            body:failed.redundancy===0
                ?`With one drive down, your ${failed.pool||"storage"} pool can't lose another. Don't pull or swap any drive except Bay ${bay}, and only when you reach step 6.`
                :`Don't pull or swap any drive except Bay ${bay}, and only when you reach step 6.`,
            source:TRUENAS_REPLACE},
        {key:"backup",when:"Before you start",title:"Make sure your backup is current",body:backupBody,
            action:failed.sessionId&&!machine.backup?{kind:"ack",label:"I've checked my backup"}:null,
            machine:machine.backup,noManualTick:true,source:{title:"Load Master",url:"#loadmaster"}},
        {key:"replacement",when:"Before you start",title:"Get a replacement drive",
            body:`Buy ${article(sizeText)} ${sizeText} or larger NAS drive${modelText?`. The simplest choice is another ${modelText}`:""}. It must be new, or wiped. TruePanel checks its size when you plug it in.`,
            machine:machine.replacement,source:TRUENAS_REPLACE},
        {key:"bay",when:"When the drive arrives",title:`Find Bay ${bay} on the NAS`,
            body:failed.canIdentify
                ?`Press the button below and Bay ${bay}'s light will blink so you can't pull the wrong drive.`
                :`Bay ${bay} is highlighted under "Your drives" above. The blink-the-light button unlocks once TruePanel has confirmed this NAS model and the bay (see Technical details).`,
            action:failed.canIdentify?{kind:"identify",label:`Blink Bay ${bay}`}:null,
            machine:machine.bay,source:{...QNAP_MANUAL,title:"QNAP manual, ch. 4 (lights)"}},
        {key:"offline",when:"In TrueNAS",title:"Take the old drive offline",
            body:`In TrueNAS: Storage, then View VDEVs on the ${failed.pool||"affected"} pool. Open the disk in Bay ${bay}${failed.serial?` (serial ending ${failed.serial})`:""} and click Offline. Its status changes to OFFLINE.`,
            warn:"If TrueNAS says \"no valid replicas\", run a scrub from the ZFS Health widget first, then try Offline again.",
            machine:machine.offline,source:{...TRUENAS_REPLACE,title:"TrueNAS: Replacing Disks, steps 1–2"}},
        {key:"swap",when:"At the NAS",title:"Turn off the NAS and swap the drive",
            body:`Shut down from TrueNAS (the power icon, then Shut Down) and wait for the lights to go out. Slide out the Bay ${bay} tray, fit the new drive with the flat-head screws, slide it back in, and power on.`,
            warn:`QNAP strongly recommends turning the NAS off before replacing a drive. Only open Bay ${bay}.`,
            machine:machine.swapped,source:{...QNAP_MANUAL,title:"QNAP manual, ch. 8 (p. 30)"}},
        {key:"replace",when:"In TrueNAS",title:"Tell TrueNAS to use the new drive",
            body:"Back on the VDEVs screen, open the offline disk and click Replace. Pick the new drive from the Member Disk list and click Replace Disk.",
            warn:"Leave \"Force\" unticked. Force erases whatever disk you pick. You only need it if the new drive was used before, and you're sure it's the right one.",
            machine:machine.replaced,source:{...TRUENAS_REPLACE,title:"TrueNAS: Replacing Disks, steps 5–7"}},
        {key:"rebuild",when:"Hands off",title:"Let it rebuild",
            body:resilvering
                ?`Rebuilding now${percent!=null?`: ${percent}% done`:""}${activity.remaining?`, ${activity.remaining}`:""}. You can keep using your apps. Don't remove any drive until this finishes.`
                :`TrueNAS copies your data onto the new drive (called resilvering). TruePanel shows the progress here. With ${pool.size?sizeLabel(pool.size):"a large pool"} of storage this can take many hours. It's done when the pool reads Online and this page turns green.`,
            machine:machine.rebuilt,noManualTick:true,source:{...TRUENAS_REPLACE,title:"TrueNAS: Replacing Disks, steps 8–9"}},
    ];
    // Once TruePanel confirms a later step, everything before it has
    // necessarily happened; show those as passed rather than still open.
    let lastConfirmed=-1;
    steps.forEach((step,index)=>{ if(step.machine) lastConfirmed=index; });
    return steps.map((step,index)=>({
        ...step,
        n:index+1,
        done:!!step.machine||index<lastConfirmed||(!step.noManualTick&&ticks[step.key]===true),
        confirmed:!!step.machine,
    }));
}

function genericSteps(card,ticks){
    const sections=[["Now",card.immediate_actions],["Check",card.diagnosis],["Fix",card.remediation],["Confirm",card.verification]];
    const firstSource=list(card.sources)[0]||null;
    const steps=[];
    for(const [when,items] of sections){
        for(const item of list(items)){
            if(!item) continue;
            const key=`${when}:${item.title}`;
            steps.push({
                key,
                when,
                title:String(item.title||""),
                body:String(item.detail||""),
                warn:item.destructive?"This step can erase data. Read it twice before you do it.":"",
                source:firstSource?{title:firstSource.title,url:firstSource.url}:null,
                done:ticks[key]===true,
                confirmed:false,
            });
        }
    }
    return steps.map((step,index)=>({...step,n:index+1}));
}

function buildModel(payload){
    payload=obj(payload);
    const health=obj(payload.health);
    const state=String(health.state||"UNKNOWN").toUpperCase();
    const guidance=activeGuidance(payload);
    const storageCards=guidance.filter(card=>STORAGE_CODES.includes(card.code));
    const incident=obj(obj(payload.reliability).active_incident);
    const incidentId=String(incident.incident_id||(guidance[0]&&guidance[0].code)||"none");
    const ticks=loadTicks(incidentId);

    if(!guidance.length){
        if(state==="UNKNOWN"&&!payload.timestamp) return {kind:"waiting"};
        return allClear(payload,state);
    }

    if(storageCards.length){
        const codes=storageCards.map(card=>card.code);
        const failed=failedDrive(payload);
        const pool=poolInfo(payload,failed.pool);
        const contents=poolContents(payload,failed.pool);
        const peers=healthyPeers(payload,failed);
        const backup=backupStatus(payload);
        const scrub=scrubSummary(obj(obj(payload.storage).zfs_activity).status_line);
        const checklist=checklistFor(payload,"storage.disk_faulted")||checklistFor(payload,codes[0]);
        const steps=driveSteps(payload,failed,checklist,ticks);
        const faulted=codes.includes("storage.disk_faulted");
        const bayText=failed.bay!=null?`Bay ${failed.bay}`:"one bay";
        const activity=obj(obj(payload.storage).zfs_activity);
        const rebuilding=activity.resilver_running===true;
        const headline=rebuilding
            ?`Your new ${bayText} drive is being set up`
            :faulted
            ?`The hard drive in ${bayText} has failed`
            :codes.includes("storage.pool_degraded")
                ?`Your ${failed.pool||"storage"} pool is running without its safety net`
                :`The hard drive in ${bayText} is starting to wear out`;
        const sub=rebuilding
            ?`TrueNAS is copying your data onto it${activity.percent!=null?` (${activity.percent}% done${activity.remaining?`, ${activity.remaining}`:""})`:""}. Keep every drive in place until it finishes.`
            :failed.redundancy===0
            ?"Your files are all still there and working. But your storage has no safety net left, so plan to replace this drive soon."
            :"Your files are all still there and working. Plan to replace this drive while you still have protection.";
        const wrong=[];
        if(failed.reallocated||failed.pending){
            wrong.push(`The drive is wearing out. It has already swapped out ${fmt(failed.reallocated)} damaged spot${failed.reallocated===1?"":"s"}${failed.pending?` and has ${fmt(failed.pending)} more it can't read`:""}${faulted?", so your storage stopped using it":""}.`);
        }else if(failed.readErrors||failed.checksumErrors){
            wrong.push(`The drive returned ${fmt(failed.readErrors)} read error${failed.readErrors===1?"":"s"} and ${fmt(failed.checksumErrors)} damaged block${failed.checksumErrors===1?"":"s"}${faulted?", so your storage stopped using it":""}.`);
        }else{
            wrong.push(String(storageCards[0].summary||"TrueNAS reported a problem with this drive."));
        }
        if(!failed.present) wrong.push("It's no longer responding. That's expected for a drive this far gone.");
        const protecting=[];
        if(peers.count) protecting.push({ok:peers.clean,text:`The other ${peers.count} drive${peers.count===1?" is":"s are"} ${peers.clean?"healthy":"online"}${peers.clean?": no errors":""}${peers.range?`, ${peers.range}`:""}.`});
        if(scrub) protecting.push({ok:scrub.errors===0,text:scrub.errors===0?`Last full health check (${scrub.date}) found no damaged files.`:`Last full health check (${scrub.date}) found ${scrub.errors} problem${scrub.errors===1?"":"s"}.`});
        protecting.push({ok:true,text:backup.waiting?`Load Master keeps copies on your USB drives. ${backup.waiting} new item${backup.waiting===1?"":"s"} (${gigabytes(backup.bytes)}) ${backup.waiting===1?"is":"are"} waiting to be copied.`:"Load Master's USB copies are up to date."});
        const avoid=failed.redundancy===0
            ?`Don't remove any other drive. If a second drive fails before this one is replaced, the ${failed.pool||"affected"} storage would be lost.`
            :"Don't remove more than one drive at a time.";
        const bays=list(obj(obj(payload.storage).bay_mirror).bays).map(b=>{
            const dev=list(obj(payload.storage).devices).find(d=>d&&d.physical_bay===b.bay)||{};
            const temp=list(obj(payload.storage).temperatures).find(t=>t&&t.bay===b.bay);
            const bad=b.bay===failed.bay||["fault","faulted","removed","missing"].includes(String(b.state||"").toLowerCase());
            const size=terabytes(dev.capacity_bytes);
            return {
                n:b.bay,
                bad,
                label:bad?"Failed":b.installed===false?"Empty":"Healthy",
                note:bad?"Replace this one":[size,temp?`${temp.temp} °C`:""].filter(Boolean).join(" · "),
            };
        });
        const reliability=obj(payload.reliability);
        return {
            kind:"fault",
            incidentId,
            tone:rebuilding?"warn":faulted?"bad":"warn",
            headline,
            sub,
            identity:{
                title:[bayText,[friendlyModel(failed.model),terabytes(failed.capacity)].filter(Boolean).join(" ")].filter(Boolean).join(" · "),
                serial:failed.serial,
            },
            wrong,
            affects:{pool:failed.pool,size:pool.size,folders:contents.folders,affected:contents.affected,unaffected:contents.unaffected,settingsElsewhere:contents.settingsElsewhere},
            protecting,
            avoid,
            bays,
            poolNote:pool.percentUsed!=null?`${failed.pool} storage is ${pool.percentUsed}% full${pool.free?` · ${sizeLabel(pool.free)} free`:""}`:"",
            poolFull:pool.percentUsed!=null&&pool.percentUsed>=85,
            manualTitle:`How to replace the ${bayText} drive`,
            steps,
            sessionId:failed.sessionId,
            technical:technicalSummary(reliability,checklist,failed),
        };
    }

    const card=guidance[0];
    const steps=genericSteps(card,ticks);
    return {
        kind:"fault",
        incidentId,
        tone:card.severity==="critical"?"bad":"warn",
        headline:String(card.title||"Something needs attention"),
        sub:String(card.summary||health.reason||""),
        identity:null,
        wrong:[String(card.summary||"")].filter(Boolean),
        affects:null,
        protecting:otherSubsystems(health),
        avoid:String(card.escalation||""),
        bays:[],
        poolNote:"",
        poolFull:false,
        manualTitle:"How to fix it",
        steps,
        sessionId:"",
        technical:technicalSummary(obj(payload.reliability),checklistFor(payload,card.code),null),
    };
}

function otherSubsystems(health){
    const subsystems=obj(health.subsystems);
    return Object.entries(subsystems)
        .filter(([,value])=>String(obj(value).state||"").toUpperCase()==="NOMINAL")
        .map(([,value])=>({ok:true,text:String(obj(value).summary||"")}));
}

function technicalSummary(reliability,checklist,failed){
    const incident=obj(reliability.active_incident);
    const gates=list(obj(checklist).preflight);
    const cleared=gates.filter(g=>g&&g.state==="verified").length;
    const next=gates.find(g=>g&&g.state!=="verified");
    const rehearsals=list(obj(reliability.flight_director).rehearsals);
    const rows=[];
    if(incident.likely_cause) rows.push({title:"AEGIS diagnosis",text:`${incident.likely_cause} · ${Math.round(num(incident.confidence)*100)}% confidence from ${list(obj(incident.confidence_basis).hard_alerts).length||"several"} signals`});
    if(gates.length) rows.push({title:"Checkride safety gates",text:`${cleared} of ${gates.length} cleared${next?` · next: ${String(next.title||"").toLowerCase()}`:""}`});
    if(failed&&(failed.member||failed.reallocated)) rows.push({title:"Raw drive readings",text:`${failed.member||"member"} ${failed.zfsState||""} · ${fmt(failed.reallocated)} reallocated · ${fmt(failed.pending)} pending · ${fmt(failed.uncorrectable)} uncorrectable · ${fmt(failed.readErrors)} ZFS read errors · ${fmt(failed.checksumErrors)} checksum errors`});
    if(rehearsals.length) rows.push({title:"HoloDeck rehearsals",text:`${rehearsals.length} practice scenarios on record`});
    return rows;
}

function allClear(payload,state){
    const storage=obj(payload.storage);
    const devices=list(storage.devices);
    const online=devices.filter(d=>d&&String(d.zfs_state||"").toUpperCase()==="ONLINE").length;
    const health=obj(payload.health);
    const subsystems=obj(health.subsystems);
    const cooling=String(obj(subsystems.cooling).state||"").toUpperCase();
    const apps=list(obj(payload.sentinel_topology).applications);
    const running=apps.filter(a=>a&&String(a.state||"").toUpperCase()==="RUNNING").length;
    const backup=backupStatus(payload);
    const fullest=list(storage.pools)
        .map(p=>({name:p&&p.name,used:parseInt(String(p&&p.capacity||"").replace("%",""),10)}))
        .filter(p=>p.name&&p.name!=="boot-pool"&&Number.isFinite(p.used))
        .sort((a,b)=>b.used-a.used)[0]||null;
    const tiles=[];
    if(devices.length) tiles.push({label:"Drives",value:`${online} of ${devices.length} healthy`,ok:online===devices.length});
    if(cooling) tiles.push({label:"Cooling",value:cooling==="NOMINAL"?"Normal":"Check",ok:cooling==="NOMINAL"});
    tiles.push({label:"USB backups",value:backup.waiting?`${backup.waiting} waiting`:"Up to date",ok:!backup.waiting});
    if(apps.length) tiles.push({label:"Apps",value:`${running} running`,ok:running===apps.length});
    const nominal=state==="NOMINAL";
    return {
        kind:"clear",
        tone:nominal?"good":"warn",
        headline:nominal?"Everything's working":String(health.summary||"Check your NAS"),
        sub:nominal?"All drives are healthy and your storage has its safety net.":String(health.reason||""),
        tiles,
        poolNote:fullest&&fullest.used>=85?`${fullest.name} storage is ${fullest.used}% full`:"",
    };
}

/* ---------------------------------------------------------------- render */

const ICON={
    alert:'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    check:'<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    wrong:'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    disk:'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
    shield:'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg>',
};

const ui={open:null,current:null,lastSignature:"",model:null,busy:"",error:""};

function safeUrl(value){
    const text=String(value||"");
    if(text.startsWith("#")) return text;
    try{
        const url=new URL(text,window.location.href);
        return ["http:","https:"].includes(url.protocol)?url.href:"";
    }catch(_error){
        return "";
    }
}

function renderHero(model){
    const doneCount=(model.steps||[]).filter(s=>s.done).length;
    const total=(model.steps||[]).length;
    const label=model.kind==="clear"?(model.tone==="good"?"All clear":"Heads up"):"Action needed";
    return `<section class="ff-hero ff-${esc(model.tone)}" aria-label="Status">
        <div class="ff-hero-main">
            <div class="ff-hero-icon">${model.kind==="clear"&&model.tone==="good"?ICON.check:ICON.alert}</div>
            <div class="ff-hero-text">
                <span class="ff-kicker">${esc(label)}</span>
                <h2>${esc(model.headline)}</h2>
                ${model.sub?`<p>${esc(model.sub)}</p>`:""}
            </div>
        </div>
        ${model.kind==="fault"&&total?`<div class="ff-hero-cta">
            <a class="ff-primary" href="#ffManual">Show me how to fix it</a>
            <span>${doneCount?`${doneCount} of ${total} steps done`:`${total} steps · most of it is waiting`}</span>
        </div>`:""}
    </section>`;
}

function renderCards(model){
    const affects=model.affects;
    const wrongCard=`<article class="ff-card"><h3 class="ff-card-title ff-bad-text">${ICON.wrong}<span>What's wrong</span></h3>
        ${model.identity?`<div class="ff-identity"><strong>${esc(model.identity.title)}</strong>${model.identity.serial?`<span>Serial ending ${esc(model.identity.serial)}</span>`:""}</div>`:""}
        ${model.wrong.map(text=>`<p>${esc(text)}</p>`).join("")}
    </article>`;
    const affectsCard=affects?`<article class="ff-card"><h3 class="ff-card-title ff-warn-text">${ICON.disk}<span>What it affects</span></h3>
        <p>Your <strong>${esc(affects.pool)}</strong> storage${affects.size?` (${esc(sizeLabel(affects.size))})`:""}${affects.folders.length?", which holds:":"."}</p>
        ${affects.folders.length?`<div class="ff-chips">${affects.folders.map(f=>`<span>${esc(f)}</span>`).join("")}</div>`:""}
        ${affects.affected.length?`<div class="ff-line"><span class="ff-good-text">${affects.affected.every(a=>a.running)?"Still working":"Uses this storage"}</span><span>${esc(affects.affected.map(a=>a.name).join(", "))}</span></div>`:""}
        ${affects.unaffected.length?`<div class="ff-line"><span class="ff-muted">Not affected</span><span>${esc(affects.unaffected.join(", "))}${affects.settingsElsewhere?", and your app settings (they're stored on other drives)":""}</span></div>`:""}
    </article>`:"";
    const protectCard=`<article class="ff-card"><h3 class="ff-card-title ff-good-text">${ICON.shield}<span>What's protecting you</span></h3>
        <ul class="ff-checks">${model.protecting.map(p=>`<li><span class="${p.ok?"ff-good-text":"ff-warn-text"}" aria-hidden="true">${p.ok?"✓":"!"}</span><span>${esc(p.text)}</span></li>`).join("")}</ul>
        ${model.avoid?`<div class="ff-avoid"><strong>The one thing to avoid</strong><span>${esc(model.avoid)}</span></div>`:""}
    </article>`;
    return `<div class="ff-cards${affects?"":" ff-cards-2"}">${wrongCard}${affectsCard}${protectCard}</div>`;
}

function renderBays(model){
    if(!model.bays.length) return "";
    return `<section class="ff-card ff-bays" aria-label="Your drives">
        <div class="ff-row"><h3>Your drives</h3>${model.poolNote?`<span class="${model.poolFull?"ff-warn-text":"ff-muted"}">${esc(model.poolNote)}</span>`:""}</div>
        <div class="ff-bay-grid">${model.bays.map(b=>`<div class="ff-bay${b.bad?" ff-bay-bad":""}"><span class="ff-muted">Bay ${esc(b.n)}</span><strong>${esc(b.label)}</strong><span class="${b.bad?"ff-bad-text":"ff-muted"}">${esc(b.note)}</span></div>`).join("")}</div>
    </section>`;
}

function renderSteps(model){
    const steps=model.steps||[];
    if(!steps.length) return "";
    const doneCount=steps.filter(s=>s.done).length;
    const current=steps.find(s=>!s.done);
    ui.current=current?current.key:null;
    const openKey=ui.open===null?ui.current:ui.open;
    return `<section id="ffManual" class="ff-card ff-manual" aria-label="${esc(model.manualTitle)}">
        <div class="ff-row ff-manual-head">
            <div><span class="ff-kicker ff-accent-text">Flight manual</span><h3>${esc(model.manualTitle)}</h3><p class="ff-muted">Steps from the TrueNAS and QNAP guides, in order. TruePanel ticks off what it can see for itself.</p></div>
            <div class="ff-progress"><strong>${doneCount} of ${steps.length} done</strong><div class="ff-bar"><div style="width:${Math.round(doneCount/steps.length*100)}%"></div></div></div>
        </div>
        <ol class="ff-steps">${steps.map(step=>{
            const open=step.key===openKey;
            const url=step.source?safeUrl(step.source.url):"";
            const tickLabel=step.confirmed?"TruePanel confirmed this step":step.done?`Unmark step ${step.n}`:`Mark step ${step.n} done`;
            const tickDisabled=step.confirmed||(step.noManualTick&&!step.done);
            return `<li class="ff-step${open?" ff-open":""}${step.done?" ff-done":""}">
                <div class="ff-step-head">
                    <button type="button" class="ff-tick" data-ff-tick="${esc(step.key)}" aria-label="${esc(tickLabel)}" aria-pressed="${step.done?"true":"false"}"${tickDisabled?" disabled":""}>${step.done?"✓":""}</button>
                    <button type="button" class="ff-step-toggle" data-ff-open="${esc(step.key)}" aria-expanded="${open?"true":"false"}">
                        <span><span class="ff-muted ff-small">Step ${esc(step.n)} · ${esc(step.when)}${step.confirmed?" · confirmed by TruePanel":""}</span><span class="ff-step-title">${esc(step.title)}</span></span>
                        <span class="ff-muted" aria-hidden="true">${open?"−":"+"}</span>
                    </button>
                </div>
                ${open?`<div class="ff-step-body">
                    <p>${esc(step.body)}</p>
                    ${step.warn?`<div class="ff-warn-box">${esc(step.warn)}</div>`:""}
                    ${step.action&&ui.error?`<div class="ff-warn-box" role="alert">${esc(ui.error)}</div>`:""}
                    <div class="ff-actions">
                        ${step.action&&!step.done?`<button type="button" class="ff-primary" data-ff-action="${esc(step.action.kind)}"${ui.busy?" disabled":""}>${esc(ui.busy===step.action.kind?"Working…":step.action.label)}</button>`:""}
                        ${url?`<a href="${esc(url)}"${url.startsWith("#")?"":' target="_blank" rel="noopener noreferrer"'}>${esc(step.source.title)} ↗</a>`:""}
                    </div>
                </div>`:""}
            </li>`;
        }).join("")}</ol>
    </section>`;
}

function renderClear(model){
    return `<div class="ff-tiles">${model.tiles.map(t=>`<div class="ff-card ff-tile"><span class="ff-muted">${esc(t.label)}</span><strong class="${t.ok?"ff-good-text":"ff-warn-text"}">${esc(t.value)}</strong></div>`).join("")}</div>
        ${model.poolNote?`<div class="ff-card ff-note"><strong class="ff-warn-text">Worth knowing: ${esc(model.poolNote)}</strong><span>Storage pools slow down as they fill up. Plan for more space when you can.</span></div>`:""}`;
}

function renderTechnical(model){
    const rows=model.technical||[];
    return rows.length?`<div class="ff-tech-grid">${rows.map(r=>`<div><strong>${esc(r.title)}</strong><span>${esc(r.text)}</span></div>`).join("")}</div>`:"";
}

function render(view,drawer,payload){
    const model=buildModel(payload);
    ui.model=model;
    const signature=JSON.stringify([model,ui.open,ui.busy,ui.error]);
    if(signature===ui.lastSignature) return;
    ui.lastSignature=signature;
    if(model.kind==="waiting"){
        view.innerHTML='<section class="ff-hero ff-warn"><div class="ff-hero-main"><div class="ff-hero-text"><span class="ff-kicker">Checking</span><h2>Checking your NAS…</h2></div></div></section>';
        return;
    }
    view.innerHTML=model.kind==="clear"
        ?renderHero(model)+renderClear(model)
        :renderHero(model)+renderCards(model)+renderBays(model)+renderSteps(model);
    const summary=drawer.querySelector(".ff-tech-summary");
    if(summary) summary.innerHTML=renderTechnical(model);
}

/* --------------------------------------------------------------- actions */

async function post(url,intent,body){
    const response=await fetch(url,{
        method:"POST",
        headers:{"Accept":"application/json","Content-Type":"application/json","X-TruePanel-Intent":intent},
        body:JSON.stringify(body),
    });
    if(!response.ok) throw new Error(`${intent} ${response.status}`);
    return response.json();
}

async function runAction(kind,refresh){
    const model=ui.model;
    if(!model||!model.sessionId||ui.busy) return;
    ui.busy=kind;
    ui.error="";
    refresh(true);
    try{
        if(kind==="ack"){
            await post(ACK_URL,"lifeline-backup-ack",{session_id:model.sessionId,acknowledgement:"backup_state",value:true,confirmation:ACK_CONFIRMATION});
        }else if(kind==="identify"){
            await post(IDENTIFY_URL,"lifeline-identify-bay",{session_id:model.sessionId,confirmation:IDENTIFY_CONFIRMATION});
        }
    }catch(_error){
        ui.error=kind==="identify"
            ?"TruePanel couldn't blink the light just now. Nothing was changed. Try again in a moment."
            :"TruePanel couldn't save that just now. Nothing was changed. Try again in a moment.";
        window.setTimeout(()=>{ui.error="";refresh(true);},8000);
    }finally{
        ui.busy="";
        refresh();
    }
}

/* --------------------------------------------------------------- install */

function adopt(drawerBody){
    const health=document.querySelector(".health-command");
    const items=[health,...ADOPT_IDS.map(id=>document.getElementById(id))].filter(Boolean);
    const inOrder=items.every((el,index)=>drawerBody.children[index]===el);
    if(inOrder) return;
    // Keep a stable reading order however late each companion panel installs.
    for(const el of items) drawerBody.append(el);
}

const STYLE=`
#friendlyFaultView{grid-column:1/-1;display:flex;flex-direction:column;gap:1rem}
#friendlyFaultView h2,#friendlyFaultView h3,#friendlyFaultView p{margin:0}
.ff-hero{display:flex;flex-wrap:wrap;gap:1.25rem;align-items:center;justify-content:space-between;padding:1.75rem;border-radius:24px;border:1px solid var(--edge-strong);background:var(--panel);backdrop-filter:var(--blur)}
.ff-hero.ff-bad{border-color:color-mix(in srgb,var(--bad) 45%,transparent);background:linear-gradient(135deg,var(--bad-soft),var(--panel) 60%)}
.ff-hero.ff-warn{border-color:color-mix(in srgb,var(--warn) 45%,transparent);background:linear-gradient(135deg,var(--warn-soft),var(--panel) 60%)}
.ff-hero.ff-good{border-color:color-mix(in srgb,var(--good) 45%,transparent);background:linear-gradient(135deg,var(--good-soft),var(--panel) 60%)}
.ff-hero-main{display:flex;gap:1.1rem;align-items:flex-start;flex:1 1 30rem;min-width:0}
.ff-hero-icon{flex:0 0 auto;width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;color:#fff;background:var(--muted)}
.ff-bad .ff-hero-icon{background:var(--bad)}.ff-warn .ff-hero-icon{background:var(--warn)}.ff-good .ff-hero-icon{background:var(--good)}
.ff-hero-text{display:flex;flex-direction:column;gap:.45rem;min-width:0}
.ff-hero-text h2{font-size:clamp(1.5rem,3vw,2.1rem);line-height:1.15;font-weight:700}
.ff-hero-text p{font-size:1.05rem;line-height:1.5;color:var(--text);opacity:.85;max-width:42rem}
.ff-kicker{font-size:.8rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.ff-bad .ff-kicker{color:var(--bad)}.ff-warn .ff-kicker{color:var(--warn)}.ff-good .ff-kicker{color:var(--good)}
.ff-hero-cta{display:flex;flex-direction:column;gap:.5rem;align-items:center}
.ff-hero-cta span{font-size:.85rem;color:var(--muted)}
.ff-primary{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:0 1.4rem;border-radius:14px;border:0;background:var(--accent);color:#fff;font-size:1rem;font-weight:600;text-decoration:none;cursor:pointer}
.ff-primary:disabled{opacity:.6;cursor:default}
.ff-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}
.ff-cards-2{grid-template-columns:repeat(2,minmax(0,1fr))}
@media (max-width:900px){.ff-cards,.ff-cards-2{grid-template-columns:minmax(0,1fr)}}
.ff-card{padding:1.4rem;border-radius:20px;border:1px solid var(--edge);background:var(--panel);backdrop-filter:var(--blur);display:flex;flex-direction:column;gap:.85rem;font-size:.95rem;line-height:1.55}
.ff-card-title{display:flex;gap:.6rem;align-items:center;font-size:1.2rem;font-weight:700}
.ff-card-title span{color:var(--text)}
.ff-bad-text{color:var(--bad)}.ff-warn-text{color:var(--warn)}.ff-good-text{color:var(--good)}.ff-accent-text{color:var(--accent)}.ff-muted{color:var(--muted)}.ff-small{font-size:.8rem}
.ff-identity{padding:.85rem;border-radius:14px;background:color-mix(in srgb,var(--text) 5%,transparent);display:flex;flex-direction:column;gap:.2rem}
.ff-identity strong{font-size:1.05rem}.ff-identity span{color:var(--muted);font-size:.88rem}
.ff-chips{display:flex;flex-wrap:wrap;gap:.4rem}
.ff-chips span{padding:.3rem .65rem;border-radius:8px;background:color-mix(in srgb,var(--text) 8%,transparent);font-size:.88rem}
.ff-line{display:flex;gap:.5rem}.ff-line>span:first-child{font-weight:700;white-space:nowrap}
.ff-checks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.6rem}
.ff-checks li{display:flex;gap:.6rem}.ff-checks li>span:first-child{font-weight:700}
.ff-avoid{padding:.85rem;border-radius:14px;background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 40%,transparent);display:flex;flex-direction:column;gap:.3rem}
.ff-avoid strong{color:var(--warn)}
.ff-row{display:flex;justify-content:space-between;align-items:baseline;gap:.75rem;flex-wrap:wrap}
.ff-row h3{font-size:1.2rem;font-weight:700}
.ff-bay-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.75rem}
.ff-bay{padding:.85rem;border-radius:14px;border:2px solid color-mix(in srgb,var(--good) 40%,transparent);background:color-mix(in srgb,var(--text) 4%,transparent);display:flex;flex-direction:column;gap:.2rem}
.ff-bay span{font-size:.82rem}.ff-bay strong{font-size:1rem}
.ff-bay-bad{border-color:var(--bad);background:var(--bad-soft)}
.ff-manual-head h3{font-size:1.6rem;margin:.2rem 0}
.ff-progress{display:flex;flex-direction:column;align-items:flex-end;gap:.4rem;min-width:13rem}
.ff-bar{width:13rem;height:8px;border-radius:999px;background:color-mix(in srgb,var(--text) 12%,transparent);overflow:hidden}
.ff-bar div{height:100%;border-radius:999px;background:var(--good)}
.ff-steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.6rem}
.ff-step{padding:.6rem .85rem;border-radius:16px;border:1px solid var(--edge);background:color-mix(in srgb,var(--text) 3%,transparent)}
.ff-step.ff-open{border-color:color-mix(in srgb,var(--accent) 45%,transparent);background:var(--accent-soft)}
.ff-step-head{display:flex;gap:.85rem;align-items:center}
.ff-tick{flex:0 0 auto;width:44px;height:44px;border-radius:999px;border:2px solid color-mix(in srgb,var(--text) 30%,transparent);background:transparent;color:var(--text);font-size:1.1rem;font-weight:700;cursor:pointer}
.ff-done .ff-tick{background:var(--good);border-color:var(--good);color:#04260f}
.ff-tick:disabled{cursor:default}
.ff-tick:not(:disabled):hover{border-color:var(--accent)}
.ff-step-toggle{flex:1 1 auto;min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:.75rem;background:none;border:0;color:inherit;text-align:left;cursor:pointer;padding:0;font:inherit}
.ff-step-toggle>span:first-child{display:flex;flex-direction:column;gap:.1rem}
.ff-step-title{font-size:1.05rem;font-weight:600}
.ff-done .ff-step-title{color:var(--muted)}
.ff-step-body{margin:.4rem 0 .4rem 3.6rem;display:flex;flex-direction:column;gap:.75rem}
@media (max-width:640px){.ff-step-body{margin-left:0}}
.ff-warn-box{padding:.75rem .9rem;border-radius:12px;background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 40%,transparent)}
.ff-actions{display:flex;gap:.75rem;flex-wrap:wrap;align-items:center}
.ff-actions a{text-decoration:none;color:var(--accent);padding:.6rem .2rem}
.ff-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.9rem}
.ff-tile strong{font-size:1.35rem}
.ff-note{flex-direction:row;flex-wrap:wrap;justify-content:space-between;background:var(--warn-soft)}
#ffTechnical{grid-column:1/-1;border-radius:20px;border:1px solid var(--edge);background:var(--panel);padding:1rem 1.25rem}
#ffTechnical>summary{cursor:pointer;font-weight:600;font-size:1.05rem;min-height:2rem;display:list-item}
#ffTechnical>summary span{font-weight:400;color:var(--muted);font-size:.9rem}
.ff-tech-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.75rem;margin:1rem 0;font-size:.9rem;line-height:1.5}
.ff-tech-grid>div{padding:.85rem;border-radius:12px;background:color-mix(in srgb,var(--text) 4%,transparent);display:flex;flex-direction:column;gap:.2rem}
.ff-tech-body{display:flex;flex-direction:column;gap:1rem}
`;

function install(){
    const host=document.getElementById("cockpitOverview")||document.querySelector("main .grid");
    if(!host){window.setTimeout(install,50);return;}
    if(document.getElementById("friendlyFaultView")) return;

    const style=document.createElement("style");
    style.id="friendlyFaultViewStyle";
    style.textContent=STYLE;
    document.head.appendChild(style);

    const view=document.createElement("section");
    view.id="friendlyFaultView";
    view.setAttribute("aria-live","polite");
    view.setAttribute("aria-label","NAS status");

    const drawer=document.createElement("details");
    drawer.id="ffTechnical";
    drawer.innerHTML='<summary>Technical details <span>· AEGIS, Checkride, Flight Director and raw drive data</span></summary><div class="ff-tech-summary"></div><div class="ff-tech-body"></div>';
    try{ drawer.open=window.localStorage.getItem(DRAWER_KEY)==="1"; }catch(_error){ drawer.open=false; }
    drawer.addEventListener("toggle",()=>{
        try{ window.localStorage.setItem(DRAWER_KEY,drawer.open?"1":"0"); }catch(_error){ /* convenience only */ }
    });

    host.prepend(view);
    view.insertAdjacentElement("afterend",drawer);
    const drawerBody=drawer.querySelector(".ff-tech-body");

    let lastPayload=null;
    const place=()=>{
        // During a fault the plain-language banner leads the page, above the
        // virtual front panel; when all is clear it sits back in the overview.
        const grid=document.querySelector("main .grid");
        const overview=document.getElementById("cockpitOverview")||host;
        if(ui.model&&ui.model.kind==="fault"&&grid){
            if(grid.firstElementChild!==view) grid.prepend(view);
        }else if(view.parentElement!==overview){
            overview.prepend(view);
        }
    };
    const refresh=force=>{
        if(force) ui.lastSignature="";
        if(lastPayload) render(view,drawer,lastPayload);
        place();
        adopt(drawerBody);
    };

    view.addEventListener("click",event=>{
        const target=event.target;
        const opener=target.closest?.("[data-ff-open]");
        if(opener){
            const key=opener.dataset.ffOpen;
            const effective=ui.open===null?ui.current:ui.open;
            ui.open=effective===key?"":key;
            refresh(true);
            return;
        }
        const tick=target.closest?.("[data-ff-tick]");
        if(tick&&!tick.disabled&&ui.model){
            const key=tick.dataset.ffTick;
            const ticks=loadTicks(ui.model.incidentId);
            ticks[key]=!ticks[key];
            saveTicks(ui.model.incidentId,ticks);
            ui.open=null;
            refresh(true);
            return;
        }
        const action=target.closest?.("[data-ff-action]");
        if(action) runAction(action.dataset.ffAction,refresh);
    });

    window.addEventListener("truepanel:status",event=>{
        const payload=event?.detail;
        if(!payload||typeof payload!=="object") return;
        lastPayload=payload;
        refresh();
    });

    const poll=async()=>{
        try{
            const response=await fetch(STATUS_URL,{cache:"no-store",headers:{Accept:"application/json"}});
            if(!response.ok) throw new Error(`status ${response.status}`);
            lastPayload=await response.json();
        }catch(_error){
            // Keep the last good view; the header badge reports connection loss.
        }
        refresh();
    };
    poll();
    window.setInterval(poll,POLL_MS);
    // Late-installing companion panels are adopted as they appear, and the
    // banner keeps its place if another script reorders the page after us.
    window.setInterval(()=>{place();adopt(drawerBody);},1000);
}

const api={buildModel,friendlyModel,terabytes,scrubSummary,backupStatus,sizeLabel,esc};
if(typeof module!=="undefined"&&module.exports) module.exports=api;
if(typeof document!=="undefined"){
    if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",install,{once:true});
    else install();
}
})();
