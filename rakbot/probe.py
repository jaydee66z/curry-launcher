"""Two bounded, credential-free UDP probes. No encrypted session is attempted."""

from dataclasses import asdict
import secrets
import socket
import struct
import time

from .protocol import MAGIC, ProtocolError, decode, encode_request1


def classify(data: bytes) -> dict:
    # Report protocol structure only, not raw peer data or arbitrary strings.
    if len(data) >= 35 and data[0] == 0x1C and data[17:33] == MAGIC:
        length = int.from_bytes(data[33:35], "big")
        if 35 + length == len(data):
            return {"kind": "raknet_unconnected_pong", "bytes": len(data)}
    try:
        packet = decode(data)
        result = {"kind": type(packet).__name__, "bytes": len(data)}
        # The decoder's results contain bounded numeric/address fields only.
        result["fields"] = asdict(packet)
        return result
    except ProtocolError:
        pass
    # This shape is from an external research sample. Matching it does not
    # establish which cipher or which transport the current server requires.
    if (len(data) >= 41 and data[:3] == b"\x01\0\0" and
            data[3] in (0x17, 0x1F) and data[4:7] == b"\x01\x11\x02" and
            len(data) >= data[3] + 18):
        return {"kind": "research_udmux_shape", "bytes": len(data),
                "header_bytes": data[3], "crypto_verified": False}
    return {"kind": "unrecognized", "bytes": len(data)}


def probe_endpoint(host: str, port: int, *, timeout: float = 2) -> dict:
    socket.inet_pton(socket.AF_INET, host)
    if not 1 <= port <= 65535 or not 0 < timeout <= 5:
        raise ValueError("Invalid probe port or timeout")
    timestamp = time.monotonic_ns() // 1_000_000
    ping = b"\x01" + struct.pack(">Q", timestamp) + MAGIC + struct.pack(">Q", secrets.randbits(64))
    results = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        for name, payload in (("unconnected_ping", ping),
                              ("open_request_1_version_0", encode_request1(0, 1200))):
            # Version 0 is a diagnostic value, not a claimed Roblox version.
            # A standard RakNet peer may advertise its version in a rejection.
            sock.send(payload)
            try:
                response = classify(sock.recv(65535))
            except TimeoutError:
                response = {"kind": "timeout"}
            except OSError:
                response = {"kind": "socket_error"}
            results.append({"request": name, "response": response})
    return {"endpoint": [host, port], "probes": results,
            "correlation_verified": False,
            "game_session": False,
            "note": "Responses observed during each receive window; no login or encryption verified."}
