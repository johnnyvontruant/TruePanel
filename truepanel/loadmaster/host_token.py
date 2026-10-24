"""Short-lived, single-use host Copy authorization tokens.

Tokens use a separately provisioned shared secret. No secret is generated
implicitly and missing commissioning credentials fail closed.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path


def read_secret(path: Path) -> bytes:
    st = path.stat()
    if not path.is_file() or st.st_uid != 0 or (st.st_mode & 0o077):
        raise ValueError("Host authorization key must be root-owned mode 0600")
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("Host authorization key is too short")
    return key


def payload(digest: str, uuid: str, serial: str, issued: int, nonce: str) -> bytes:
    return ("physical-copy-v1\n" + digest + "\n" + uuid + "\n" +
            serial + "\n" + str(issued) + "\n" + nonce).encode()


def issue(key: bytes, digest: str, uuid: str, serial: str,
          *, now: int | None = None) -> dict[str, object]:
    if len(key) < 32 or len(digest) != 64 or not uuid or not serial:
        raise ValueError("Incomplete authorization inputs")
    issued = int(time.time() if now is None else now)
    nonce = secrets.token_hex(24)
    mac = hmac.new(key, payload(digest, uuid, serial, issued, nonce), hashlib.sha256).hexdigest()
    return {"issued": issued, "nonce": nonce, "mac": mac}


class TokenVerifier:
    def __init__(self, key: bytes, *, ttl: int = 10):
        if len(key) < 32:
            raise ValueError("Authorization key too short")
        self.key = key
        self.ttl = ttl
        self.used: set[str] = set()

    def consume(self, digest: str, uuid: str, serial: str,
                token: dict, *, now: int | None = None) -> bool:
        try:
            current = int(time.time() if now is None else now)
            issued = token["issued"]
            nonce = token["nonce"]
            mac = token["mac"]
            if (type(issued) is not int or not isinstance(nonce, str)
                or len(nonce) != 48 or not isinstance(mac, str)
                or len(mac) != 64 or not (0 <= current - issued <= self.ttl)
                or nonce in self.used):
                return False
            expected = hmac.new(self.key, payload(digest, uuid, serial, issued, nonce),
                                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, expected):
                return False
            self.used.add(nonce)
            return True
        except (KeyError, TypeError, ValueError):
            return False


__all__ = ["TokenVerifier", "issue", "read_secret"]
