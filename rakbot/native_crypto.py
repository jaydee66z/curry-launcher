"""Statically recovered RakNet crypto primitives from MacPlayer 0.744.0.7441080.

This is a codec component, not a complete or live-validated Roblox handshake.
See research/REVERSE.md for native addresses and evidence boundaries.
"""

from dataclasses import dataclass, field
import hashlib
import os
import threading

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


COUNTER_BASE = int.from_bytes(b"UniqueNu", "little")


class CryptoError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class DirectionalKeys:
    receive: bytes = field(repr=False)
    transmit: bytes = field(repr=False)

    def __repr__(self):
        return "DirectionalKeys(<redacted>)"


@dataclass(frozen=True, repr=False)
class ClientKeyPair:
    secret: bytes = field(repr=False)
    public: bytes = field(repr=False)

    @classmethod
    def generate(cls):
        return cls.from_secret(os.urandom(32))

    @classmethod
    def from_secret(cls, secret: bytes):
        if len(secret) != 32:
            raise CryptoError("X25519 secret must be 32 bytes.")
        key = X25519PrivateKey.from_private_bytes(secret)
        return cls(secret, key.public_key().public_bytes_raw())

    def client_keys(self, server_public: bytes) -> DirectionalKeys:
        """libsodium crypto_kx_client_session_keys: BLAKE2b(q || cpk || spk)."""
        if len(server_public) != 32:
            raise CryptoError("X25519 public key must be 32 bytes.")
        try:
            shared = X25519PrivateKey.from_private_bytes(self.secret).exchange(
                X25519PublicKey.from_public_bytes(server_public))
        except ValueError:
            raise CryptoError("X25519 peer key is invalid.") from None
        output = hashlib.blake2b(shared + self.public + server_public, digest_size=64).digest()
        return DirectionalKeys(output[:32], output[32:])

    def __repr__(self):
        return "ClientKeyPair(<redacted>)"


def early_nonce(counter: int) -> bytes:
    if type(counter) is not int or not 0 <= counter < 2**64 - COUNTER_BASE:
        raise CryptoError("Early nonce counter is outside the supported range.")
    # The last byte is lowercase 'r'. Established packets use uppercase 'R'.
    return (COUNTER_BASE + counter).to_bytes(8, "little") + b"mber"


def established_nonce(counter: int) -> bytes:
    if type(counter) is not int or not 0 <= counter < 2**64:
        raise CryptoError("Established nonce counter must fit in uint64.")
    return counter.to_bytes(8, "little") + b"mbeR"


class EarlyCipher:
    """Native early format: AAD || ciphertext || explicit nonce[12] || tag[16].

    Create one instance per fresh client keypair/connection. The object advances
    its nonce counter before encryption, including failed encryption attempts.
    """

    def __init__(self, keys: DirectionalKeys):
        if len(keys.receive) != 32 or len(keys.transmit) != 32:
            raise CryptoError("Directional keys must each contain 32 bytes.")
        self._receive = ChaCha20Poly1305(keys.receive)
        self._transmit = ChaCha20Poly1305(keys.transmit)
        self._counter = 0
        self._lock = threading.Lock()

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        with self._lock:
            nonce = early_nonce(self._counter)
            self._counter += 1
        combined = self._transmit.encrypt(nonce, plaintext, aad)
        return aad + combined[:-16] + nonce + combined[-16:]

    def decrypt(self, packet: bytes, *, aad_bytes: int = 0) -> bytes:
        if type(aad_bytes) is not int or not 0 <= aad_bytes <= len(packet) - 28:
            raise CryptoError("Truncated early packet or invalid AAD length.")
        nonce = packet[-28:-16]
        ciphertext = packet[aad_bytes:-28] + packet[-16:]
        try:
            return self._receive.decrypt(nonce, ciphertext, packet[:aad_bytes])
        except InvalidTag:
            raise CryptoError("Early packet authentication failed.") from None

    def __repr__(self):
        return "EarlyCipher(<redacted>)"


class SessionCipher:
    """Native format 1: ciphertext || LE16(counter) || tag[16], no AAD."""

    def __init__(self, keys: DirectionalKeys, cipher_format: int = 1):
        if cipher_format != 1:
            raise CryptoError("Only negotiated session cipher format 1 is implemented.")
        self._transmit = ChaCha20Poly1305(keys.transmit)
        self._receive = ChaCha20Poly1305(keys.receive)
        self._send_counter = COUNTER_BASE
        self._receive_counter = COUNTER_BASE
        self._lock = threading.Lock()

    def encrypt(self, plaintext: bytes) -> bytes:
        with self._lock:
            counter = self._send_counter
            if counter >= 2**64:
                raise CryptoError("Session nonce space exhausted.")
            self._send_counter += 1
        combined = self._transmit.encrypt(established_nonce(counter), plaintext, b"")
        return combined[:-16] + (counter & 65535).to_bytes(2, "little") + combined[-16:]

    def decrypt(self, packet: bytes) -> bytes:
        if len(packet) < 18:
            raise CryptoError("Truncated session packet.")
        hint = int.from_bytes(packet[-18:-16], "little")
        with self._lock:
            previous = self._receive_counter
            candidate = (previous & ~65535) | hint
            if candidate < previous and previous - candidate >= 32769:
                candidate += 65536
            elif candidate >= previous and candidate - previous >= 32769:
                candidate -= 65536
            if not 0 <= candidate < 2**64:
                raise CryptoError("Invalid session nonce hint.")
            try:
                plaintext = self._receive.decrypt(established_nonce(candidate), packet[:-18] + packet[-16:], b"")
            except InvalidTag:
                raise CryptoError("Session packet authentication failed.") from None
            self._receive_counter = max(previous, candidate)
        return plaintext

    def __repr__(self):
        return "SessionCipher(<redacted>)"
