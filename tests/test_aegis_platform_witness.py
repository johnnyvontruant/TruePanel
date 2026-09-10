from __future__ import annotations

from copy import deepcopy

import pytest

from truepanel.aegis.passive_runtime import BoundedTrueNASQueryCache
from truepanel.aegis.platform_witness import (
    bind_platform_witness,
    issue_platform_witness,
    normalize_truenas_version,
    validate_platform_witness,
)
from truepanel.holodeck.aegis_platform_witness import (
    run_platform_witness_rehearsal,
)


class Client:
    def __init__(self, value="TrueNAS-SCALE-25.10.5"):
        self.value = value
        self.calls = []

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_version_normalizer_accepts_documented_shapes_only():
    assert normalize_truenas_version("TrueNAS-SCALE-25.10.5") == "25.10.5"
    assert normalize_truenas_version("25.10-RC.1") == "25.10-RC.1"
    assert normalize_truenas_version(" TrueNAS-SCALE-25.10.5") is None
    assert normalize_truenas_version({"version": "25.10.5"}) is None
    assert normalize_truenas_version("25.10.5\nsecret") is None


def test_witness_is_minimal_digest_bound_and_read_only():
    delegate = Client()
    cache = BoundedTrueNASQueryCache(delegate)
    witness = issue_platform_witness(cache, clock=lambda: 1234.0)

    assert witness["status"] == "VERIFIED"
    assert witness["truenas_version"] == "25.10.5"
    assert witness["sensitive_fields_retained"] is False
    assert witness["runtime_writes"] == 0
    assert witness["control_authority"] is False
    assert validate_platform_witness(witness) == ()
    assert delegate.calls == [("system.version", ())]


def test_binding_rejects_tampering_and_unapproved_fields():
    cache = BoundedTrueNASQueryCache(Client())
    witness = issue_platform_witness(cache, clock=lambda: 1234.0)
    tampered = deepcopy(witness)
    tampered["hostname"] = "private-host"

    assert "unapproved fields" in " ".join(validate_platform_witness(tampered))
    bound = bind_platform_witness(
        {"system": {"truenas_version": "forged"}},
        tampered,
    )
    assert "truenas_version" not in bound["system"]
    assert "hostname" not in bound["system"]["platform_witness"]


def test_passive_allowlist_blocks_every_non_witness_method():
    cache = BoundedTrueNASQueryCache(Client())
    with pytest.raises(ValueError, match="not passive allowlisted"):
        cache.call("system.info")
    with pytest.raises(ValueError, match="not passive allowlisted"):
        cache.call("system.shutdown")


def test_holodeck_rehearsal_has_no_false_current_paths():
    report = run_platform_witness_rehearsal()

    assert report["status_counts"] == {"CURRENT": 2, "REVIEW": 2, "HOLD": 3}
    assert report["measurements"]["fresh_calls_first_observation"] == 1
    assert report["measurements"]["fresh_calls_after_cached_observation"] == 1
    assert report["measurements"]["privacy_fields_retained"] == 0
    assert report["measurements"]["false_current_paths"] == 0
    assert report["runtime_writes"] == 0
    assert report["control_authority"] is False
