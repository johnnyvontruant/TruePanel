import socket

from truepanel.hardware.lcd_command import (
    LCDCommandClient,
    LCDCommandProcessor,
    LCDCommandServer,
)


def test_processor_accepts_enter():
    calls = []

    processor = LCDCommandProcessor(
        lambda mask, source: (
            calls.append(
                (mask, source)
            )
            or True
        )
    )

    response = processor.process(
        {
            "button": "enter",
            "source": "web",
        }
    )

    assert response["ok"] is True
    assert response["button_mask"] == 0x01
    assert calls == [
        (0x01, "web")
    ]


def test_processor_accepts_select():
    calls = []

    processor = LCDCommandProcessor(
        lambda mask, source: (
            calls.append(
                (mask, source)
            )
            or True
        )
    )

    response = processor.process(
        {
            "button": "select",
        }
    )

    assert response["ok"] is True
    assert response["button_mask"] == 0x02
    assert calls == [
        (0x02, "web")
    ]


def test_processor_rejects_unknown_button():
    processor = LCDCommandProcessor(
        lambda mask, source: True
    )

    response = processor.process(
        {
            "button": "launch",
        }
    )

    assert response["ok"] is False
    assert response["status"] == "unknown_button"


def test_processor_rejects_unknown_fields():
    processor = LCDCommandProcessor(
        lambda mask, source: True
    )

    response = processor.process(
        {
            "button": "enter",
            "raw_serial": "4d28",
        }
    )

    assert response["ok"] is False
    assert response["status"] == "invalid_request"


def test_processor_reports_unavailable_dispatcher():
    processor = LCDCommandProcessor(
        lambda mask, source: False
    )

    response = processor.process(
        {
            "button": "enter",
        }
    )

    assert response["ok"] is False
    assert (
        response["status"]
        == "dispatcher_unavailable"
    )


def test_client_server_round_trip(tmp_path):
    calls = []
    path = (
        tmp_path
        / "lcd-command.sock"
    )

    processor = LCDCommandProcessor(
        lambda mask, source: (
            calls.append(
                (mask, source)
            )
            or True
        )
    )
    server = LCDCommandServer(
        processor,
        path=path,
    )
    server.start()

    try:
        client = LCDCommandClient(
            path=path,
        )
        response = client.request(
            "select"
        )
    finally:
        server.stop()

    assert response["ok"] is True
    assert response["button"] == "select"
    assert calls == [
        (0x02, "web")
    ]
    assert not path.exists()
