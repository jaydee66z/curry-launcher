"""Persistent recovered native transport. Application login is still incomplete."""

from collections import Counter
import math
import socket
import struct
import time

from .native_crypto import CryptoError
from .native_open import NativeOpen
from .protocol import encode_address
from .application import protocol_sync, network_metadata, player_metadata, authentication, string
from . import reliability as wire
from .schema import decode_schema_packet
from .player_probe import initial_player_record, marker_ack
from .players import PlayerRoster


# Native 0.744 client initializer, not an account password.
CONNECTION_PASSWORD = b"7O^\x11lE"


def milliseconds():
    return time.monotonic_ns() // 1_000_000


def connection_request(guid, timestamp):
    return b"\x09" + struct.pack(">QQ", guid, timestamp) + b"\0" + CONNECTION_PASSWORD


def connected_pong(ping, timestamp, unix_timestamp):
    # Native 0x102e3bdc6: echoed ping, monotonic milliseconds, Unix milliseconds.
    # All four kinds are sent unreliably. MTU probes 0x51..0x53 are unpadded.
    if len(ping) != 9 or ping[0] not in (0, 0x51, 0x52, 0x53):
        raise CryptoError("Unexpected connected ping layout.")
    return bytes([ping[0] + 3]) + ping[1:] + struct.pack(">QQ", timestamp, unix_timestamp)


