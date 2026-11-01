"""Versioned, privacy-safe Black Box calibration for AEGIS correlation."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from truepanel.aegis.correlation import correlate_incident
from truepanel.aegis.evidence_gate import validate_field_manifest
from truepanel.history.black_box import BlackBoxRecorder
from truepanel.oracle import OracleEngine

CORPUS_ID = "aegis-black-box-corpus-v1"
EXPECTED_INCIDENT = "aegis:shared-cooling"
REQUIRED_CHALLENGES = frozenset(
    {
        "shared-cause-positive",
        "ambient-shift",
        "workload-shift",
        "transient-sensor-error",
        "telemetry-dropout",
        "sensor-noise",
    }
)
MAX_CORPUS_CASES = 64
MAX_CORPUS_BYTES = 16 * 1024 * 1024


class IncidentDetector(Protocol):
    """Replaceable detector boundary used only by deterministic evaluation."""

    detector_id: str

    def detect(self, outlook: Mapping[str, Any]) -> dict[str, Any] | None: ...


class PolicyIncidentDetector:
    """Adapter from the built-in correlation policy to the benchmark boundary."""

    detector_id = "aegis-declarative-correlation-v1"

    def detect(self, outlook: Mapping[str, Any]) -> dict[str, Any] | None:
        return correlate_incident([], outlook)


def builtin_corpus_path() -> Path:
    """Return the repository's immutable built-in corpus directory."""

    return Path(__file__).resolve().parent / "corpus" / "v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_corpus(
    path: str | Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load and validate a bounded, content-addressed Black Box corpus."""

    root = Path(path or builtin_corpus_path()).resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported AEGIS corpus manifest")
    source = manifest.get("source")
    if source == "deterministic-synthetic":
        if manifest.get("corpus_id") != CORPUS_ID:
            raise ValueError("unsupported built-in AEGIS corpus ID")
    elif source == "operator-opt-in-field":
        admission_errors = validate_field_manifest(manifest)
        if admission_errors:
            raise ValueError(
                f"AEGIS field corpus admission failed: {list(admission_errors)}"
            )
    else:
        raise ValueError("unsupported AEGIS corpus provenance")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CORPUS_CASES:
        raise ValueError("AEGIS corpus case count is invalid")
    if manifest.get("privacy") != "sanitized":
        raise ValueError("AEGIS corpus must declare sanitized provenance")

    manifest_without_digest = dict(manifest)
    declared_digest = manifest_without_digest.pop("corpus_sha256", None)
    if declared_digest != _sha256(_canonical(manifest_without_digest)):
        raise ValueError("AEGIS corpus manifest digest mismatch")

    loaded = []
    seen_ids: set[str] = set()
    total_bytes = 0
    for case in cases:
        case_id = str(case.get("case_id", ""))
        relative = Path(str(case.get("recording", "")))
        recording = (root / relative).resolve()
        if not case_id or case_id in seen_ids:
            raise ValueError("AEGIS corpus case IDs must be present and unique")
        if root not in recording.parents or relative.is_absolute():
            raise ValueError(f"{case_id}: recording escapes the corpus root")
        seen_ids.add(case_id)
        raw = recording.read_bytes()
        total_bytes += len(raw)
        if total_bytes > MAX_CORPUS_BYTES:
            raise ValueError("AEGIS corpus byte limit exceeded")
        if _sha256(raw) != case.get("sha256"):
            raise ValueError(f"{case_id}: recording digest mismatch")

        replay = BlackBoxRecorder(recording).load_replay()
        frames = replay.frames
        if len(frames) != case.get("frame_count"):
            raise ValueError(f"{case_id}: frame count mismatch")

        # BlackBoxFrame.from_dict sanitizes defensively.  A committed fixture
        # must already be safe at rest, not merely become safe while loading.
        raw_records = [
            json.loads(line) for line in raw.decode("utf-8").splitlines() if line
        ]
        if raw_records != [frame.as_dict() for frame in frames]:
            raise ValueError(f"{case_id}: recording was not sanitized at rest")
        loaded.append({"label": case, "frames": frames})

    if source == "deterministic-synthetic":
        challenges = {str(item["label"].get("challenge", "")) for item in loaded}
        missing = REQUIRED_CHALLENGES - challenges
        if missing:
            raise ValueError(
                f"AEGIS corpus challenge coverage missing: {sorted(missing)}"
            )
    return manifest, loaded


def validate_builtin_corpus() -> tuple[str, ...]:
    """Return CI-friendly validation errors for the built-in corpus."""

    try:
        load_corpus()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return (str(error),)
    return ()


def run_black_box_corpus(
    path: str | Path | None = None,
    *,
    detector_factory: Callable[[], IncidentDetector] = PolicyIncidentDetector,
) -> dict[str, Any]:
    """Replay the corpus through ORACLE and the real AEGIS policy."""

    manifest, cases = load_corpus(path)
    results = []
    tp = fp = tn = fn = negative_frames = false_positive_frames = 0
    detector_ids = set()
    for item in cases:
        label = item["label"]
        oracle = OracleEngine()
        detector = detector_factory()
        detector_ids.add(detector.detector_id)
        incident_frames: list[int] = []
        confidences: list[float] = []
        for index, frame in enumerate(item["frames"]):
            telemetry = frame.telemetry
            outlook = oracle.observe(
                timestamp=frame.captured_at,
                metrics=telemetry.get("metrics", {}),
                hard_faults=tuple(telemetry.get("hard_faults", ())),
            )
            incident = detector.detect(outlook)
            if incident and incident.get("incident_id") == EXPECTED_INCIDENT:
                incident_frames.append(index)
                confidences.append(float(incident["confidence"]))

        expected = bool(label.get("expected_shared_cooling"))
        predicted = bool(incident_frames)
        if expected and predicted:
            tp += 1
        elif expected:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
        if not expected:
            negative_frames += len(item["frames"])
            false_positive_frames += len(incident_frames)

        first_match = incident_frames[0] if incident_frames else None
        threshold = label.get("first_isolated_threshold_index")
        post_detection = (
            len(item["frames"]) - first_match if first_match is not None else 0
        )
        stability = len(incident_frames) / post_detection if post_detection else 0.0
        result = {
            "case_id": label["case_id"],
            "challenge": label["challenge"],
            "expected_shared_cooling": expected,
            "first_policy_match_index": first_match,
            "first_isolated_threshold_index": threshold,
            "lead_samples": (
                threshold - first_match
                if first_match is not None and isinstance(threshold, int)
                else None
            ),
            "incident_frame_count": len(incident_frames),
            "root_cause_stability": round(stability, 3),
            "confidence_mean": round(statistics.mean(confidences), 3)
            if confidences
            else None,
            "confidence_pstdev": (
                round(statistics.pstdev(confidences), 3) if confidences else None
            ),
            "passed": predicted is expected,
        }
        results.append(result)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    report = {
        "schema_version": 1,
        "detector_id": detector_ids.pop() if len(detector_ids) == 1 else "mixed",
        "corpus_id": manifest["corpus_id"],
        "corpus_sha256": manifest["corpus_sha256"],
        "source": manifest["source"],
        "privacy": manifest["privacy"],
        "simulation": True,
        "hardware_isolated": True,
        "production_mutation": False,
        "corpus_size": len(results),
        "frame_count": sum(len(item["frames"]) for item in cases),
        "confusion_matrix": {
            "true_positive": tp,
            "false_positive": fp,
            "true_negative": tn,
            "false_negative": fn,
        },
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "specificity": round(specificity, 3),
        "negative_frame_false_positive_rate": round(
            false_positive_frames / negative_frames if negative_frames else 0.0, 6
        ),
        "negative_frame_count": negative_frames,
        "false_positive_frame_count": false_positive_frames,
        "results": results,
        "limitations": list(manifest.get("limitations", ())),
    }
    report["evidence_sha256"] = _sha256(_canonical(report))
    return report


__all__ = [
    "CORPUS_ID",
    "IncidentDetector",
    "PolicyIncidentDetector",
    "builtin_corpus_path",
    "load_corpus",
    "run_black_box_corpus",
    "validate_builtin_corpus",
]
