import json

import pytest

from truepanel.guidance import (
    HOLODECK_MISSION_GUIDANCE,
    guidance_codes,
    guidance_for,
    guidance_for_mission,
    guidance_payload,
)
from truepanel.holodeck.missions import mission_names


def test_every_holodeck_mission_has_operator_guidance():
    assert set(mission_names()) == set(HOLODECK_MISSION_GUIDANCE)
    for mission in mission_names():
        assert guidance_for_mission(mission)


def test_guidance_entries_have_complete_recovery_arc():
    for code in guidance_codes():
        item = guidance_for(code)
        assert item.code == code
        assert item.title
        assert item.summary
        assert item.evidence_fields
        assert item.immediate_actions
        assert item.diagnosis
        assert item.remediation
        assert item.verification
        assert item.escalation


def test_destructive_steps_are_explicitly_marked():
    destructive = [
        step
        for code in guidance_codes()
        for step in guidance_for(code).remediation
        if step.risk == "destructive"
    ]
    assert destructive
    assert all(step.destructive is True for step in destructive)


def test_storage_replacement_guidance_uses_authoritative_sources():
    item = guidance_for("storage.disk_faulted")
    authorities = {source.authority for source in item.sources}
    assert "TrueNAS" in authorities
    assert "QNAP" in authorities
    assert any("pool.replace" in source.url for source in item.sources)


def test_model_specific_guidance_has_hardware_source():
    for code in guidance_codes():
        item = guidance_for(code)
        if not item.model_specific:
            continue
        assert any(source.authority == "QNAP" for source in item.sources)


def test_guidance_payload_is_json_serializable():
    payload = guidance_payload("storage.disk_faulted")
    encoded = json.dumps(payload, sort_keys=True)
    assert "storage.disk_faulted" in encoded
    assert "verification" in payload
    assert "sources" in payload


def test_unknown_guidance_code_is_actionable():
    with pytest.raises(ValueError, match="available"):
        guidance_for("storage.warp_core_breach")


def test_unknown_mission_guidance_is_actionable():
    with pytest.raises(ValueError, match="available"):
        guidance_for_mission("kobayashi-maru")
