"""Replaceable RFC 3161 verification adapter for AEGIS evidence timestamps."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from .ssh_verifier import OpenSshSignatureVerifier

MAX_TIMESTAMP_TOKEN_BYTES: Final = 128 * 1024
MAX_TRUST_ANCHOR_BYTES: Final = 256 * 1024
DEFAULT_POLICY_OID: Final = "1.3.6.1.4.1.55555.1"
_POLICY = re.compile(r"^Policy OID: (\S+)$", re.MULTILINE)
_TIME = re.compile(r"^Time stamp: (.+)$", re.MULTILINE)
_HASH = re.compile(r"^Hash Algorithm: (\S+)$", re.MULTILINE)


def _utc(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%b %d %H:%M:%S %Y GMT").replace(
        tzinfo=UTC
    )
    return parsed.isoformat().replace("+00:00", "Z")


class OpenSslRfc3161TimestampVerifier:
    """Verify a timestamp token over exact bytes using one protected CA bundle."""

    def __init__(
        self,
        trust_anchor_path: str | Path,
        *,
        expected_policy_oid: str = DEFAULT_POLICY_OID,
        expected_hash_algorithm: str = "sha256",
        token_is_content_info: bool = False,
        executable: str = "/usr/bin/openssl",
        timeout: float = 5.0,
    ) -> None:
        self.trust_anchor_path = Path(trust_anchor_path)
        self.expected_policy_oid = expected_policy_oid
        self.expected_hash_algorithm = expected_hash_algorithm.lower()
        self.token_is_content_info = bool(token_is_content_info)
        self.executable = executable
        self.timeout = float(timeout)

    def __call__(self, signed_value: bytes, token: bytes) -> dict[str, Any]:
        result: dict[str, Any] = {
            "verified": False,
            "profile": "RFC3161",
            "policy_oid": None,
            "gen_time_utc": None,
            "hash_algorithm": None,
            "errors": [],
        }
        descriptors: list[int] = []
        try:
            if (
                not isinstance(signed_value, bytes)
                or not signed_value
                or not isinstance(token, bytes)
                or not token
                or len(token) > MAX_TIMESTAMP_TOKEN_BYTES
                or not Path(self.executable).is_absolute()
                or not self.expected_policy_oid
                or self.expected_hash_algorithm not in {"sha256", "sha512"}
            ):
                raise ValueError("Rfc3161InputInvalid")
            anchor = OpenSshSignatureVerifier._snapshot(
                self.trust_anchor_path, maximum=MAX_TRUST_ANCHOR_BYTES
            )
            value_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-timestamped-signature", signed_value
            )
            token_fd = OpenSshSignatureVerifier._memfd("truepanel-rfc3161-token", token)
            anchor_fd = OpenSshSignatureVerifier._memfd(
                "truepanel-timestamp-root", anchor
            )
            descriptors.extend((value_fd, token_fd, anchor_fd))
            paths = {
                "value": f"/proc/self/fd/{value_fd}",
                "token": f"/proc/self/fd/{token_fd}",
                "anchor": f"/proc/self/fd/{anchor_fd}",
            }
            verify_command = [
                self.executable,
                "ts",
                "-verify",
                "-data",
                paths["value"],
                "-in",
                paths["token"],
                "-CAfile",
                paths["anchor"],
            ]
            if self.token_is_content_info:
                verify_command.append("-token_in")
            verified = subprocess.run(
                verify_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
                pass_fds=tuple(descriptors),
            )
            if verified.returncode != 0:
                raise ValueError("Rfc3161VerificationFailed")
            inspect_command = [
                self.executable,
                "ts",
                "-reply",
                "-in",
                paths["token"],
                "-text",
            ]
            if self.token_is_content_info:
                inspect_command.append("-token_in")
            inspected = subprocess.run(
                inspect_command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                pass_fds=tuple(descriptors),
            )
            if inspected.returncode != 0 or len(inspected.stdout) > 64 * 1024:
                raise ValueError("Rfc3161InspectionFailed")
            policy, generated, algorithm = (
                pattern.search(inspected.stdout) for pattern in (_POLICY, _TIME, _HASH)
            )
            if not policy or not generated or not algorithm:
                raise ValueError("Rfc3161ProfileInvalid")
            if policy.group(1) != self.expected_policy_oid:
                raise ValueError("Rfc3161PolicyMismatch")
            if algorithm.group(1).lower() != self.expected_hash_algorithm:
                raise ValueError("Rfc3161DigestPolicyMismatch")
            result.update(
                {
                    "verified": True,
                    "policy_oid": policy.group(1),
                    "gen_time_utc": _utc(generated.group(1)),
                    "hash_algorithm": algorithm.group(1).lower(),
                }
            )
        except (
            OSError,
            subprocess.SubprocessError,
            UnicodeError,
            ValueError,
        ) as error:
            result["errors"].append(str(error) or error.__class__.__name__)
        finally:
            for descriptor in descriptors:
                os.close(descriptor)
        return result


__all__ = [
    "DEFAULT_POLICY_OID",
    "MAX_TIMESTAMP_TOKEN_BYTES",
    "OpenSslRfc3161TimestampVerifier",
]
