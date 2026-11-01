"""Fail-closed operator workflow for privacy-safe AEGIS field evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from truepanel.aegis.evidence_gate import evaluate_evidence_gate
from truepanel.history.black_box import BlackBoxRecorder
from truepanel.holodeck.aegis_corpus import (
    MAX_CORPUS_BYTES,
    MAX_CORPUS_CASES,
    builtin_corpus_path,
    load_corpus,
    run_black_box_corpus,
)

CONSENT_CONFIRMATION = "I CONSENT TO SANITIZED AEGIS CALIBRATION"
REVIEW_CONFIRMATION = "I REVIEWED THIS INCIDENT OUTCOME"
FREEZE_CONFIRMATION = "FREEZE THIS FIELD CORPUS"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n")


def _root(path: str | Path) -> Path:
    return Path(path).resolve()


def _load_session(root: Path) -> dict[str, Any]:
    session_path = root / "workflow.json"
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"no AEGIS field workflow at {root}") from error
    if session.get("schema_version") != 1:
        raise ValueError("unsupported AEGIS field workflow")
    return session


def _require_state(session: dict[str, Any], expected: str) -> None:
    if session.get("state") != expected:
        raise ValueError(
            f"field workflow is {session.get('state')!r}; expected {expected!r}"
        )


def initialize_field_workflow(
    path: str | Path,
    *,
    corpus_id: str,
    retention_policy: str,
    confirmation: str,
) -> dict[str, Any]:
    """Create an explicitly consented, identity-free collection workspace."""

    if confirmation != CONSENT_CONFIRMATION:
        raise ValueError("explicit field-evidence consent confirmation is required")
    if not _SAFE_ID.fullmatch(corpus_id):
        raise ValueError("corpus_id must be a safe lowercase identifier")
    if not retention_policy.strip():
        raise ValueError("retention_policy is required")
    root = _root(path)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"refusing to initialize non-empty workflow path: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "recordings").mkdir()
    session = {
        "schema_version": 1,
        "workflow_id": "aegis-field-corpus-workflow-v1",
        "corpus_id": corpus_id,
        "state": "collecting",
        "consent": {
            "authority": "operator-opt-in",
            "scope": "sanitized-aegis-calibration",
            "identity_recorded": False,
            "withdrawal_supported_before_freeze": True,
        },
        "dataset_card": {
            "collection_authority": "operator-opt-in",
            "review_state": "pending",
            "raw_identifiers_retained": False,
            "label_method": "human-reviewed-incident-outcome",
            "allowed_uses": ["aegis-calibration"],
            "retention_policy": retention_policy.strip(),
        },
        "cases": [],
        "control_authority": False,
        "live_capture": False,
    }
    _write_json(root / "workflow.json", session)
    return workflow_status(root)


def ingest_field_recording(
    path: str | Path,
    recording: str | Path,
    *,
    case_id: str,
    challenge: str,
    system_profile: str,
    workload_class: str,
    expected_shared_cooling: bool,
    first_isolated_threshold_index: int | None = None,
) -> dict[str, Any]:
    """Import one already-sanitized recording without touching its source."""

    root = _root(path)
    session = _load_session(root)
    _require_state(session, "collecting")
    if not _SAFE_ID.fullmatch(case_id):
        raise ValueError("case_id must be a safe lowercase identifier")
    if any(item["case_id"] == case_id for item in session["cases"]):
        raise ValueError(f"duplicate field case: {case_id}")
    if len(session["cases"]) >= MAX_CORPUS_CASES:
        raise ValueError("AEGIS corpus case limit exceeded")
    for label, value in (
        ("challenge", challenge),
        ("system_profile", system_profile),
        ("workload_class", workload_class),
    ):
        if not str(value).strip():
            raise ValueError(f"{label} is required")

    source = Path(recording).resolve()
    raw = source.read_bytes()
    existing_bytes = sum(int(item["byte_count"]) for item in session["cases"])
    if existing_bytes + len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("AEGIS corpus byte limit exceeded")
    replay = BlackBoxRecorder(source).load_replay()
    raw_records = [json.loads(line) for line in raw.decode().splitlines() if line]
    if raw_records != [frame.as_dict() for frame in replay.frames]:
        raise ValueError("recording is not sanitized at rest")

    relative = Path("recordings") / f"{case_id}.jsonl"
    destination = root / relative
    if destination.exists():
        raise ValueError(f"refusing to overwrite recording: {destination}")
    _atomic_write(destination, raw)
    case = {
        "case_id": case_id,
        "recording": relative.as_posix(),
        "sha256": _sha256(raw),
        "byte_count": len(raw),
        "frame_count": len(replay.frames),
        "expected_shared_cooling": bool(expected_shared_cooling),
        "challenge": str(challenge).strip(),
        "system_profile": str(system_profile).strip(),
        "workload_class": str(workload_class).strip(),
        "incident_reviewed": False,
    }
    if first_isolated_threshold_index is not None:
        case["first_isolated_threshold_index"] = int(
            first_isolated_threshold_index
        )
    session["cases"].append(case)
    _write_json(root / "workflow.json", session)
    return workflow_status(root)


def review_field_case(
    path: str | Path, *, case_id: str, confirmation: str
) -> dict[str, Any]:
    """Record a human outcome review without retaining reviewer identity."""

    if confirmation != REVIEW_CONFIRMATION:
        raise ValueError("explicit incident-outcome review confirmation is required")
    root = _root(path)
    session = _load_session(root)
    _require_state(session, "collecting")
    case = next(
        (item for item in session["cases"] if item["case_id"] == case_id), None
    )
    if case is None:
        raise ValueError(f"unknown field case: {case_id}")
    case["incident_reviewed"] = True
    _write_json(root / "workflow.json", session)
    return workflow_status(root)


def freeze_field_workflow(
    path: str | Path, *, confirmation: str
) -> dict[str, Any]:
    """Freeze reviewed evidence into the loader's content-addressed manifest."""

    if confirmation != FREEZE_CONFIRMATION:
        raise ValueError("explicit corpus freeze confirmation is required")
    root = _root(path)
    session = _load_session(root)
    _require_state(session, "collecting")
    if not session["cases"]:
        raise ValueError("cannot freeze an empty field corpus")
    unreviewed = [c["case_id"] for c in session["cases"] if not c["incident_reviewed"]]
    if unreviewed:
        raise ValueError(f"unreviewed field cases: {unreviewed}")
    manifest = {
        "schema_version": 1,
        "corpus_id": session["corpus_id"],
        "source": "operator-opt-in-field",
        "privacy": "sanitized",
        "dataset_card": {**session["dataset_card"], "review_state": "approved"},
        "cases": [
            {key: value for key, value in case.items() if key != "byte_count"}
            for case in session["cases"]
        ],
        "limitations": [
            "field admission is not production validation",
            "automated assessment cannot authorize control or deployment",
        ],
    }
    manifest["corpus_sha256"] = _sha256(_canonical(manifest))
    _write_json(root / "manifest.json", manifest)
    load_corpus(root)
    session["state"] = "frozen"
    session["manifest_sha256"] = manifest["corpus_sha256"]
    _write_json(root / "workflow.json", session)
    return workflow_status(root)


