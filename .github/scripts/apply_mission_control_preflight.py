"""One-shot builder for the Mission Control Preflight feature branch."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def patch_once(path: str, marker: str, anchor: str, replacement: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")

    if marker in source:
        return

    if anchor not in source:
        raise RuntimeError(f"Could not find patch anchor in {path}: {anchor[:80]!r}")

    target.write_text(
        source.replace(anchor, replacement, 1),
        encoding="utf-8",
    )


def append_once(path: str, marker: str, addition: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")

    if marker in source:
        return

    target.write_text(
        source.rstrip() + "\n\n" + addition.strip() + "\n",
        encoding="utf-8",
    )


# Backend imports.
patch_once(
    "truepanel/web/server.py",
    "from truepanel.compatibility.checks import collect_compatibility",
    "from urllib.parse import parse_qs, urlparse\n\nfrom truepanel.config.persistence import (",
    "from urllib.parse import parse_qs, urlparse\n\n"
    "from truepanel.compatibility.checks import collect_compatibility\n"
    "from truepanel.compatibility.support import (\n"
    "    build_support_bundle,\n"
    "    default_support_path,\n"
    ")\n"
    "from truepanel.config.persistence import (",
)

patch_once(
    "truepanel/web/server.py",
    "from .preflight import build_preflight_payload",
    "from .snapshot import SnapshotService",
    "from .preflight import build_preflight_payload\n"
    "from .snapshot import SnapshotService",
)

# Read-only GET routes.
patch_once(
    "truepanel/web/server.py",
    '"/api/v1/preflight": self._preflight,',
    '            "/api/v1/status": self._status,\n',
    '            "/api/v1/status": self._status,\n'
    '            "/api/v1/preflight": self._preflight,\n'
    '            "/api/v1/preflight/support-bundle": (\n'
    '                self._preflight_support_bundle\n'
    '            ),\n',
)

# On-demand compatibility collection. Nothing here enters the telemetry loop.
patch_once(
    "truepanel/web/server.py",
    "def _preflight_support_bundle(self, parsed):",
    "    def _lcd_status(self, parsed):\n",
    '''    def _preflight(self, parsed):
        del parsed

        try:
            report = collect_compatibility()
        except Exception:
            LOGGER.exception(
                "Mission Control preflight survey failed"
            )
            self._json(
                {
                    "error": "preflight_unavailable",
                    "message": (
                        "Passive compatibility survey could not complete."
                    ),
                },
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        self._json(
            build_preflight_payload(report)
        )

    def _preflight_support_bundle(self, parsed):
        del parsed

        try:
            report = collect_compatibility()
            payload = build_support_bundle(report)
            filename = default_support_path().name
        except Exception:
            LOGGER.exception(
                "Mission Control support bundle generation failed"
            )
            self._json(
                {
                    "error": "support_bundle_unavailable",
                    "message": (
                        "Privacy-safe support bundle could not be generated."
                    ),
                },
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        self._json(
            payload,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                ),
                "Cache-Control": "no-store",
            },
        )

    def _lcd_status(self, parsed):
''',
)

# Dashboard styling. Keep the panel in the existing Mission Control visual grammar.
patch_once(
    "truepanel/web/static/index.html",
    ".preflight-panel{",
    ".lcd-panel{grid-column:1/-1;",
    '''.preflight-panel{position:relative;overflow:hidden;border-color:rgba(57,167,255,.34);background:linear-gradient(130deg,rgba(13,30,45,.98),rgba(7,14,23,.98) 58%,rgba(8,24,36,.98))}
.preflight-panel::after{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(90deg,transparent,rgba(57,167,255,.025),transparent)}
.preflight-head,.preflight-sections,.preflight-actions,.preflight-details,.preflight-message{position:relative;z-index:1}
.preflight-head{display:flex;align-items:flex-start;justify-content:space-between;gap:1.5rem}
.preflight-head h2{margin-bottom:.45rem}
.preflight-status{font-size:clamp(1.7rem,4vw,2.8rem);font-weight:850;line-height:1;letter-spacing:.05em}
.preflight-status.good{color:var(--good)}
.preflight-status.warn{color:var(--warn)}
.preflight-status.bad{color:var(--bad)}
.preflight-summary{margin-top:.45rem;color:var(--text);font-size:.95rem}
.preflight-meta{display:flex;flex-direction:column;align-items:flex-end;gap:.25rem;color:var(--muted);font-size:.75rem;text-align:right}
.preflight-meta strong{color:var(--text);font-weight:700}
.preflight-sections{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin-top:1.15rem}
.preflight-section{min-width:0;padding:.75rem;border:1px solid var(--edge);border-radius:10px;background:rgba(3,8,13,.5)}
.preflight-section-name{display:block;overflow:hidden;color:var(--muted);font-size:.68rem;letter-spacing:.08em;text-overflow:ellipsis;text-transform:uppercase}
.preflight-section-status{display:block;margin-top:.3rem;font-size:.9rem;font-weight:800;letter-spacing:.04em}
.preflight-section-status.good{color:var(--good)}
.preflight-section-status.warn{color:var(--warn)}
.preflight-section-status.bad{color:var(--bad)}
.preflight-section-count{display:block;margin-top:.2rem;color:var(--muted);font-size:.7rem}
.preflight-actions{display:flex;flex-wrap:wrap;gap:.7rem;margin-top:1rem}
.button-link{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--edge);border-radius:8px;padding:.7rem 1rem;background:#132030;color:var(--text);font-size:.86rem;font-weight:700;text-decoration:none}
.button-link:hover{border-color:#238fd5;background:#172b3e}
.preflight-details{margin-top:1rem;padding:.75rem .9rem;border:1px solid rgba(143,164,184,.18);border-radius:10px;background:rgba(3,9,15,.46)}
.preflight-details>summary{cursor:pointer;color:var(--text);font-size:.8rem;font-weight:750;letter-spacing:.06em;text-transform:uppercase}
.preflight-detail-group{margin-top:.8rem}
.preflight-detail-group h3{margin:0 0 .35rem;color:var(--muted);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}
.preflight-check{display:grid;grid-template-columns:minmax(130px,.8fr) minmax(90px,.35fr) minmax(220px,1.7fr);gap:.75rem;padding:.5rem 0;border-bottom:1px solid rgba(143,164,184,.12);font-size:.78rem}
.preflight-check:last-child{border-bottom:0}
.preflight-check-name{color:var(--text);font-weight:650}
.preflight-check-status{font-weight:800}
.preflight-check-status.good{color:var(--good)}
.preflight-check-status.warn{color:var(--warn)}
.preflight-check-status.bad{color:var(--bad)}
.preflight-check-detail{color:var(--muted);overflow-wrap:anywhere}
.preflight-message{min-height:1rem;margin-top:.7rem;color:var(--muted);font-size:.75rem}
.preflight-message.good{color:var(--good)}
.preflight-message.warn{color:var(--warn)}
.preflight-message.bad{color:var(--bad)}
@media(max-width:900px){.preflight-sections{grid-template-columns:repeat(2,minmax(0,1fr))}.preflight-section:last-child{grid-column:1/-1}}
@media(max-width:640px){.preflight-head{display:block}.preflight-meta{align-items:flex-start;margin-top:.7rem;text-align:left}.preflight-sections{grid-template-columns:1fr}.preflight-section:last-child{grid-column:auto}.preflight-check{grid-template-columns:1fr;gap:.2rem}}
.lcd-panel{grid-column:1/-1;''',
)

# Dashboard markup directly beneath System Health.
patch_once(
    "truepanel/web/static/index.html",
    'id="preflightTitle"',
    '<button id="openFlightManual" type="button" disabled>Open Flight Manual</button>\n</article>\n<article class="card"><h2>CPU</h2>',
    '''<button id="openFlightManual" type="button" disabled>Open Flight Manual</button>
</article>
<article id="preflightPanel" class="card wide preflight-panel" aria-labelledby="preflightTitle">
<div class="preflight-head">
<div>
<h2 id="preflightTitle">Preflight</h2>
<div id="preflightFlightStatus" class="preflight-status warn">CHECKING</div>
<div id="preflightSummary" class="preflight-summary">Running passive compatibility survey.</div>
</div>
<div class="preflight-meta">
<span>Mode: <strong id="preflightMode">Observation only</strong></span>
<span>Authority: <strong id="preflightAuthority">Hardware control locked</strong></span>
<span id="preflightCounts">Awaiting checks</span>
</div>
</div>
<div id="preflightSections" class="preflight-sections" aria-label="Preflight subsystem results"></div>
<div class="preflight-actions">
<button id="runPreflight" class="primary" type="button">Run Preflight Again</button>
<a id="preflightSupportBundle" class="button-link" href="/api/v1/preflight/support-bundle" download>Download Support Bundle</a>
</div>
<details class="preflight-details">
<summary>View compatibility details</summary>
<div id="preflightDetails"></div>
</details>
<div id="preflightMessage" class="preflight-message" aria-live="polite">Compatibility checks run on demand and never grant hardware-control authority.</div>
</article>
<article class="card"><h2>CPU</h2>''',
)

# Safe DOM-only rendering for host-derived compatibility strings.
patch_once(
    "truepanel/web/static/index.html",
    "function preflightTone(status){",
    "function formPatch(){return{enabled:q(\"nightEnabled\")",
    '''function preflightTone(status){
    const normalized=String(status||"").toUpperCase();

    if(normalized==="READY"||normalized==="PASS"){
        return "good";
    }

    if(normalized==="HOLD"||normalized==="FAIL"){
        return "bad";
    }

    return "warn";
}

function preflightElement(tag,className,text){
    const element=document.createElement(tag);

    if(className){
        element.className=className;
    }

    if(text!==undefined&&text!==null){
        element.textContent=String(text);
    }

    return element;
}

function renderPreflight(payload){
    const flightStatus=String(
        payload&&payload.flight_status||"REVIEW"
    ).toUpperCase();
    const tone=preflightTone(flightStatus);
    const sections=Array.isArray(payload&&payload.sections)
        ?payload.sections
        :[];
    const counts=payload&&payload.counts||{};

    q("preflightPanel").dataset.loaded="true";
    q("preflightFlightStatus").textContent=flightStatus;
    q("preflightFlightStatus").className=
        `preflight-status ${tone}`;
    q("preflightSummary").textContent=val(
        payload&&payload.summary,
        "Compatibility result available."
    );
    q("preflightMode").textContent=val(
        payload&&payload.installation_mode,
        "Observation only"
    );
    q("preflightAuthority").textContent=val(
        payload&&payload.hardware_control,
        "Hardware control locked"
    );
    q("preflightCounts").textContent=(
        `${Number(counts.pass||0)} pass · `
        +`${Number(counts.review||0)} review · `
        +`${Number(counts.fail||0)} fail`
    );

    const sectionRoot=q("preflightSections");
    const detailsRoot=q("preflightDetails");
    sectionRoot.replaceChildren();
    detailsRoot.replaceChildren();

    sections.forEach(section=>{
        const checks=Array.isArray(section&&section.checks)
            ?section.checks
            :[];
        const sectionStatus=String(
            section&&section.status||"REVIEW"
        ).toUpperCase();
        const sectionTone=preflightTone(sectionStatus);
        const card=preflightElement(
            "div",
            "preflight-section"
        );
        card.append(
            preflightElement(
                "span",
                "preflight-section-name",
                val(section&&section.label,"Unknown")
            ),
            preflightElement(
                "strong",
                `preflight-section-status ${sectionTone}`,
                sectionStatus
            ),
            preflightElement(
                "span",
                "preflight-section-count",
                `${checks.length} ${checks.length===1?"check":"checks"}`
            )
        );
        sectionRoot.append(card);

        const group=preflightElement(
            "section",
            "preflight-detail-group"
        );
        group.append(
            preflightElement(
                "h3",
                "",
                val(section&&section.label,"Unknown")
            )
        );

        if(!checks.length){
            group.append(
                preflightElement(
                    "div",
                    "detail",
                    "No checks reported."
                )
            );
        }

        checks.forEach(check=>{
            const checkStatus=String(
                check&&check.status||"REVIEW"
            ).toUpperCase();
            const row=preflightElement(
                "div",
                "preflight-check"
            );
            row.append(
                preflightElement(
                    "span",
                    "preflight-check-name",
                    val(check&&check.name,"Unnamed check")
                ),
                preflightElement(
                    "span",
                    `preflight-check-status ${preflightTone(checkStatus)}`,
                    checkStatus
                ),
                preflightElement(
                    "span",
                    "preflight-check-detail",
                    val(check&&check.detail,"No detail reported")
                )
            );
            group.append(row);
        });

        detailsRoot.append(group);
    });
}

let preflightRequestInFlight=false;

async function loadPreflight(){
    if(preflightRequestInFlight){
        return;
    }

    preflightRequestInFlight=true;
    q("runPreflight").disabled=true;
    q("preflightMessage").textContent=
        "Running passive compatibility survey…";
    q("preflightMessage").className=
        "preflight-message warn";

    try{
        const response=await fetch(
            "/api/v1/preflight",
            {cache:"no-store"}
        );
        const payload=await response.json();

        if(!response.ok){
            throw Error(
                payload.message
                ||"Preflight survey failed"
            );
        }

        renderPreflight(payload);

        const tone=preflightTone(
            payload.flight_status
        );
        q("preflightMessage").textContent=
            "Passive compatibility survey complete.";
        q("preflightMessage").className=
            `preflight-message ${tone}`;
    }catch(error){
        q("preflightFlightStatus").textContent=
            "UNAVAILABLE";
        q("preflightFlightStatus").className=
            "preflight-status bad";
        q("preflightSummary").textContent=
            "Preflight could not complete.";
        q("preflightMessage").textContent=
            error.message;
        q("preflightMessage").className=
            "preflight-message bad";
    }finally{
        preflightRequestInFlight=false;
        q("runPreflight").disabled=false;
    }
}

function formPatch(){return{enabled:q("nightEnabled")''',
)

# The preflight survey loads once on page startup and only reruns by operator action.
patch_once(
    "truepanel/web/static/index.html",
    'q("runPreflight").addEventListener(',
    'q("thermalArm").addEventListener(\n',
    '''q("runPreflight").addEventListener(
    "click",
    ()=>loadPreflight()
);

q("thermalArm").addEventListener(
''',
)

patch_once(
    "truepanel/web/static/index.html",
    "loadPreflight();\nrefresh();",
    "refresh();\nrefreshVirtualLcd();\n",
    "loadPreflight();\nrefresh();\nrefreshVirtualLcd();\n",
)

# Runtime and dashboard contract tests.
append_once(
    "tests/test_web_preflight.py",
    "def test_preflight_handler_returns_projected_payload",
    '''def _handler_with_json_capture():
    from truepanel.web.server import MissionControlRequestHandler

    handler = object.__new__(MissionControlRequestHandler)
    captured = []

    def capture(payload, **kwargs):
        captured.append((payload, kwargs))

    handler._json = capture
    return handler, captured


def test_preflight_handler_returns_projected_payload(monkeypatch):
    from truepanel.web import server as server_module

    handler, captured = _handler_with_json_capture()
    monkeypatch.setattr(
        server_module,
        "collect_compatibility",
        lambda: make_report(),
    )

    handler._preflight(None)

    assert captured[0][0]["flight_status"] == "READY"
    assert captured[0][0]["read_only"] is True
    assert captured[0][1] == {}


def test_support_bundle_handler_is_downloadable_and_privacy_safe(monkeypatch):
    from truepanel.compatibility.support import (
        support_bundle_contains_forbidden_keys,
    )
    from truepanel.web import server as server_module

    handler, captured = _handler_with_json_capture()
    monkeypatch.setattr(
        server_module,
        "collect_compatibility",
        lambda: make_report(),
    )

    handler._preflight_support_bundle(None)

    payload, kwargs = captured[0]
    headers = kwargs["headers"]

    assert support_bundle_contains_forbidden_keys(payload) == set()
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Disposition"].startswith(
        'attachment; filename="truepanel-support-'
    )


def test_preflight_routes_are_registered():
    from truepanel.web.server import MissionControlRequestHandler

    handler = object.__new__(MissionControlRequestHandler)
    called = []
    handler.path = "/api/v1/preflight"
    handler._preflight = lambda parsed: called.append(parsed.path)

    handler.do_GET()

    assert called == ["/api/v1/preflight"]


def test_dashboard_preflight_is_on_demand_not_in_refresh_loop():
    from pathlib import Path

    source = (
        Path(__file__).parents[1]
        / "truepanel"
        / "web"
        / "static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'id="preflightTitle"' in source
    assert 'id="runPreflight"' in source
    assert 'href="/api/v1/preflight/support-bundle"' in source
    assert 'fetch(\n            "/api/v1/preflight"' in source
    assert "loadPreflight();\nrefresh();" in source
    assert "setInterval(loadPreflight" not in source
    assert "setInterval(refresh,5000);" in source
    assert "replaceChildren()" in source
''',
)
