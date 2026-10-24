"""Synthetic acceptance never grants authority on malformed or altered evidence."""
import hashlib
import json

from truepanel.loadmaster.synthetic_acceptance import (
    TEST_SHA256, TEST_FILE, accept_synthetic_preflight,
)


def fixture(tmp_path):
    nas = tmp_path / "mnt" / "SSDs" / "Applications" / "Loadmaster-V2-Lab" / "test"
    # The acceptance verifier intentionally rejects anything outside the
    # SSD test scope, including pytest temp folders.
    nas.mkdir(parents=True)
    test = nas / TEST_FILE
    test.write_bytes(b"test-data")
    receipt = tmp_path / "baseline.json"
    receipt.write_text(json.dumps({
        "kind": "truepanel.loadmaster_v2_synthetic_baseline",
        "schema_version": 1, "authorized": False,
        "cartridge": {"label": "Untitled", "uuid": "6ADA-80D5",
                      "serial": "2532EA8D421A",
                      "nas_path": str(nas), "usb_folder": "acceptance"},
        "files": [],
    }))
    status = {"available": True, "age": 0, "state": "READY",
              "drive": {"name": "Untitled", "uuid": "6ADA-80D5",
                        "serial": "2532EA8D421A", "nas_path": str(nas),
                        "usb_folder": "acceptance"},
              "plan": {"state": "READY", "first_sync": False,
                       "needs_confirmation": False, "digest": "a" * 64,
                       "summary": {"to_usb_files": 1, "to_usb_bytes": 65536},
                       "preview": [{"op": "to_usb", "path": TEST_FILE,
                                    "size": 65536}]}}
    return receipt, status


def test_rejects_any_non_acceptance_scope(tmp_path):
    receipt, status = fixture(tmp_path)
    assert accept_synthetic_preflight(receipt, status) is None


def test_rejects_missing_or_stale_receipt(tmp_path):
    receipt, status = fixture(tmp_path)
    assert accept_synthetic_preflight(tmp_path / "absent.json", status) is None
    status["age"] = 30
    assert accept_synthetic_preflight(receipt, status) is None


def test_rejects_changed_cartridge(tmp_path):
    receipt, status = fixture(tmp_path)
    status["drive"]["uuid"] = "OTHER"
    assert accept_synthetic_preflight(receipt, status) is None


def test_rejects_plan_with_ingestion(tmp_path):
    receipt, status = fixture(tmp_path)
    status["plan"]["summary"]["to_nas_files"] = 1
    assert accept_synthetic_preflight(receipt, status) is None