def assess_field_workflow(path: str | Path) -> dict[str, Any]:
    """Replay frozen evidence and preserve a fail-closed assessment receipt."""

    root = _root(path)
    session = _load_session(root)
    if session.get("state") not in {"frozen", "assessed"}:
        raise ValueError("field workflow must be frozen before assessment")
    manifest, _ = load_corpus(root)
    if manifest["corpus_sha256"] != session.get("manifest_sha256"):
        raise ValueError("frozen manifest no longer matches workflow receipt")
    report = run_black_box_corpus(root)
    gate = evaluate_evidence_gate(report, manifest)
    receipt = {
        "schema_version": 1,
        "receipt_id": "aegis-field-assessment-v1",
        "corpus_id": manifest["corpus_id"],
        "corpus_sha256": manifest["corpus_sha256"],
        "report_sha256": report["evidence_sha256"],
        "stage": gate["stage"],
        "eligible_for_field_validation": gate["eligible_for_field_validation"],
        "production_validated": False,
        "release_review_required": True,
        "gaps": gate["gaps"],
        "measurements": gate["measurements"],
        "simulation": True,
        "hardware_isolated": True,
        "control_authority": False,
    }
    receipt["receipt_sha256"] = _sha256(_canonical(receipt))
    _write_json(root / "assessment.json", receipt)
    session["state"] = "assessed"
    session["assessment_sha256"] = receipt["receipt_sha256"]
    _write_json(root / "workflow.json", session)
    return receipt


def workflow_status(path: str | Path) -> dict[str, Any]:
    """Return operator-safe progress without exposing source paths or identity."""

    root = _root(path)
    session = _load_session(root)
    reviewed = sum(bool(item["incident_reviewed"]) for item in session["cases"])
    return {
        "workflow_id": session["workflow_id"],
        "corpus_id": session["corpus_id"],
        "state": session["state"],
        "case_count": len(session["cases"]),
        "reviewed_case_count": reviewed,
        "remaining_reviews": len(session["cases"]) - reviewed,
        "consent_recorded": session["consent"]["authority"] == "operator-opt-in",
        "raw_identifiers_retained": False,
        "live_capture": False,
        "control_authority": False,
        "production_validated": False,
        "next_action": {
            "collecting": "import sanitized evidence and review every outcome",
            "frozen": "run deterministic assessment",
            "assessed": "review assessment gaps; release review remains mandatory",
        }[session["state"]],
    }


def run_field_workflow_smoke(path: str | Path) -> dict[str, Any]:
    """Exercise the complete workflow using packaged deterministic fixtures."""

    root = _root(path)
    initialize_field_workflow(
        root,
        corpus_id="aegis-field-workflow-smoke-v1",
        retention_policy="delete after deterministic smoke verification",
        confirmation=CONSENT_CONFIRMATION,
    )
    source_manifest, _ = load_corpus(builtin_corpus_path())
    for case in source_manifest["cases"]:
        ingest_field_recording(
            root,
            builtin_corpus_path() / case["recording"],
            case_id=case["case_id"],
            challenge=case["challenge"],
            system_profile="holodeck-qnap-six-bay",
            workload_class=case["challenge"],
            expected_shared_cooling=case["expected_shared_cooling"],
            first_isolated_threshold_index=case.get("first_isolated_threshold_index"),
        )
        review_field_case(
            root, case_id=case["case_id"], confirmation=REVIEW_CONFIRMATION
        )
    freeze_field_workflow(root, confirmation=FREEZE_CONFIRMATION)
    return assess_field_workflow(root)


__all__ = [
    "CONSENT_CONFIRMATION",
    "FREEZE_CONFIRMATION",
    "REVIEW_CONFIRMATION",
    "assess_field_workflow",
    "freeze_field_workflow",
    "ingest_field_recording",
    "initialize_field_workflow",
    "review_field_case",
    "run_field_workflow_smoke",
    "workflow_status",
]
