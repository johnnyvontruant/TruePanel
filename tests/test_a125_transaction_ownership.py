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


def test_stop_auto_display_consumes_its_own_nack():
    transport = FakeTransport(
        bytes([
            0x53, 0xFB, 0x28,
            0x53, 0x05, 0x00, 0x01,
        ])
    )
    controller = A125Controller(
        transport,
        timeout=0.05,
    )

    reply = controller.stop_auto_display_reply()

    assert reply.response == A125Response.NACK
    assert reply.payload == bytes([0x28])
    assert reply.hex() == "53 FB 28"

    # The next query must receive its own BUTTON_STATUS frame,
    # not the earlier STOP_AUTO_DISPLAY NACK.
    assert controller.query_buttons() == 0x0001

    assert transport.writes == [
        bytes([0x4D, 0x28]),
        bytes([0x4D, 0x06]),
    ]


def test_exchange_returns_encoded_command_and_reply():
    transport = FakeTransport(
        bytes([0x53, 0xFA])
    )
    controller = A125Controller(
        transport,
        timeout=0.05,
    )

    encoded, reply = controller.exchange(
        bytes([0x4D, 0x0D])
    )

    assert encoded == bytes([0x4D, 0x0D])
    assert reply.response == A125Response.ACK
    assert reply.payload == b""
