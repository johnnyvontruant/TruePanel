#!/usr/bin/env python3
"""Generate a public RFC 4998 oracle fixture without retaining private keys."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import tempfile
from pathlib import Path

from truepanel.aegis.temperature_calibration_candidate_appraisal import _canonical
from truepanel.aegis.temperature_rfc4998_interop_fixture import (
    build_detached_evidence_record,
)
from truepanel.holodeck.aegis_temperature_reviewer_timestamp_witness import (
    _extract_timestamp_token,
    _issue,
    _tsa,
)
from truepanel.holodeck.aegis_temperature_revocation_hash_tree_renewal import (
    run_temperature_revocation_hash_tree_renewal_checkride,
)


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def build_fixture() -> dict[str, object]:
    predecessor = run_temperature_revocation_hash_tree_renewal_checkride()
    if predecessor["measurements"]["trusted_renewals"] != 1:
        raise RuntimeError("Rfc4998PredecessorRehearsalFailed")
    detached = hashlib.sha512(
        b"TRUEPANEL-RFC4998-DETACHED-ROOT-V1\x00"
        + _canonical(predecessor["measurements"])
    ).digest()
    with tempfile.TemporaryDirectory(prefix="truepanel-rfc4998-oracle-") as directory:
        root = Path(directory).resolve()
        trusted = root / "trusted"
        wrong = root / "wrong"
        trusted.mkdir()
        wrong.mkdir()
        _, config = _tsa(trusted, digest_algorithm="sha512")
        _tsa(wrong, digest_algorithm="sha512")
        data_path = root / "detached-root.bin"
        response_path = root / "response.tsr"
        token_path = root / "token.tst"
        data_path.write_bytes(detached)
        _issue(config, data_path, response_path, digest_algorithm="sha512")
        _extract_timestamp_token(response_path, token_path)
        record = build_detached_evidence_record(token_path.read_bytes())
        return {
            "schema": "truepanel.aegis-rfc4998-bouncycastle-fixture/v1",
            "profile": "RFC4998-SINGLE-DETACHED-OBJECT",
            "digest_algorithm": "sha512",
            "evidence_record_der_base64": _b64(record),
            "detached_data_base64": _b64(detached),
            "trusted_root_pem_base64": _b64((trusted / "tsa-ca.crt").read_bytes()),
            "wrong_root_pem_base64": _b64((wrong / "tsa-ca.crt").read_bytes()),
            "evidence_record_sha256": hashlib.sha256(record).hexdigest(),
            "detached_data_sha512": hashlib.sha512(detached).hexdigest(),
            "private_keys_retained": False,
            "production_trusted": False,
            "deployment_authority": False,
            "hardware_authority": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(build_fixture(), sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