def incoming_connection(accepted, endpoint):
    if len(accepted) != 104 or accepted[0] != 0x10:
        raise CryptoError("Unexpected ConnectionRequestAccepted layout.")
    internal = encode_address(("127.0.0.1", 0)) + encode_address(("0.0.0.0", 0)) * 9
    return (b"\x13" + encode_address(endpoint) + internal + accepted[-16:-8] +
            struct.pack(">QQ", milliseconds(), time.time_ns() // 1_000_000))


class NativeClient:
    def __init__(self, info, *, application_stage="transport", on_player=None):
        if application_stage not in ("transport", "metadata", "ticket"):
            raise CryptoError("Unknown application investigation stage.")
        self.application_stage = application_stage
        self.info = info
        self.open = NativeOpen.from_connection(info)
        self.assembler = wire.Assembler()
        self.sequence = self.reliable_index = self.order_index = 0
        self.split_id = 0
        self.pending = {}
        self.ack_timeout = None
        self.messages = Counter()
        self.message_sizes = {}
        self.transport_accepted = False
        self.offline_open_authenticated = False
        self.application_packets = 0
        self.pongs_sent = 0
        self.mtu = 1200
        self.resent = 0
        self.received_datagrams = 0
        self.received_bytes = 0
        self.last_received_at = time.monotonic()
        self.batch_acks = False
        self._pending_acks = set()
        self._ack_at = time.monotonic()
        self.ack_datagrams_sent = 0
        self.nack_datagrams_sent = 0
        self.datagram_loss = wire.DatagramLoss()
        self.shared_cache_snapshot = {}
        self.shared_cache_advertised = {}
        self.reason = "duration_elapsed"
        self.disconnect_code = None
        self.execution_request_received = False
        self.schema = None
        self.player_roster = None
        self.on_player = on_player
        self.own_player_record_received = False
        self.local_player_guid = None
        self.pending_markers = []
        self.markers_acked = 0
        self.message_events = []
        self._receiving_datagram = None
        self._started_at = time.monotonic()

    def _raw(self, plain):
        self.sock.send(self.open._prefix + self.open._session_cipher.encrypt(plain))

    def _flush_acks(self):
        if self._pending_acks:
            self._raw(wire.ack_many(self._pending_acks))
            self.ack_datagrams_sent += 1
            self._pending_acks.clear()
            self._ack_at = time.monotonic()

    def _queue_ack(self, sequence):
        if not self.batch_acks:
            self._raw(wire.ack(sequence))
            self.ack_datagrams_sent += 1
            return
        self._pending_acks.add(sequence)
        if len(self._pending_acks) >= 32 or time.monotonic() - self._ack_at >= 0.002:
            self._flush_acks()

    def _flush_nacks(self):
        if self.batch_acks:
            missing = self.datagram_loss.due(time.monotonic())
            if missing:
                self._raw(wire.nack_many(missing))
                self.nack_datagrams_sent += 1

    def _send(self, payload, reliability=2):
        chunks = [payload[n:n + 960] for n in range(0, len(payload), 960)]
        if not chunks or len(self.pending) + len(chunks) > 512:
            raise CryptoError("Reliable send window exceeded.")
        for index, chunk in enumerate(chunks):
            split = (self.split_id, len(chunks), index) if len(chunks) > 1 else None
            encoded = wire.frame(chunk, reliability=reliability, split=split,
                                 reliable_index=self.reliable_index, order_index=self.order_index)
            sequence = self.sequence
            self.sequence = (sequence + 1) & 0xffffff
            if reliability in (2, 3):
                self.reliable_index = (self.reliable_index + 1) & 0xffffff
                self.pending[sequence] = [encoded, time.monotonic(), 0, {sequence}]
            self._raw(wire.datagram(encoded, sequence))
        if len(chunks) > 1:
            self.split_id = (self.split_id + 1) & 65535
        if reliability == 3:
            self.order_index = (self.order_index + 1) & 0xffffff

    def _resend(self, sequence, now):
        record = self.pending.get(sequence)
        if record is None:
            return
        if record[2] >= getattr(self,'reliable_retry_limit',8):
            self.ack_timeout = {'datagram_sequence': sequence, 'attempts': record[2] + 1,
                                'pending_datagrams': len(self.pending)}
            raise CryptoError("Reliable packet acknowledgement timed out.")
        # Retransmit the same reliable frame inside a NEW datagram. Datagram
        # sequence numbers describe transmissions, not reliable messages.
        replacement = self.sequence
        self.sequence = (replacement + 1) & 0xffffff
        self._raw(wire.datagram(record[0], replacement))
        del self.pending[sequence]
        self.pending[replacement] = record
        record[3].add(replacement)
        record[1], record[2] = now, record[2] + 1
        self.resent += 1

    def _acknowledge(self, positive, ranges, now):
        for sequence, record in list(self.pending.items()):
            attempts = record[3] if positive else (sequence,)
            if any(first <= attempt <= last for attempt in attempts for first, last in ranges):
                if positive:
                    del self.pending[sequence]
                elif now - record[1] >= getattr(self,'nak_retry_floor',0.1):
                    self._resend(sequence, now)

    def _ack_markers(self):
        # The optional native Data subtype mapping maps canonical 2 to 46.
        # Decoding a real canonical NewInstance/Player/UserId establishes that
        # this session uses unmapped subtypes, including Marker item 4.
        if self.own_player_record_received:
            for packet in self.pending_markers:
                self._send(marker_ack(packet), 3)
                self.markers_acked += 1
            self.pending_markers.clear()

    def _message(self, payload):
        kind = payload[0]
        self.messages[f"0x{kind:02x}"] += 1
        self.message_sizes[f"0x{kind:02x}"] = len(payload)
        if (kind >= 0x80 or kind in (0x15, 0x16, 0x18)) and len(self.message_events) < 64:
            # Identifiers/timing only: never retain ticket, SessionId or script.
            self.message_events.append({"kind": f"0x{kind:02x}",
                                        "datagram_sequence": self._receiving_datagram,
                                        "elapsed_ms": round((time.monotonic() - self._started_at) * 1000, 2)})
        if kind == 0x10 and not self.transport_accepted:
            self._send(incoming_connection(payload, self.info.endpoints[0]), 3)
            self.transport_accepted = True
            if self.application_stage != "transport":
                from .shared_cache import CAPABILITY, advertisement
                if self.open._negotiated_capabilities & CAPABILITY and not self.open._negotiated_capabilities & (1 << 29):
                    packet = advertisement(self.shared_cache_snapshot)
                    if packet is not None:
                        self._send(packet, 3)
                        self.shared_cache_advertised = self.shared_cache_snapshot
                self._send(network_metadata(self.open._negotiated_capabilities,
                                             player_metadata(self.info)), 3)
                self._send(protocol_sync(), 3)
            if self.application_stage == "ticket":
                self._send(authentication(self.info), 3)
                self._send(b"\x8f" + string(""), 3)
        elif (kind in (0, 0x51, 0x52, 0x53) and
              (len(payload) == 9 or (kind == 0 and len(payload) == self.mtu - 40))):
            response = connected_pong(payload[:9], milliseconds(), time.time_ns() // 1_000_000)
            if kind == 0 and len(payload) != 9:
                response += bytes(len(payload) - len(response))
            self._send(response, 0)
            self.pongs_sent += 1
        elif kind in (0x15, 0x16, 0x18):
            if kind == 0x15 and len(payload) == 5:
                self.disconnect_code = int.from_bytes(payload[1:], "big")
            self.reason = {0x15: "peer_disconnected", 0x16: "connection_lost", 0x18: "invalid_protocol_password"}[kind]
            return False
        elif kind >= 0x80:
            self.application_packets += 1
            if kind == 0x97:
                if self.schema is not None:
                    raise CryptoError("Duplicate network schema is unsupported.")
                self.schema = decode_schema_packet(payload)
                self.player_roster = PlayerRoster(self.schema, self.info.account.user_id,
                                                  on_player=self.on_player)
            elif kind == 0x83 and self.schema is not None:
                if not self.own_player_record_received:
                    record = initial_player_record(payload, self.schema, self.info.account.user_id)
                    if record is not None and record["account_matches"]:
                        self.local_player_guid = record['wire_guid']
                        self.own_player_record_received = True
                        self._ack_markers()
                if self.player_roster is not None:
                    self._player_data(payload)
            elif kind == 0x84:
                marker_ack(payload)  # validate before retaining the bounded marker
                if len(self.pending_markers) >= 64:
                    raise CryptoError("Replication marker queue exceeded its bound.")
                self.pending_markers.append(payload)
                self._ack_markers()
            elif kind == 0x9b:
                if len(payload) < 13 or int.from_bytes(payload[9:13], "little") != len(payload) - 13:
                    raise CryptoError("Unsupported remote execution request layout.")
                # Retain only the fact of the request. Never execute server
                # bytecode in the host interpreter or expose its contents.
                self.execution_request_received = True
        return True

    def _player_data(self, payload):
        self.player_roster.push(payload)

    def _poll(self):
        """Process local input on the network thread. False requests clean exit."""
        return True

    def run(self, *, duration=15):
        if duration is not None and (not math.isfinite(duration) or not 1 <= duration <= 300):
            raise CryptoError("Duration must be finite and in 1..300 seconds.")
        started = time.monotonic()
        self._started_at = started
        deadline = started + duration if duration is not None else None
        scan_deadline = getattr(self, '_scan_deadline', None)
        if scan_deadline is not None:
            deadline = scan_deadline if deadline is None else min(deadline, scan_deadline)
        def receive(limit):
            remaining = limit if deadline is None else min(limit, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError('Game connection deadline elapsed.')
            self.sock.settimeout(remaining)
            return self.sock.recv(65535)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as self.sock:
            # Decoding a large JoinData block can briefly delay recv(). Keep
            # the arriving burst in the socket instead of losing fragments.
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF,
                                 (4 if self.batch_acks else 1) * 1024 * 1024)
            self.sock.settimeout(3)
            self.sock.connect(self.info.endpoints[0])
            probe_started = time.monotonic()
            self.sock.send(self.open.request1())
            rtt_limit = getattr(self, 'scan_rtt_limit', None)
            try:
                opening = receive(3 if rtt_limit is None else min(3, rtt_limit))
            except TimeoutError:
                if rtt_limit is None:
                    raise
                self.reason = 'server_latency_limit'
                return self.summary()
            open_rtt = time.monotonic() - probe_started
            milestones = getattr(self, 'scan_milestones', None)
            if isinstance(milestones, dict):
                milestones['open_rtt'] = round(open_rtt, 4)
            reply = self.open.inspect_reply1(opening)
            if reply["kind"] != "rbx_open_reply1":
                raise CryptoError("Native Request1 was not accepted.")
            self.sock.send(self.open.request(self.info.endpoints[0], mtu=reply["mtu"]))
            reply = self.open.inspect_reply(receive(3))
            if not reply.get("offline_open"):
                raise CryptoError("Native Request2 was not authenticated.")
            self.offline_open_authenticated = True
            self.mtu = reply['mtu']
            self._send(connection_request(self.open._guid, milliseconds()))
            self.sock.settimeout(0.1)
            active = True
            while active and (deadline is None or time.monotonic() < deadline):
                self._flush_nacks()
                if self._pending_acks and time.monotonic() - self._ack_at >= 0.002:
                    self._flush_acks()
                if not self._poll():
                    if self.reason == 'duration_elapsed':
                        self.reason = 'client_quit'
                    break
                now = time.monotonic()
                for sequence, record in list(self.pending.items()):
                    if now - record[1] >= min(2, 0.5 * 2**record[2]):
                        self._resend(sequence, now)
                if self.batch_acks:
                    # Wait at most the rest of the 2ms ACK window. Flushing on
                    # every temporary empty socket defeats batching at 1Gbps.
                    self.sock.settimeout(max(0.0001, 0.002 - (time.monotonic() - self._ack_at))
                                         if self._pending_acks else 0.1)
                try:
                    packet = self.sock.recv(65535)
                except TimeoutError:
                    self._flush_acks()
                    continue
                self.received_bytes += len(packet)
                plain = self.open.decrypt_session(packet)
                self.last_received_at = time.monotonic()
                self.received_datagrams += 1
                if plain and plain[0] & 0x60:
                    positive, ranges = wire.acknowledgements(plain)
                    self._acknowledge(positive, ranges, now)
                    continue
                sequence, frames = wire.decode(plain)
                if self.batch_acks:
                    self.datagram_loss.receive(sequence, self.last_received_at)
                self._receiving_datagram = sequence
                self._queue_ack(sequence)
                for item in frames:
                    for message in self.assembler.push(item):
                        if len(message) >= 8192:
                            self._flush_acks()  # Before potentially expensive application parsing.
                        if not self._message(message):
                            active = False
            self._flush_acks()
            # Reliable disconnect notification, best effort on this same socket.
            if active and self.transport_accepted:
                self._send(b"\x15", 3)
        return self.summary()

    def summary(self):
        """Credential-free snapshot, also usable after a bounded probe fails."""
        state = "application_login_pending" if self.transport_accepted else "transport_pending"
        if self.schema is not None:
            state = "replication_pending"
        if self.reason not in ("duration_elapsed", "client_quit", "scan_complete"):
            state = "application_rejected" if self.transport_accepted else "transport_rejected"
        return {"state": state, "application_stage": self.application_stage,
                **(self.player_roster.summary() if self.player_roster is not None else {
                    "players": [], "players_complete": False,
                    "players_scope": "No replication schema received.", "player_list_decode_stops": {}}),
                "offline_open_authenticated": self.offline_open_authenticated, "transport_accepted": self.transport_accepted,
                "game_session": False, "character_spawned": False, "movement_ready": False,
                "elapsed_seconds": round(time.monotonic() - self._started_at, 2), "stop_reason": self.reason,
                "disconnect_code": self.disconnect_code,
                "ack_timeout": self.ack_timeout,
                "remote_execution_request_received": self.execution_request_received,
                "schema_received": self.schema is not None,
                "own_player_record_received": self.own_player_record_received,
                "markers_acked": self.markers_acked,
                "schema": self.schema.summary() if self.schema is not None else None,
                "received_datagrams": self.received_datagrams, "retransmissions": self.resent,
                "received_bytes": self.received_bytes,
                "ack_datagrams_sent": self.ack_datagrams_sent,
                "nack_datagrams_sent": self.nack_datagrams_sent,
                "datagram_gaps_detected": self.datagram_loss.detected,
                "datagram_gaps_reported": self.datagram_loss.reported,
                "shared_cache_advertised": len(self.shared_cache_advertised),
                "pongs_sent": self.pongs_sent, "application_packets": self.application_packets,
                "message_counts": dict(self.messages), "last_message_sizes": self.message_sizes,
                "message_events": self.message_events,
                "note": ("Own Player record identified; character spawn and movement are not implemented."
                         if self.own_player_record_received else
                         "Player and character replication are not yet confirmed; movement is not implemented.")}
