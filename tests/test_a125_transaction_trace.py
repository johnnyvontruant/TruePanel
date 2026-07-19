from truepanel.diagnostics.protocol import A125Response
from truepanel.hardware.a125 import A125Controller


class FakeTransport:
    def __init__(self, replies: bytes):
        self.replies = bytearray(replies)
        self.writes = []

    def write(self, data: bytes):
        self.writes.append(bytes(data))
        return len(data)

    def read(self, size: int) -> bytes:
        if not self.replies:
            return b""

        output = bytes(self.replies[:size])
        del self.replies[:size]
        return output

    def flush(self):
        return None


def test_button_query_records_complete_transaction():
    transport = FakeTransport(
        bytes([0x53, 0x05, 0x00, 0x01])
    )
    controller = A125Controller(
        transport,
        timeout=0.05,
    )

    assert controller.query_buttons() == 0x0001

    trace = controller.last_transaction

    assert trace is not None
    assert trace.command_name in {
        "GET_BUTTONS",
        "BUTTONS",
        "BUTTON_STATUS",
    }
    assert trace.response_name == "BUTTON_STATUS"
    assert trace.tx_hex == "4D 06"
    assert trace.rx_hex == "53 05 00 01"
    assert trace.classification == "EXPECTED"
    assert trace.expected_response == "BUTTON_STATUS"
    assert trace.latency_ms >= 0.0

    assert list(controller.transaction_history) == [trace]

    formatted = controller.format_last_transaction()
    assert "TX 4D 06" in formatted
    assert "RX 53 05 00 01" in formatted
    assert "EXPECTED" in formatted
    assert "BUTTON_STATUS" in formatted


def test_stop_auto_display_nack_has_its_own_trace():
    transport = FakeTransport(
        bytes([0x53, 0xFB, 0x28])
    )
    controller = A125Controller(
        transport,
        timeout=0.05,
    )

    reply = controller.stop_auto_display_reply()

    assert reply.response == A125Response.NACK

    trace = controller.last_transaction

    assert trace.tx_hex == "4D 28"
    assert trace.rx_hex == "53 FB 28"
    assert trace.classification == "NACK"
    assert trace.response_name == "NACK"
