"""Credential-safe TrueNAS WebSocket transport for passive AEGIS evidence."""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .passive_providers import PASSIVE_METHODS

MAX_API_KEY_BYTES = 4096
MAX_TLS_CA_BYTES = 64 * 1024
TRANSPORT_BOOTSTRAP_METHODS = ("core.set_options", "auth.login_ex")


def _text(value: Any) -> str:
    return str(value or "").strip()


class GovernedAPIKeyFile:
    """Read one API key from a tightly governed local file without exposing it."""

    def __init__(
        self,
        path: Path | str,
        *,
        expected_uid: int | None = None,
        max_bytes: int = MAX_API_KEY_BYTES,
    ) -> None:
        self.path = Path(path)
        self.expected_uid = os.geteuid() if expected_uid is None else expected_uid
        self.max_bytes = max_bytes

    def _governance(self) -> tuple[bool, str]:
        try:
            metadata = self.path.lstat()
        except OSError:
            return False, "API-key file is unavailable"
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return False, "API-key source must be a real regular file"
        if metadata.st_uid != self.expected_uid:
            return False, "API-key file owner does not match the runtime"
        if metadata.st_mode & 0o077:
            return False, "API-key file must not grant group or world permissions"
        if metadata.st_size <= 0 or metadata.st_size > self.max_bytes:
            return False, "API-key file size is outside the governed bound"
        return True, "API-key file ownership, mode, and size are governed"

    def status(self) -> dict[str, Any]:
        governed, reason = self._governance()
        return {
            "governed": governed,
            "reason": reason,
            "source": "owner_mode_governed_file",
            "max_bytes": self.max_bytes,
            "symlinks_allowed": False,
            "group_world_access_allowed": False,
            "secret_in_argv_allowed": False,
            "path_published": False,
        }

    def load(self) -> str | None:
        governed, _reason = self._governance()
        if not governed:
            return None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != self.expected_uid
                    or metadata.st_mode & 0o077
                    or metadata.st_size <= 0
                    or metadata.st_size > self.max_bytes
                ):
                    return None
                raw = handle.read(self.max_bytes + 1)
        except OSError:
            return None
        if not raw or len(raw) > self.max_bytes:
            return None
        try:
            key = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
        if not 32 <= len(key) <= 512 or any(character.isspace() for character in key):
            return None
        return key


class GovernedTLSCAFile:
    """Admit one local PEM trust file without changing the system trust store."""

    def __init__(
        self,
        path: Path | str,
        *,
        expected_uid: int | None = None,
        max_bytes: int = MAX_TLS_CA_BYTES,
    ) -> None:
        self.path = Path(path)
        self.expected_uid = os.geteuid() if expected_uid is None else expected_uid
        self.max_bytes = max_bytes

    def _governance(self) -> tuple[bool, str]:
        try:
            metadata = self.path.lstat()
        except OSError:
            return False, "TLS CA file is unavailable"
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return False, "TLS CA source must be a real regular file"
        if metadata.st_uid != self.expected_uid:
            return False, "TLS CA file owner does not match the runtime"
        if metadata.st_mode & 0o022:
            return False, "TLS CA file must not be group- or world-writable"
        if metadata.st_size <= 0 or metadata.st_size > self.max_bytes:
            return False, "TLS CA file size is outside the governed bound"

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                confirmed = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(confirmed.st_mode)
                    or confirmed.st_uid != self.expected_uid
                    or confirmed.st_mode & 0o022
                    or confirmed.st_size != metadata.st_size
                ):
                    return False, "TLS CA file changed during validation"
                raw = handle.read(self.max_bytes + 1)
        except OSError:
            return False, "TLS CA file could not be read safely"

        if len(raw) > self.max_bytes:
            return False, "TLS CA file size is outside the governed bound"
        if b"PRIVATE KEY" in raw:
            return False, "TLS CA file must not contain private key material"
        if b"-----BEGIN CERTIFICATE-----" not in raw or b"-----END CERTIFICATE-----" not in raw:
            return False, "TLS CA file does not contain a PEM certificate"
        return True, "TLS CA ownership, mode, size, and PEM content are governed"

    def trust_path(self) -> Path | None:
        governed, _reason = self._governance()
        return self.path if governed else None

    def status(self) -> dict[str, Any]:
        governed, reason = self._governance()
        return {
            "governed": governed,
            "reason": reason,
            "source": "process_local_ca_file",
            "max_bytes": self.max_bytes,
            "symlinks_allowed": False,
            "group_world_write_allowed": False,
            "private_material_allowed": False,
            "system_trust_store_changed": False,
            "path_published": False,
        }


