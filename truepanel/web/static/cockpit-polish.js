(()=>{
"use strict";

function el(tag,className,text){
    const node=document.createElement(tag);
    if(className) node.className=className;
    if(text!==undefined) node.textContent=String(text);
    return node;
}

function installStyle(){
    if(document.getElementById("cockpitPolishStyle")) return;

    const style=document.createElement("style");
    style.id="cockpitPolishStyle";
    style.textContent=`
.cockpit-drawer{margin-top:.85rem;padding:0 .9rem;border:1px solid rgba(143,164,184,.2);border-radius:10px;background:rgba(3,9,15,.46)}
.cockpit-drawer>summary{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.85rem 0;cursor:pointer;list-style:none;color:var(--text)}
.cockpit-drawer>summary::-webkit-details-marker{display:none}.cockpit-drawer>summary::before{content:"▸";margin-right:.5rem;color:var(--muted);font-size:.7rem}.cockpit-drawer[open]>summary::before{content:"▾"}.cockpit-drawer-title{display:flex;align-items:center;font-size:.75rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}.cockpit-drawer-state{margin-left:auto;color:var(--muted);font-size:.72rem;font-weight:600;letter-spacing:.01em;text-align:right;text-transform:none}.cockpit-drawer-state.good{color:var(--good)}.cockpit-drawer-state.warn{color:var(--warn)}.cockpit-drawer-state.bad{color:var(--bad)}.cockpit-drawer[open]>summary{border-bottom:1px solid rgba(143,164,184,.14)}
.cockpit-lcd-drawer .lcd-transport{max-width:none;margin:0;padding:.85rem 0;border:0;border-radius:0;background:transparent}.cockpit-lcd-drawer .lcd-transport h3{display:none}
.cockpit-cooling-drawer .control-panel{margin:0;padding:.85rem 0 0;border-top:0}.cockpit-cooling-drawer+.diagnostics-drawer{margin-top:.75rem}
.cooling-instrument[data-cockpit-readiness="uncommissioned"]{border-color:rgba(255,200,87,.34);background:rgba(54,39,10,.16)}
.preflight-section[data-cockpit-review="true"]{position:relative;cursor:pointer;border-color:rgba(255,200,87,.5);box-shadow:inset 0 0 0 1px rgba(255,200,87,.05)}.preflight-section[data-cockpit-review="true"]:hover{background:rgba(255,200,87,.07)}.preflight-section[data-cockpit-review="true"]:focus-visible{outline:2px solid var(--warn);outline-offset:2px}.preflight-review-hint{display:block;margin-top:.35rem;color:var(--warn);font-size:.62rem;font-weight:750;letter-spacing:.05em;text-transform:uppercase}.preflight-detail-group.cockpit-preflight-focus{border-left:2px solid var(--warn);padding-left:.75rem;animation:cockpitFocus 1.2s ease-out}@keyframes cockpitFocus{0%{background:rgba(255,200,87,.12)}100%{background:transparent}}
.cockpit-maintenance-drawer{grid-column:1/-1;margin:0;padding:0 1rem;border:1px solid var(--edge);border-radius:14px;background:linear-gradient(145deg,rgba(12,20,30,.9),rgba(7,12,19,.94))}.cockpit-maintenance-drawer>summary{display:flex;align-items:center;gap:.8rem;padding:1rem 0;cursor:pointer;list-style:none}.cockpit-maintenance-drawer>summary::-webkit-details-marker{display:none}.cockpit-maintenance-drawer>summary::before{content:"▸";color:var(--muted);font-size:.72rem}.cockpit-maintenance-drawer[open]>summary::before{content:"▾"}.cockpit-maintenance-title{font-size:.76rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase}.cockpit-maintenance-state{margin-left:auto;color:var(--muted);font-size:.72rem;text-align:right}.cockpit-maintenance-state.good{color:var(--good)}.cockpit-maintenance-state.warn{color:var(--warn)}.cockpit-maintenance-drawer[open]>summary{border-bottom:1px solid rgba(143,164,184,.14)}.cockpit-maintenance-drawer>.card{margin:1rem 0;grid-column:auto}.cockpit-maintenance-drawer>.card+ .card{margin-top:0}
@media(max-width:640px){.cockpit-drawer>summary,.cockpit-maintenance-drawer>summary{align-items:flex-start}.cockpit-drawer-state,.cockpit-maintenance-state{max-width:55%}}
`;
    document.head.appendChild(style);
}

function drawerAround(target,{id,className,title,state}){
    if(!target||document.getElementById(id)) return null;

    const details=el("details",`cockpit-drawer ${className||""}`.trim());
    details.id=id;

    const summary=el("summary");
    const titleNode=el("span","cockpit-drawer-title",title);
    const stateNode=el("span","cockpit-drawer-state","Checking");
    summary.append(titleNode,stateNode);

    target.parentNode.insertBefore(details,target);
    details.append(summary,target);

    const refresh=()=>{
        const result=state();
        const desiredText=String(result.text||"");
        const desiredClass=`cockpit-drawer-state ${result.tone||""}`.trim();
        if(stateNode.textContent!==desiredText){
            stateNode.textContent=desiredText;
        }
        if(stateNode.className!==desiredClass){
            stateNode.className=desiredClass;
        }
    };

    refresh();
    return{details,stateNode,refresh};
}

function installLcdTransportDrawer(){
    const transport=document.querySelector(".lcd-transport");
    if(!transport) return;

    const connection=document.getElementById("lcdTransportConnection");
    const reader=document.getElementById("lcdTransportReader");
    const dispatcher=document.getElementById("lcdTransportDispatcher");

    const wrapper=drawerAround(transport,{
        id:"cockpitLcdTransport",
        className:"cockpit-lcd-drawer",
        title:"LCD Transport",
        state:()=>{
            const values=[connection,reader,dispatcher]
                .filter(Boolean)
                .map(node=>String(node.textContent||"").trim().toLowerCase());
            const failed=values.some(value=>
                value.includes("disconnected")
                ||value.includes("offline")
                ||value.includes("failed")
                ||value.includes("error")
            );
            const healthy=values.length>=2&&values.every(value=>
                value.includes("connected")
                ||value.includes("running")
                ||value.includes("healthy")
            );
            return failed
                ?{text:"Attention required",tone:"bad"}
                :healthy
                    ?{text:"Healthy",tone:"good"}
                    :{text:"Checking",tone:""};
        },
    });

    if(!wrapper) return;
    [connection,reader,dispatcher].filter(Boolean).forEach(node=>{
        new MutationObserver(wrapper.refresh).observe(node,{
            childList:true,
            subtree:true,
            characterData:true,
            attributes:true,
            attributeFilter:["class"],
        });
    });
}

function installCoolingControlsDrawer(){
    const connection=document.getElementById("fanControlConnection");
    const panel=connection?.closest(".control-panel");
    if(!panel) return;

    const active=document.getElementById("fanActiveProfile");
    const recommendation=document.getElementById("fanThermalRecommendation");
    const safety=document.getElementById("thermalArmState");

    const wrapper=drawerAround(panel,{
        id:"cockpitCoolingControls",
        className:"cockpit-cooling-drawer",
        title:"Controls & Automation",
        state:()=>{
            const activeText=String(active?.textContent||"Automatic").trim();
            const recommendationText=String(recommendation?.textContent||"").trim();
            const mode=(recommendationText.split("·")[1]||"").trim();
            const safetyText=String(safety?.textContent||"").trim().toLowerCase();
            const connectionText=String(connection?.textContent||"").trim().toLowerCase();
            const failed=(
                connectionText.includes("disconnected")
                && !connectionText.includes("disabled")
            )||safetyText.includes("fault");

            if(failed){
                return{text:"Attention required",tone:"bad"};
            }

            return{
                text:`Active ${activeText}${mode?` · ${mode}`:""}`,
                tone:"",
            };
        },
    });

    if(!wrapper) return;
    [connection,active,recommendation,safety].filter(Boolean).forEach(node=>{
        new MutationObserver(wrapper.refresh).observe(node,{
            childList:true,
            subtree:true,
            characterData:true,
            attributes:true,
            attributeFilter:["class"],
        });
    });
}

function installThermalReadinessSemantics(){
    const readiness=document.getElementById("fanThermalReadiness");
    if(!readiness) return;

    const instrument=readiness.closest(".cooling-instrument");

    const refresh=()=>{
        const current=String(readiness.textContent||"").trim();
        const normalized=current.toLowerCase();
        const intentional=(
            normalized.includes("thermal policy is not configured for automatic control")
            ||normalized.startsWith("not commissioned")
        );

        if(!intentional){
            if(instrument?.hasAttribute("data-cockpit-readiness")){
                instrument.removeAttribute("data-cockpit-readiness");
            }
            return;
        }

        const desired="Not commissioned · Observe only";
        const desiredClass="value warn";
        if(readiness.textContent!==desired){
            readiness.textContent=desired;
        }
        if(readiness.className!==desiredClass){
            readiness.className=desiredClass;
        }
        if(instrument?.getAttribute("data-cockpit-readiness")!=="uncommissioned"){
            instrument.setAttribute("data-cockpit-readiness","uncommissioned");
        }
    };

    new MutationObserver(refresh).observe(readiness,{
        childList:true,
        subtree:true,
        characterData:true,
        attributes:true,
        attributeFilter:["class"],
    });
    refresh();
}

function installPreflightReviewNavigation(){
    const sections=document.getElementById("preflightSections");
    const details=document.querySelector(".preflight-details");
    const detailRoot=document.getElementById("preflightDetails");
    if(!sections||!details||!detailRoot) return;

    const annotate=()=>{
        [...sections.children].forEach(card=>{
            const status=card.querySelector(".preflight-section-status");
            const review=String(status?.textContent||"").trim().toUpperCase()==="REVIEW";
            if(review){
                if(card.dataset.cockpitReview!=="true"){
                    card.dataset.cockpitReview="true";
                }
                if(card.getAttribute("role")!=="button"){
                    card.setAttribute("role","button");
                }
                if(card.tabIndex!==0){
                    card.tabIndex=0;
                }
                if(!card.querySelector(".preflight-review-hint")){
                    card.append(el("span","preflight-review-hint","Review details →"));
                }
            }else{
                if(card.dataset.cockpitReview!==undefined){
                    delete card.dataset.cockpitReview;
                }
                if(card.hasAttribute("role")){
                    card.removeAttribute("role");
                }
                if(card.hasAttribute("tabindex")){
                    card.removeAttribute("tabindex");
                }
                card.querySelector(".preflight-review-hint")?.remove();
            }
        });
    };

    const openReview=card=>{
        if(card?.dataset.cockpitReview!=="true") return;
        const cards=[...sections.children];
        const index=cards.indexOf(card);
        const group=detailRoot.children[index];
        if(index<0||!group) return;

        details.open=true;
        detailRoot.querySelectorAll(".cockpit-preflight-focus").forEach(node=>
            node.classList.remove("cockpit-preflight-focus")
        );
        group.classList.add("cockpit-preflight-focus");
        window.requestAnimationFrame(()=>{
            group.scrollIntoView({behavior:"smooth",block:"center"});
        });
    };

    sections.addEventListener("click",event=>{
        openReview(event.target.closest(".preflight-section"));
    });
    sections.addEventListener("keydown",event=>{
        if(!["Enter"," "].includes(event.key)) return;
        const card=event.target.closest(".preflight-section");
        if(card?.dataset.cockpitReview!=="true") return;
        event.preventDefault();
        openReview(card);
    });

    new MutationObserver(annotate).observe(sections,{
        childList:true,
        subtree:true,
        characterData:true,
    });
    annotate();
}

function installMaintenanceDrawer(){
    if(document.getElementById("cockpitMaintenance")) return;

    const night=document.getElementById("nightEnabled")?.closest("article");
    const status=document.getElementById("configMode")?.closest("article");
    if(!night||!status||night.parentNode!==status.parentNode) return;

    const configMode=document.getElementById("configMode");
    const directRow=[...status.querySelectorAll(".row")].find(row=>
        String(row.querySelector(".label")?.textContent||"").trim()==="Direct hardware access"
    );
    const directValue=directRow?.querySelector(".value");

    const details=el("details","cockpit-maintenance-drawer");
    details.id="cockpitMaintenance";
    const summary=el("summary");
    const title=el("span","cockpit-maintenance-title","Configuration & Mission Control");
    const state=el("span","cockpit-maintenance-state","Checking");
    summary.append(title,state);

    night.parentNode.insertBefore(details,night);
    details.append(summary,night,status);

    const refresh=()=>{
        const config=String(configMode?.textContent||"Configuration").trim();
        const hardware=String(directValue?.textContent||"Unknown").trim();
        const safe=(
            config.toLowerCase().includes("read only")
            &&hardware.toLowerCase().includes("disabled")
        );
        const desiredText=`${config} · Hardware ${hardware}`;
        const desiredClass=`cockpit-maintenance-state ${safe?"good":"warn"}`;
        if(state.textContent!==desiredText){
            state.textContent=desiredText;
        }
        if(state.className!==desiredClass){
            state.className=desiredClass;
        }
    };

    [configMode,directValue].filter(Boolean).forEach(node=>{
        new MutationObserver(refresh).observe(node,{
            childList:true,
            subtree:true,
            characterData:true,
            attributes:true,
            attributeFilter:["class"],
        });
    });
    refresh();
}

function cleanFooter(){
    const footer=document.querySelector("footer");
    if(footer) footer.textContent="TruePanel Mission Control";
}

function install(){
    installStyle();
    installLcdTransportDrawer();
    installCoolingControlsDrawer();
    installThermalReadinessSemantics();
    installPreflightReviewNavigation();
    installMaintenanceDrawer();
    cleanFooter();
    document.body.classList.add("cockpit-polished");
}

if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",install,{once:true});
}else{
    install();
}
})();
