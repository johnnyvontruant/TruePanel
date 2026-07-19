from truepanel.diagnostics.protocol import (
    A125Response,
    UnexpectedResponse,
    UnsupportedCommand,
)
from truepanel.hardware.a125 import A125Controller


class FakeTransport:
    def __init__(self, reply: bytes):
        self.reply = bytearray(reply)
        self.writes = []

    def write(self, data: bytes):
        self.writes.append(bytes(data))
        return len(data)

    def read(self, size: int) -> bytes:
        if not self.reply:
            return b""

        output = bytes(self.reply[:size])
        del self.reply[:size]
        return output

    def flush(self):
        return None


def test_button_query_preserves_nack_reason_and_raw_reply():
    transport = FakeTransport(bytes([0x53, 0xFB, 0x42]))
    controller = A125Controller(transport, timeout=0.05)

    try:
        controller.query_buttons()
    except UnsupportedCommand as error:
        assert error.expected_response == A125Response.BUTTON_STATUS
        assert error.reason == 0x42
        assert error.raw_reply == "53 FB 42"
        assert "reason=0x42" in str(error)
        assert "raw=53 FB 42" in str(error)
    else:
        raise AssertionError("Expected UnsupportedCommand")


def test_button_query_distinguishes_unexpected_valid_response():
    transport = FakeTransport(
        bytes([0x53, 0x01, 0x00, 0x7D])
    )
    controller = A125Controller(transport, timeout=0.05)

    try:
        controller.query_buttons()
    except UnexpectedResponse as error:
        assert error.expected_response == A125Response.BUTTON_STATUS
        assert error.actual_response == A125Response.BOARD_ID
        assert error.raw_reply == "53 01 00 7D"
        assert "BOARD_ID" in str(error)
    else:
        raise AssertionError("Expected UnexpectedResponse")


def test_successful_button_query_is_unchanged():
    transport = FakeTransport(
        bytes([0x53, 0x05, 0x00, 0x01])
    )
    controller = A125Controller(transport, timeout=0.05)

    assert controller.query_buttons() == 0x0001
    assert transport.writes == [bytes([0x4D, 0x06])]