@contextmanager
def _process_local_tls_ca(path: Path | None):
    if path is None:
        yield
        return
    previous = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous


def _validate_uri(uri: str) -> str:
    normalized = _text(uri)
    parsed = urlsplit(normalized)
    if parsed.scheme != "wss":
        raise ValueError("passive WebSocket API-key transport requires wss://")
    if not parsed.hostname:
        raise ValueError("passive WebSocket URI requires a hostname")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in the WebSocket URI")
    if parsed.path != "/api/current":
        raise ValueError("passive WebSocket URI must target /api/current")
    if parsed.query or parsed.fragment:
        raise ValueError("passive WebSocket URI must not contain query or fragment data")
    return normalized


class TrueNASWebSocketReadOnlyClient:
    """Persistent authenticated client restricted to the passive method allowlist."""

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        api_key_file: Path | str,
        tls_ca_file: Path | str | None = None,
        client_factory: Any | None = None,
        expected_uid: int | None = None,
        call_timeout: float = 10.0,
    ) -> None:
        self.uri = _validate_uri(uri)
        self.username = _text(username)
        if not self.username or any(character.isspace() for character in self.username):
            raise ValueError("passive WebSocket username must be non-empty and whitespace-free")
        if not 1 <= call_timeout <= 30:
            raise ValueError("passive WebSocket call timeout must be between 1 and 30 seconds")
        self.call_timeout = float(call_timeout)
        self.api_key_file = GovernedAPIKeyFile(
            api_key_file,
            expected_uid=expected_uid,
        )
        self.tls_ca_file = (
            GovernedTLSCAFile(tls_ca_file, expected_uid=expected_uid)
            if tls_ca_file is not None
            else None
        )
        self._client_factory = client_factory
        self._client: Any | None = None
        self._connection_attempted = False
        self._authenticated = False

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        from truenas_api_client import Client

        return Client(**kwargs)

    def _connect(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._connection_attempted:
            return None
        self._connection_attempted = True
        api_key = self.api_key_file.load()
        if api_key is None:
            return None
        ca_path = None
        if self.tls_ca_file is not None:
            ca_path = self.tls_ca_file.trust_path()
            if ca_path is None:
                api_key = ""
                return None
        factory = self._client_factory or self._default_client_factory
        client: Any | None = None
        try:
            with _process_local_tls_ca(ca_path):
                client = factory(
                    uri=self.uri,
                    verify_ssl=True,
                    call_timeout=self.call_timeout,
                )
            response = client.call(
                "auth.login_ex",
                {
                    "mechanism": "API_KEY_PLAIN",
                    "username": self.username,
                    "api_key": api_key,
                    "login_options": {"user_info": False},
                },
            )
            if not isinstance(response, dict) or response.get("response_type") != "SUCCESS":
                self._close_client(client)
                return None
        except Exception:
            if client is not None:
                self._close_client(client)
            return None
        finally:
            api_key = ""
        self._client = client
        self._authenticated = True
        return client

    @staticmethod
    def _close_client(client: Any) -> None:
        with suppress(Exception):
            client.close()

    def call(self, method: str, *arguments: Any) -> Any:
        if method not in PASSIVE_METHODS:
            raise ValueError(f"TrueNAS method is not passive allowlisted: {method}")
        client = self._connect()
        if client is None:
            return None
        try:
            return client.call(method, *arguments)
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        tls_trust = (
            self.tls_ca_file.status()
            if self.tls_ca_file is not None
            else {
                "governed": True,
                "source": "system_default",
                "system_trust_store_changed": False,
                "path_published": False,
            }
        )
        return {
            "transport": "truenas_jsonrpc_websocket",
            "endpoint": "/api/current",
            "tls_required": True,
            "tls_verification": True,
            "tls_trust": tls_trust,
            "persistent_session": True,
            "authenticated": self._authenticated,
            "credential": self.api_key_file.status(),
            "transport_bootstrap": {
                "methods": list(TRANSPORT_BOOTSTRAP_METHODS),
                "core_set_options_scope": "connection_only",
                "persistent_configuration_changed": False,
            },
            "governed_evidence_methods": sorted(PASSIVE_METHODS),
            "username_published": False,
            "uri_published": False,
            "control_authority": False,
        }

    def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            self._close_client(client)

    def __enter__(self) -> TrueNASWebSocketReadOnlyClient:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


__all__ = [
    "GovernedAPIKeyFile",
    "GovernedTLSCAFile",
    "MAX_API_KEY_BYTES",
    "MAX_TLS_CA_BYTES",
    "TRANSPORT_BOOTSTRAP_METHODS",
    "TrueNASWebSocketReadOnlyClient",
]
