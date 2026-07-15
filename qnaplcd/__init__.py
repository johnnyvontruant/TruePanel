#
# QNAP LCD Display and Button Class
#
import serial
from threading import *

# Get ID       send=0x4d, 0x00  recv=0x53, 0x01, 0xXX, 0xYY 
# Get Button   send=0x4d, 0x06  recv=0x53, 0x05, 0xXX, 0xYY
# Get Protocol send=0x4d, 0x07  recv=0x53, 0x08, 0xXX, 0xYY
# Display Char send=0x4d, 0x0C
# Display Cls  send=0x4d, 0x0D
# Backlight    send=x04d, 0x5e, 0xXX  : on,x=0x01 off,x=0x00
# Negative ACK                  recv=0x53, 0xFB, 0xXX
# Reset        send=0x4d, 0xFF

class QnapLCD:
    def __init__(self, port='/dev/ttyS1', speed=1200, handler=None):
        self.port = port
        self.speed = speed

        self.lines = 2
        self.columns = 16

        try:
            self.connection = serial.Serial(self.port, self.speed, timeout=None)
        except serial.SerialException as se:
            self.connection = None
            print('error', se)

        if handler:
            self.handler = handler
            self.reader = Thread(target=self.serial_reader)
            self.reader.start()

    def _read_bytes(self, bytes=1):
        if self.connection:
            data = self.connection.read(bytes)
            if bytes == 1:
                return data[0]

            return data

        return None

    def serial_reader(self):
        while True:
            preamble = self._read_bytes()
            if preamble == 0x53 or preamble == 0x83:
                cmd =  self._read_bytes()
                if cmd == 0x01:
                    report = self._read_bytes(2)
                    report = report[0] * 256 + report[1]
                    self.handler('Report_ID', report)

                if cmd == 0x05:
                    buttons = self._read_bytes(2)
                    buttons = buttons[0]*256 + buttons[1]
                    self.handler('Switch_Status', buttons)

                if cmd == 0x08:
                    version = self._read_bytes(2)
                    version = version[0]*256 + version[1]
                    self.handler('Protocol_Version', version)

                if cmd == 0xAA:
                    self.handler('Reset_OK', True)

                if cmd == 0xFA:
                    #self.buffer = sport.read()
                    self.handler('Ack', None)

                if cmd == 0xFB:
                    nack_cmd = self._read_bytes()
                    self.handler('Nack', nack_cmd)

    def backlight(self, on=True):
        if self.connection:
            if on:
                self.connection.write(bytes([0x4d, 0x5e, 0x01]))
            else:
                self.connection.write(bytes([0x4d, 0x5e, 0x00]))

    def clear(self):
        if self.connection:
            self.connection.write(bytes([0x4d, 0x0d]))

    def reset(self):
        if self.connection:
            self.connection.write(bytes([0x4d, 0xff]))

    def get_board(self):
        if self.connection:
            self.connection.write(bytes([0x4d, 0x00]))

    def get_protocol(self):
        if self.connection:
            self.connection.write(bytes([0x4d, 0x07]))

    def get_buttons(self):
        if self.connection:
            self.connection.write(bytes([0x4d, 0x06]))

    def _row_address(self, line):
        # Preserve the existing driver convention:
        # logical line 1 -> row 0x00
        # logical line 2 -> row 0x01
        line %= 2
        return 0x00 if line else 0x01

    def write_bytes(self, line, payload):
        """
        Write raw character bytes to one LCD row.

        This supports LCD ROM byte values and custom-character slots without
        UTF-8 transforming the payload.
        """

        if isinstance(payload, bytearray):
            payload = bytes(payload)

        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes or bytearray")

        payload = payload[:self.columns]
        row = self._row_address(line)

        print(f'RAW LINE {line}: {payload!r}')

        if self.connection:
            self.connection.write(
                bytes([0x4d, 0x0c, row, len(payload)])
            )
            self.connection.write(payload)
            self.connection.flush()

    def write_text(self, line, message):
        """
        Write conservative single-byte text.

        Latin-1 preserves byte values one-to-one. Unsupported characters are
        replaced instead of becoming multi-byte UTF-8 sequences.
        """

        message = str(message)[:self.columns]
        payload = message.encode("latin-1", errors="replace")
        self.write_bytes(line, payload)

    def write_frame(self, frame):
        """
        Write a two-row frame containing strings or raw byte payloads.
        """

        lines = getattr(frame, "lines", frame)

        if not isinstance(lines, (list, tuple)):
            raise TypeError("frame must provide two lines")

        first = lines[0] if len(lines) >= 1 else b""
        second = lines[1] if len(lines) >= 2 else b""

        for line_number, value in ((1, first), (2, second)):
            if isinstance(value, (bytes, bytearray)):
                self.write_bytes(line_number, value)
            else:
                self.write_text(line_number, value)

    def write(self, line, msg):
        """
        Backward-compatible text and two-line frame writer.
        """

        if isinstance(msg, list):
            self.write_frame(msg)
        elif isinstance(msg, (bytes, bytearray)):
            self.write_bytes(line, msg)
        else:
            self.write_text(line, msg)
