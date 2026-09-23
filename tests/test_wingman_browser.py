"""Run Wingman's real cockpit JavaScript in a mock browser with no host access."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "truepanel/web/static/wingman.js"

NODE_HARNESS = r"""
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

async function exercise(ready) {
    const requests = [];
    const nodes = {};
    const controls = {};
    for (const selector of [".wm-ai", ".wm-offline", ".wm-readiness"]) {
        controls[selector] = {
            disabled: false,
            textContent: "",
            setAttribute() {},
            removeAttribute() {},
            addEventListener(event, fn) {
                assert.equal(event, "click");
                this.click = fn;
            },
        };
    }
    for (const selector of [".wm-body", ".wm-offline-panel",
        ".wm-readiness-panel"]) {
        nodes[selector] = {innerHTML: "", querySelector() {return null;}};
    }
    const deepDive = {open:false};
    const view = {
        dataset: {},
        innerHTML: "",
        setAttribute() {},
        querySelector(selector) {
            return controls[selector] || nodes[selector]
                || (selector === ".wm-deep-dive" ? deepDive : null);
        },
    };
    const document = {
        readyState: "complete",
        head: {appendChild() {}},
        createElement(tag) {return tag === "article" ? view : {};},
        getElementById(id) {
            return id === "glassCockpitSituation"
                ? {insertAdjacentElement() {}} : null;
        },
        querySelector(selector) {
            return selector === "main .grid" ? {} : null;
        },
    };
    const offline = {
        project: "WINGMAN",schema_version:1,advisory_only:true,
        control_authority:false,production_mutation:false,model_invoked:false,
        mode:"offline_brief",status:"OBSERVED",
        summary:"Pool HDDs: reported ONLINE. AEGIS reports HOLD.",
        source_ids:["status:storage","status:reliability"],
        observations:[],uncertainty:["SMART status unavailable."],
    };
    const readiness = {
        project:"WINGMAN",schema_version:1,advisory_only:true,
        control_authority:false,production_mutation:false,model_invoked:false,
        launch_authorized:false,
        status:ready?"READY_FOR_RECHECK":"HOLD",
        reason_codes:ready?[]:["MEMORY_BELOW_POLICY"],
        available_memory_gib:ready?5.0:1.18,minimum_memory_gib:3.0,
        load_1m:4.63,maximum_load_1m:6.0,
    };
    const generated = {
        status:"EXPLAINED",advisory_only:true,control_authority:false,
        production_mutation:false,
        advisory:{summary:"Model report.",summary_source_ids:["status:storage"],
            observations:[],next_steps:[],uncertainty:[]},
    };
    const fetch = async (url,options) => {
        requests.push([url,options.method]);
        if (url.endsWith("/offline-brief") && options.method==="GET") {
            return {ok:true,async json(){return offline;}};
        }
        if (url.endsWith("/readiness") && options.method==="GET") {
            return {ok:true,async json(){return readiness;}};
        }
        if (url.endsWith("/brief") && options.method==="POST") {
            if (!ready) throw new Error("Model invoked under HOLD!");
            return {ok:true,status:200,async json(){return generated;}};
        }
        throw new Error("Unexpected HTTP request");
    };
    vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),{
        document,fetch,window:{setTimeout(){}},performance:{now(){return 0;}},
        console,
    });
    assert.equal(requests.length,0,"No automatic model or status requests");
    assert(view.innerHTML.indexOf('class="wm-ai"') === -1 ||
        view.innerHTML.includes('wm-ai'));
    assert(view.innerHTML.indexOf('wm-ai"') < view.innerHTML.indexOf('wm-offline"'),
        "AI brief is the first, primary control");
    assert(view.innerHTML.includes('<details class="wm-deep-dive">'),
        "Engineer details use a collapsed disclosure");
    assert(!view.innerHTML.includes('<details class="wm-deep-dive" open'),
        "Engineer details start closed");
    assert.equal(deepDive.open,false);
    assert(nodes[".wm-body"].innerHTML === "" ||
        view.innerHTML.includes("Select AI BRIEF for a plain-language explanation"));
    await controls[".wm-offline"].click();
    assert.deepEqual(requests.map(r=>r[1]),["GET"]);
    assert(nodes[".wm-offline-panel"].innerHTML.includes("Pool HDDs"));
    assert(nodes[".wm-offline-panel"].innerHTML.includes("UNCERTAINTY"));
    await controls[".wm-readiness"].click();
    assert.deepEqual(requests.map(r=>r[1]),["GET","GET"]);
    assert(nodes[".wm-readiness-panel"].innerHTML.includes(
        ready?"READY FOR RECHECK":"RESOURCE HOLD"));
    await controls[".wm-ai"].click();
    assert.deepEqual(requests.map(r=>r[1]),
        ready?["GET","GET","GET","POST"]:["GET","GET","GET"]);
    assert(nodes[".wm-offline-panel"].innerHTML.includes("AEGIS reports HOLD"),
        "An AI request must never erase a previously displayed offline HOLD.");
    if (!ready) {
        assert(nodes[".wm-body"].innerHTML.includes("RESOURCE HOLD"));
        assert.equal(deepDive.open,true,"Show readiness reasons when AI is on HOLD");
        assert.equal(controls[".wm-ai"].disabled,false);
    } else {
        assert(nodes[".wm-body"].innerHTML.includes("Model report."));
        assert.equal(controls[".wm-ai"].textContent,"AI BRIEF");
    }
}

(async () => {
    await exercise(false);
    await exercise(true);
})().catch(error => {console.error(error);process.exitCode=1;});
"""


def test_wingman_cockpit_obeys_readiness_and_preserves_offline_hold():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable: browser contract exercised in CI")
    subprocess.run([node, "-e", NODE_HARNESS, str(SCRIPT)], check=True)


def test_wingman_cockpit_script_has_valid_javascript():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable: syntax checked in CI")
    subprocess.run([node, "--check", str(SCRIPT)], check=True)
