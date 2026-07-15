"""
Tests for Stargate response classification and opcode safety policy.

Run with:

    PYTHONPATH=. python3 tests/test_lab_classifier.py
"""

from __future__ import annotations

from truepanel.diagnostics.protocol import (
    A125Reply,
    A125Response,
)
from truepanel.lab.classifier import (
    ResponseClassification,
    classify_error,
    classify_reply,
)
from truepanel.lab.survey import (
    OpcodeRisk,
    classify_opcode,
    validate_survey_opcodes,
)


def test_ack_classification():
    result = classify_reply(
        A125Reply(
            preamble=0x53,
            response=A125Response.ACK,
        )
    )

    assert result.classification == ResponseClassification.ACK
    assert result.response_name == "ACK"


def test_nack_classification():
    result = classify_reply(
        A125Reply(
            preamble=0x53,
            response=A125Response.NACK,
            payload=b"\x02",
        )
    )

    assert result.classification == ResponseClassification.NACK
    assert result.payload_hex == "02"


def test_known_response_classification():
    result = classify_reply(
        A125Reply(
            preamble=0x53,
            response=A125Response.BOARD_ID,
            payload=b"\x00\x7D",
        )
    )

    assert (
        result.classification
        == ResponseClassification.KNOWN_RESPONSE
    )
    assert result.response_name == "BOARD_ID"


def test_unknown_response_classification():
    result = classify_reply(
        A125Reply(
            preamble=0x53,
            response=0x42,
            payload=b"\x99",
        )
    )

    assert (
        result.classification
        == ResponseClassification.UNKNOWN_RESPONSE
    )
    assert result.response_name == "UNKNOWN_0x42"


def test_timeout_classification():
    result = classify_error(
        TimeoutError("simulated timeout")
    )

    assert result.classification == ResponseClassification.TIMEOUT


def test_opcode_policy():
    assert classify_opcode(0x00).risk == OpcodeRisk.SAFE_READ_ONLY
    assert classify_opcode(0x0C).risk == OpcodeRisk.DOCUMENTED_WRITE
    assert classify_opcode(0x10).risk == OpcodeRisk.EXPERIMENTAL_STATEFUL
    assert classify_opcode(0xFF).risk == OpcodeRisk.BLOCKED


def test_safe_validation():
    policies = validate_survey_opcodes(
        [0x00, 0x06, 0x07]
    )

    assert len(policies) == 3
    assert all(
        policy.permitted_by_default
        for policy in policies
    )


def test_experimental_requires_authorization():
    try:
        validate_survey_opcodes([0x10])
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Experimental opcode should require authorization"
        )


def test_blocked_opcode_cannot_be_authorized():
    try:
        validate_survey_opcodes(
            [0xFF],
            allow_experimental_read_only=True,
            allow_experimental_stateful=True,
            allow_documented_writes=True,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError(
            "Blocked opcode should never be permitted"
        )


def main():
    tests = [
        test_ack_classification,
        test_nack_classification,
        test_known_response_classification,
        test_unknown_response_classification,
        test_timeout_classification,
        test_opcode_policy,
        test_safe_validation,
        test_experimental_requires_authorization,
        test_blocked_opcode_cannot_be_authorized,
    ]

    for test in tests:
        test()
        print(f"PASS: {test.__name__}")

    print()
    print("Project Stargate Mission 3C.1: PASS")


if __name__ == "__main__":
    main()
