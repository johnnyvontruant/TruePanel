"""
Response classification for Project Stargate protocol experiments.

This module classifies already-received A125 replies. It performs no serial
I/O and does not transmit commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from truepanel.diagnostics.protocol import (
    A125Reply,
    A125Response,
    describe_response,
)


class ResponseClassification(str, Enum):
    ACK = "ACK"
    NACK = "NACK"
    KNOWN_RESPONSE = "KNOWN_RESPONSE"
    UNKNOWN_RESPONSE = "UNKNOWN_RESPONSE"
    TIMEOUT = "TIMEOUT"
    INVALID_PACKET = "INVALID_PACKET"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"


@dataclass(frozen=True)
class ClassifiedResponse:
    classification: ResponseClassification
    response_code: int | None = None
    response_name: str = ""
    preamble: int | None = None
    payload: bytes = b""
    detail: str = ""

    @property
    def payload_hex(self) -> str:
        return self.payload.hex(" ").upper()

    def as_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification.value,
            "response_code": self.response_code,
            "response_code_hex": (
                f"0x{self.response_code:02X}"
                if self.response_code is not None
                else None
            ),
            "response_name": self.response_name,
            "preamble": self.preamble,
            "preamble_hex": (
                f"0x{self.preamble:02X}"
                if self.preamble is not None
                else None
            ),
            "payload_hex": self.payload_hex,
            "detail": self.detail,
        }


def classify_reply(reply: A125Reply) -> ClassifiedResponse:
    """Classify a decoded A125 reply."""

    response_code = int(reply.response)
    response_name = describe_response(response_code)

    if response_code == A125Response.ACK:
        classification = ResponseClassification.ACK
    elif response_code == A125Response.NACK:
        classification = ResponseClassification.NACK
    else:
        try:
            A125Response(response_code)
        except ValueError:
            classification = ResponseClassification.UNKNOWN_RESPONSE
        else:
            classification = ResponseClassification.KNOWN_RESPONSE

    return ClassifiedResponse(
        classification=classification,
        response_code=response_code,
        response_name=response_name,
        preamble=int(reply.preamble),
        payload=bytes(reply.payload),
    )


def classify_error(error: Exception) -> ClassifiedResponse:
    """Convert a protocol or transport exception into a structured result."""

    if isinstance(error, TimeoutError):
        classification = ResponseClassification.TIMEOUT
    elif isinstance(error, ValueError):
        classification = ResponseClassification.INVALID_PACKET
    else:
        classification = ResponseClassification.TRANSPORT_ERROR

    return ClassifiedResponse(
        classification=classification,
        detail=f"{type(error).__name__}: {error}",
    )
