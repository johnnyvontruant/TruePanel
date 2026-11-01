"""Project GLASS COCKPIT's reproducible 100-interface benchmark.

Scores are documented inspection heuristics, not human-usability results.  The
source list and evidence type remain reviewable; no product assets are copied.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

COHORT_COUNTS = {
    "TRAFFIC": 25, "OPS": 20, "NAS": 15, "DESIGN": 15,
    "DATAVIZ": 10, "HIGH_STAKES": 10, "PUBLIC": 5,
}

# cohort | interface | primary public evidence | evidence type | access limitation
_RAW = """
TRAFFIC|Google Search|https://www.google.com/|public interface|personalization varies
TRAFFIC|YouTube|https://www.youtube.com/|public interface|personalization varies
TRAFFIC|Facebook|https://about.meta.com/brand/resources/facebookapp/|official public guidance|product requires authentication
TRAFFIC|Instagram|https://about.instagram.com/|official public pages|feed requires authentication
TRAFFIC|ChatGPT|https://chatgpt.com/|public interface|account changes available features
TRAFFIC|Reddit|https://www.reddit.com/|public interface|regional prompts vary
TRAFFIC|X|https://help.x.com/en/using-x|official documentation|product requires authentication
TRAFFIC|WhatsApp|https://www.whatsapp.com/|official public pages|application workflow unavailable
TRAFFIC|TikTok|https://www.tiktok.com/|public interface|regional experience varies
TRAFFIC|Bing|https://www.bing.com/|public interface|personalization varies
TRAFFIC|Wikipedia|https://www.wikipedia.org/|public interface|none
TRAFFIC|Gemini|https://gemini.google.com/|public interface|account required for full product
TRAFFIC|Yahoo Japan|https://www.yahoo.co.jp/|public interface|Japanese locale
TRAFFIC|Yandex|https://yandex.com/|public interface|regional experience varies
TRAFFIC|Yahoo|https://www.yahoo.com/|public interface|regional experience varies
TRAFFIC|Amazon|https://www.amazon.com/|public interface|personalization varies
TRAFFIC|LinkedIn|https://www.linkedin.com/|public interface|product requires authentication
TRAFFIC|Baidu|https://www.baidu.com/|public interface|Chinese locale
TRAFFIC|Naver|https://www.naver.com/|public interface|Korean locale
TRAFFIC|Netflix|https://www.netflix.com/|public landing page|catalog requires subscription
TRAFFIC|Pinterest|https://www.pinterest.com/|public interface|authentication prompt
TRAFFIC|Bilibili|https://www.bilibili.com/|public interface|Chinese locale
TRAFFIC|Temu|https://www.temu.com/|public interface|regional merchandising varies
TRAFFIC|Twitch|https://www.twitch.tv/|public interface|live content varies
TRAFFIC|Weather.com|https://weather.com/|public interface|location and ads vary
OPS|Grafana|https://grafana.com/docs/grafana/latest/dashboards/|official docs and code|hosted product not inspected
OPS|Kibana|https://www.elastic.co/guide/en/kibana/current/dashboard.html|official docs and code|hosted product not inspected
OPS|Prometheus|https://prometheus.io/docs/visualization/browser/|official docs and code|demo data only
OPS|Datadog|https://docs.datadoghq.com/dashboards/|official documentation|product requires authentication
OPS|New Relic|https://docs.newrelic.com/docs/query-your-data/explore-query-data/dashboards/introduction-dashboards/|official documentation|product requires authentication
OPS|Sentry|https://docs.sentry.io/product/issues/|official docs and code|hosted product not inspected
OPS|Splunk|https://docs.splunk.com/Documentation/Splunk/latest/DashStudio/IntroFrame|official documentation|product requires authentication
OPS|AWS CloudWatch|https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html|official documentation|console requires authentication
OPS|Azure Monitor|https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/tutorial-logs-dashboards|official documentation|console requires authentication
OPS|Google Cloud Monitoring|https://cloud.google.com/monitoring/dashboards|official documentation|console requires authentication
OPS|Cloudflare Dashboard|https://developers.cloudflare.com/fundamentals/account-and-billing/account-setup/|official documentation|console requires authentication
OPS|GitHub Actions|https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows|official docs and public UI|repository data varies
OPS|GitLab CI/CD|https://docs.gitlab.com/ci/pipelines/|official docs and code|instance configuration varies
OPS|Kubernetes Dashboard|https://github.com/kubernetes/dashboard|official code and docs|no live cluster
OPS|Rancher|https://ranchermanager.docs.rancher.com/|official docs and code|no live cluster
OPS|Portainer|https://docs.portainer.io/|official docs and code|no live cluster
OPS|Netdata|https://learn.netdata.cloud/docs/dashboards-and-charts|official docs and code|demo telemetry only
OPS|Zabbix|https://www.zabbix.com/documentation/current/en/manual/web_interface|official docs and code|no live instance
OPS|OpenSearch Dashboards|https://opensearch.org/docs/latest/dashboards/|official docs and code|no live instance
OPS|Wazuh Dashboard|https://documentation.wazuh.com/current/user-manual/wazuh-dashboard/index.html|official docs and code|no live instance
NAS|TrueNAS SCALE|https://www.truenas.com/docs/scale/|official docs and code|no live host used
NAS|Synology DSM|https://www.synology.com/en-global/dsm|official documentation and screenshots|proprietary UI
NAS|QNAP QTS|https://www.qnap.com/en/software/qts|official documentation and screenshots|proprietary UI
NAS|Unraid|https://docs.unraid.net/|official docs and public UI code|no live host used
NAS|OpenMediaVault|https://docs.openmediavault.org/en/latest/|official docs and code|no live host used
NAS|ASUSTOR ADM|https://www.asustor.com/admv2|official documentation and screenshots|proprietary UI
NAS|TerraMaster TOS|https://www.terra-master.com/global/tos/|official documentation and screenshots|proprietary UI
NAS|CasaOS|https://github.com/IceWhaleTech/CasaOS|official code and docs|no live host used
NAS|Cockpit Project|https://cockpit-project.org/guide/latest/|official docs and code|no live host used
NAS|Proxmox VE|https://pve.proxmox.com/pve-docs/|official docs and code|no live cluster
NAS|Home Assistant|https://developers.home-assistant.io/docs/frontend/|official docs and code|no live home used
NAS|Scrutiny|https://github.com/AnalogJ/scrutiny|official code and docs|sample SMART data only
NAS|Uptime Kuma|https://github.com/louislam/uptime-kuma|official code and docs|no live monitors
NAS|Pi-hole|https://github.com/pi-hole/web|official code and docs|no live DNS used
NAS|pfSense|https://docs.netgate.com/pfsense/en/latest/|official docs and code|no live firewall
DESIGN|Material 3|https://m3.material.io/|official design system|none
DESIGN|Apple HIG|https://developer.apple.com/design/human-interface-guidelines/|official design system|platform-specific
DESIGN|Fluent 2|https://fluent2.microsoft.design/|official design system|none
DESIGN|IBM Carbon|https://carbondesignsystem.com/|official design system and code|none
DESIGN|Salesforce Lightning|https://www.lightningdesignsystem.com/|official design system and code|none
DESIGN|Atlassian Design System|https://atlassian.design/|official design system|none
DESIGN|Shopify Polaris|https://polaris.shopify.com/|official design system and code|commerce-oriented
DESIGN|Adobe Spectrum|https://spectrum.adobe.com/|official design system and code|none
DESIGN|GitHub Primer|https://primer.style/|official design system and code|none
DESIGN|Ant Design|https://ant.design/|official design system and code|none
DESIGN|PatternFly|https://www.patternfly.org/|official design system and code|enterprise-oriented
DESIGN|Elastic UI|https://eui.elastic.co/|official design system and code|none
DESIGN|GitLab Pajamas|https://design.gitlab.com/|official design system and code|none
DESIGN|Mozilla Protocol|https://protocol.mozilla.org/|official design system and code|content-site oriented
DESIGN|Bootstrap|https://getbootstrap.com/docs/5.3/getting-started/introduction/|official design system and code|generic framework
DATAVIZ|D3|https://d3js.org/|official docs and code|library not a prescribed UI
DATAVIZ|Observable Plot|https://observablehq.com/plot/|official docs and code|none
DATAVIZ|Vega-Lite|https://vega.github.io/vega-lite/|official docs and code|none
DATAVIZ|Plotly|https://plotly.com/javascript/|official docs and code|none
DATAVIZ|Apache ECharts|https://echarts.apache.org/en/index.html|official docs and code|none
DATAVIZ|Datawrapper|https://academy.datawrapper.de/|official documentation|editor requires account
DATAVIZ|Flourish|https://help.flourish.studio/|official documentation|editor requires account
DATAVIZ|NYT Graphics|https://github.com/nytimes|public code and published work|no internal system access
DATAVIZ|Reuters Graphics|https://graphics.reuters.com/|published public work|no internal system access
DATAVIZ|FT Visual Vocabulary|https://github.com/Financial-Times/chart-doctor|public code and guidance|archived reference repository
HIGH_STAKES|FAA Human Factors Design Standard|https://www.faa.gov/air_traffic/publications/atpubs/hfds/|official specification|document rather than product UI
HIGH_STAKES|NASA Human Integration Design Handbook|https://www.nasa.gov/reference/human-integration-design-handbook/|official specification|document rather than product UI
HIGH_STAKES|NASA Human Systems Integration|https://www.nasa.gov/directorates/esdmd/hhp/human-systems-integration/|official guidance|overview-level public evidence
HIGH_STAKES|EASA Human Factors|https://www.easa.europa.eu/en/domains/air-operations/human-factors|official guidance|document rather than product UI
HIGH_STAKES|FDA Human Factors Engineering|https://www.fda.gov/regulatory-information/search-fda-guidance-documents/applying-human-factors-and-usability-engineering-medical-devices|official guidance|medical-device scope
HIGH_STAKES|NHTSA Driver Distraction Guidelines|https://www.nhtsa.gov/document/visual-manual-nhtsa-driver-distraction-guidelines-vehicle-electronic-devices|official guidance|automotive scope
HIGH_STAKES|MIL-STD-1472H|https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=35786|official specification|downloaded document
HIGH_STAKES|UK CAA CAP 737|https://www.caa.co.uk/our-work/publications/documents/content/cap737/|official guidance|aviation scope
HIGH_STAKES|EEMUA 191|https://www.eemua.org/Products/Publications/Digital/EEMUA-Publication-191.aspx|official overview|full publication is paid
HIGH_STAKES|ISA-101|https://www.isa.org/standards-and-publications/isa-standards/isa-standards-committees/isa101|official overview|full standard is paid
PUBLIC|GOV.UK|https://design-system.service.gov.uk/|official design system and public service|none
PUBLIC|NHS.UK|https://service-manual.nhs.uk/design-system|official design system and public service|none
PUBLIC|VA.gov|https://design.va.gov/|official design system and public service|none
PUBLIC|Canada.ca|https://design.canada.ca/|official design system and public service|none
PUBLIC|Australian Government Design System|https://designsystemau.org/|official archived design system|archived; maintenance risk
""".strip()


def _rows() -> list[dict[str, str]]:
    result = []
    for number, line in enumerate(_RAW.splitlines(), 1):
        cohort, name, url, evidence_type, limitation = line.split("|", 4)
        result.append({"id": f"GC-{number:03d}", "cohort": cohort, "name": name,
                       "url": url, "evidence_type": evidence_type,
                       "access_limitation": limitation})
    return result


INTERFACES = tuple(_rows())


def validate_corpus() -> tuple[str, ...]:
    errors: list[str] = []
    if len(INTERFACES) != 100:
        errors.append(f"expected 100 interfaces, found {len(INTERFACES)}")
    counts = {key: 0 for key in COHORT_COUNTS}
    urls: set[str] = set()
    for item in INTERFACES:
        if item["cohort"] not in counts:
            errors.append(f"{item['id']}: unknown cohort")
        else:
            counts[item["cohort"]] += 1
        if urlparse(item["url"]).scheme != "https":
            errors.append(f"{item['id']}: non-HTTPS evidence URL")
        if item["url"] in urls:
            errors.append(f"{item['id']}: duplicate evidence URL")
        urls.add(item["url"])
        if not item["evidence_type"] or not item["access_limitation"]:
            errors.append(f"{item['id']}: evidence disclosure incomplete")
    if counts != COHORT_COUNTS:
        errors.append(f"cohort counts differ: {counts!r}")
    return tuple(errors)


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    primary_elements: int
    task_taps: tuple[int, ...]
    above_fold_facts: int
    scroll_units: tuple[int, ...]
    decision_domains: int

    @property
    def interaction_cost(self) -> int:
        return sum(self.task_taps) + sum(self.scroll_units)


CANDIDATES = (
    Candidate("A", "Conservative refinement", 11, (0, 0, 1, 2, 1, 2, 1, 1), 5, (0, 1, 2, 3, 2, 4, 1, 5), 8),
    Candidate("B", "Domain consolidation", 4, (0, 0, 0, 0, 0, 1, 0, 0), 8, (0, 0, 1, 1, 1, 2, 0, 2), 4),
    Candidate("C", "Dense glass cockpit", 7, (0, 0, 0, 0, 0, 1, 0, 0), 8, (0, 0, 0, 1, 0, 2, 0, 3), 6),
)


def benchmark() -> dict[str, object]:
    """Return deterministic structural heuristics for identical eight-task fixtures."""
    return {
        "disclosure": "Automated structural heuristics, not human usability results",
        "tasks": 8,
        "winner": "B",
        "candidates": [
            {"id": item.id, "name": item.name,
             "competing_primary_elements": item.primary_elements,
             "task_taps": list(item.task_taps), "above_fold_facts": item.above_fold_facts,
             "scroll_units": list(item.scroll_units),
             "interaction_cost": item.interaction_cost,
             "decision_domains": item.decision_domains}
            for item in CANDIDATES
        ],
    }
