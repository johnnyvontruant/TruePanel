from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy-truenas.sh"


def test_restart_deploy_waits_for_mission_control_application_readiness():
    source = DEPLOY.read_text(encoding="utf-8")

    restart = source.index('"$DEPLOYED_ROOT/start-truepanel.sh"')
    wait = source.index("wait_for_mission_control")
    ready = source.index("TruePanel services restored and application-ready.")

    assert restart < wait < ready
    assert "/healthz" in source
    assert "TRUEPANEL_DEPLOY_HEALTH_TIMEOUT" in source
    assert "Mission Control ready after" in source


def test_readiness_probe_honors_configured_mission_control_port():
    source = DEPLOY.read_text(encoding="utf-8")

    assert "TRUEPANEL_MC_PORT" in source
    assert "mission_control_port" in source
    assert "http://127.0.0.1:${port}/healthz" in source
    assert "TRUEPANEL_DEPLOY_HEALTH_URL" in source


def test_readiness_probe_has_curl_and_python_fallbacks():
    source = DEPLOY.read_text(encoding="utf-8")

    assert "command -v curl" in source
    assert "command -v python3" in source
    assert "urllib.request.urlopen" in source
