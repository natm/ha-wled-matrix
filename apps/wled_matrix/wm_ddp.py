"""Send RGB frames to WLED (or any DDP receiver) over UDP port 4048."""

import socket
import struct

DDP_PORT = 4048
MAX_DATA = 1440  # bytes per packet: 480 RGB pixels, keeps packets under a normal MTU


class DdpSender:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0

    def send(self, host, pixels):
        """`pixels` is a list of (r, g, b) tuples for the whole display, in order."""
        data = bytes(v for px in pixels for v in px)
        self.seq = self.seq % 15 + 1
        for offset in range(0, len(data), MAX_DATA):
            chunk = data[offset:offset + MAX_DATA]
            last = offset + MAX_DATA >= len(data)
            # flags: version 1, push on the last packet; data type 0x0B = RGB, 8 bits each; destination 1 = display
            header = bytes([0x41 if last else 0x40, self.seq, 0x0B, 0x01]) + struct.pack("!IH", offset, len(chunk))
            self.sock.sendto(header + chunk, (host, DDP_PORT))
