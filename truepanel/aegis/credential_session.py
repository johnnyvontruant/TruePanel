"""Credential-safe, fail-closed TrueNAS API session for passive evidence.

TrueNAS 25.10 requires API keys to travel over TLS. This adapter deliberately
supports only certificate-verified ``wss://`` connections and reads the key
from a private file descriptor. It exposes only TruePanel's passive method
allowlist after authentication.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .passive_providers import PASSIVE_METHODS

MAX_API_KEY_BYTES = 4096


def _safe_failure() -> RuntimeError:
    return RuntimeError("credential-safe TrueNAS session unavailable")


class PrivateApiKeyFile:
    """Read one API key without following links or publishing its contents."""

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

    def status(self) -> dict[str, Any]:
        reason = "API key file is private and owner-bound"
        secure = False
        try:
            metadata = self.path.lstat()
            secure = bool(
                self.path.is_absolute()
                and stat.S_ISREG(metadata.st_mode)
                and not stat.S_ISLNK(metadata.st_mode)
                and metadata.st_uid == self.expected_uid
                and metadata.st_mode & 0o077 == 0
                and 0 < metadata.st_size <= self.max_bytes
            )
        except OSError:
            metadata = None
        if not self.path.is_absolute():
            reason = "API key file path must be absolute"
        elif metadata is None:
            reason = "API key file is unavailable"
        elif stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            reason = "API key file must be a real regular file"
        elif metadata.st_uid != self.expected_uid:
            reason = "API key file owner does not match the runtime"
        elif metadata.st_mode & 0o077:
            reason = "API key file must not grant group or world access"
        elif not 0 < metadata.st_size <= self.max_bytes:
            reason = "API key file size is outside the allowed bound"
        return {
            "secure": secure,
            "reason": reason,
            "source": "private_file",
            "absolute_path": self.path.is_absolute(),
            "symlinks_allowed": False,
            "max_bytes": self.max_bytes,
        }

    def read(self) -> str:
        if self.status()["secure"] is not True:
            raise _safe_failure()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != self.expected_uid
                    or metadata.st_mode & 0o077
                    or not 0 < metadata.st_size <= self.max_bytes
                ):
                    raise _safe_failure()
                raw = handle.read(self.max_bytes + 1)
        except OSError:
            raise _safe_failure() from None
        try:
            value = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise _safe_failure() from None
        if (
            not value
            or len(value.encode("utf-8")) > self.max_bytes
            or any(character.isspace() for character in value)
            or any(ord(character) < 0x20 for character in value)
        ):
            raise _safe_failure()
        return value


def validate_api_uri(uri: str) -> str:
    """Accept only a credential-safe TrueNAS JSON-RPC WebSocket endpoint."""

    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError as error:
        raise ValueError("invalid TrueNAS API URI") from error
    if (
        parsed.scheme != "wss"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/current"
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError(
            "TrueNAS API URI must be wss://HOST[:PORT]/api/current without credentials"
        )
    return uri


def _default_client_factory(**kwargs: Any) -> Any:
    try:
        from truenas_api_client import Client
    except ImportError:
        raise _safe_failure() from None
    return Client(**kwargs)


class CredentialSafeTrueNASClient:
    """Persistent authenticated client exposing passive methods only."""

    def __init__(
        self,
        uri: str,
        api_key_file: Path | str,
        *,
        client_factory: Callable[..., Any] | None = None,
        expected_uid: int | None = None,
        call_timeout: float = 10.0,
    ) -> None:
        if not 1 <= call_timeout <= 30:
            raise ValueError("API call timeout must be between 1 and 30 seconds")
        self.uri = validate_api_uri(uri)
        self.key_file = PrivateApiKeyFile(
            api_key_file,
            expected_uid=expected_uid,
        )
        self.client_factory = client_factory or _default_client_factory
        self.call_timeout = float(call_timeout)
        self._client: Any | None = None
        self._authenticated = False
        self._connection_attempts = 0

    def status(self) -> dict[str, Any]:
        return {
            "transport": "wss",
            "tls_certificate_verification": True,
            "authentication": "api_key_over_verified_tls",
            "credential": self.key_file.status(),
            "persistent_session": True,
            "connected": self._client is not None,
            "authenticated": self._authenticated,
            "connection_attempts": self._connection_attempts,
            "read_only": True,
            "control_authority": False,
        }

    def _connect(self) -> None:
        if self._authenticated and self._client is not None:
            return
        self._connection_attempts += 1
        secret: str | None = None
        client: Any | None = None
        try:
            secret = self.key_file.read()
            client = self.client_factory(
                uri=self.uri,
                verify_ssl=True,
                py_exceptions=False,
                call_timeout=self.call_timeout,
            )
            authenticated = client.call("auth.login_with_api_key", secret)
            if authenticated is not True:
                raise _safe_failure()
        except Exception:
            if client is not None:
                with suppress(Exception):
                    client.close()
            raise _safe_failure() from None
        finally:
            secret = None
        self._client = client
        self._authenticated = True

    def call(self, method: str, *arguments: Any) -> Any:
        if method not in PASSIVE_METHODS:
            raise ValueError(f"TrueNAS method is not passive allowlisted: {method}")
        self._connect()
        try:
            return self._client.call(method, *arguments)
        except Exception:
            self.close()
            raise _safe_failure() from None

    def close(self) -> None:
        client, self._client = self._client, None
        self._authenticated = False
        if client is not None:
            with suppress(Exception):
                client.close()

    def __enter__(self) -> CredentialSafeTrueNASClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


__all__ = [
    "CredentialSafeTrueNASClient",
    "MAX_API_KEY_BYTES",
    "PrivateApiKeyFile",
    "validate_api_uri",
]
