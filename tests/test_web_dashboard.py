from pathlib import Path


def test_dashboard_contract():
    source = Path(
        "truepanel/web/static/index.html"
    ).read_text(encoding="utf-8")

    assert "TruePanel Mission Control" in source
    assert "/api/v1/status" in source
    assert "setInterval(refresh,5000)" in source
    assert "Hardware writes" in source
    assert "Read only" in source
