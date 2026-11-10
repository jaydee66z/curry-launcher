"""Application primitives recovered from the matching 0.744 native build."""

import secrets
import codecs
import json
import struct

from .native_crypto import CryptoError
from .application_crypto import seal, ticket_hash, ticket_check


# Native 0x1059d3ac7 evaluated offline using the build's own instructions/data.
# This is a protocol fingerprint, not a version number or a credential.
PROTOCOL_FINGERPRINT = 0x50794BEC
PROTOCOL_VERSION = 36  # Peer constructor 0x1057b2fed.
DEFAULT_APPLICATION_KEY = bytes.fromhex("fef9f0ebe2ddd4cfc6c1b8b3aaa59c97")
# ROT13 SHA1 literal extracted from the user's matching Windows binary.
BUILD_HASH = codecs.decode("6n2468080n3o0544sn4p1697s819rq38r128o269", "rot_13")


def varuint(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise CryptoError("Application integer must fit uint64.")
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def protocol_sync(random_word=None):
    # Native 0x1056ed02c, signed 64-bit zigzag followed by unsigned LEB128.
    word = secrets.randbits(32) if random_word is None else random_word
    if type(word) is not int or not 0 <= word < 2**32:
        raise CryptoError("Protocol salt must fit uint32.")
    value = (word << 32) | (word ^ PROTOCOL_FINGERPRINT)
    signed = value if value < 2**63 else value - 2**64
    encoded = (signed << 1) ^ (signed >> 63)
    return b"\x92" + varuint(encoded)


def string(value):
    data = value.encode("utf-8")
    if len(data) > 8192:
        raise CryptoError("Application string exceeds the supported limit.")
    return varuint(len(data)) + data


def player_metadata(info):
    """Recovered GameJoin-derived subset of PlayerConfigurer's player dictionary.

    Runtime service fields and BinaryString serialization remain unresolved.
    Do not copy the whole join response: it includes private transport keys.
    """
    script = info._join_script
    if type(script.get("UserId")) is not int or script["UserId"] != info.account.user_id:
        raise CryptoError("Player metadata identity does not match the authenticated account.")
    metadata = {}
    # Native getters return an empty string / zero / false when a key is absent.
    # Sources: PlayerConfigurer 0x1057d03da..0x1057d35cf and getters
    # 0x1046f1b32, 0x1046f1b56, 0x1046f1b7a, 0x1046f1bbe.
    groups = (
        (str, "", ("UserName", "DisplayName", "RandomSeed1", "PrivateServerID",
                   "MatchmakingAttributes", "MembershipType", "CharacterAppearance")),
        (int, 0, ("UserId", "DomainUserId", "UserIdMode", "VerifiedAMP",
                  "PrivateServerOwnerID", "ServerClaimedTime", "AccountAge", "FollowUserId")),
        (bool, False, ("HasVerifiedBadge", "SuperSafeChat")),
    )
    for expected, default, keys in groups:
        for key in keys:
            value = script.get(key, default)
            if type(value) is not expected:
                raise CryptoError("Unsupported player metadata field type.")
            metadata[key] = value
    for source, target, expected in (
        ("characterAppearanceId", "CharacterAppearanceId", int),
        ("IsUnknownOrUnder13", "IsUnder13", bool),
        ("CountryCode", "CountryRegionCode", str),
        ("PartyId", "PartyId", str),
        ("APIsecurityToken", "APIsecurityToken", str),
        ("Rm3Tier0CadenceSeconds", "Rm3Tier0CadenceSeconds", int),
        ("HasRobloxSubscription", "HasRobloxSubscription", bool),
        ("WhoCanWhisperChatWithMeInExperiences", "WhoCanWhisperChatWithMeInExperiences", str),
        ("GameChatType", "GameChatType", str),
        ("PlatformName", "PlatformName", str),
        ("AlternateName", "AlternateName", str),
    ):
        if source in script:
            if type(script[source]) is not expected:
                raise CryptoError("Unsupported player metadata field type.")
            metadata[target] = script[source]
    # AgeChecked arrives as an integer but is read through the string getter.
    if "AgeChecked" in script:
        value = script["AgeChecked"]
        if type(value) not in (str, int):
            raise CryptoError("Unsupported player metadata field type.")
        metadata["AgeChecked"] = str(value)
    # PlayerConfigurer writes both localization service fields at
    # 0x1057d1a79..0x1057d1b3b. GameJoin uses underscore locale tags.
    for source, target in (("GameLocale", "LocaleId"), ("RobloxLocale", "LocaleIdInternal")):
        if source in script:
            value = script[source]
            if not isinstance(value, str) or not 1 <= len(value) <= 32:
                raise CryptoError("Unsupported player locale metadata.")
            metadata[target] = value.lower().replace('_', '-')
    encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 8192:
        raise CryptoError("Player metadata exceeds the supported limit.")
    return encoded


def network_metadata(capabilities, player_info_json=""):
    """Minimal native metadata variant, with an empty local FastFlag registry."""
    body = b"\x90\x01" + struct.pack("<I", PROTOCOL_VERSION)
    if capabilities & 0x100000:
        body += b"\x03\x0e"
    elif capabilities & 0x800:
        body += b"\x03"
    body += b"\0\0" + string(player_info_json)  # zero advertised FastFlags, player dictionary JSON
    first = 0xdc498537
    body += struct.pack("<I", first)
    if not first & 0x0c:
        body += struct.pack("<I", first)
    body += struct.pack("<I", 0x8fe1aee5)
    if not first & 0x50:
        body += struct.pack("<I", first)
    body += struct.pack("<I", 0xff3383cb)
    if not first & 0xa0:
        body += struct.pack("<I", first)
    body += struct.pack("<I", 0xd54ec827)
    if not first & 0x900:
        body += struct.pack("<I", first)
    body += struct.pack("<I", 0x5504a345)
    return seal(body, DEFAULT_APPLICATION_KEY)


def version_hash():
    # Native 0x1059d3ddc, four interleaved little-endian hex byte columns.
    suffix = "".join(f"{(0xdc498537 >> shift) & 255:02x}"
                     f"{(0x8fe1aee5 >> shift) & 0xef:02x}"
                     f"{(0xff3383cb >> shift) & 255:02x}"
                     f"{(0xe4688655 >> shift) & 255:02x}" for shift in (0, 8, 16, 24))
    return BUILD_HASH + "!" + suffix + "."


def login_key(place_id):
    def signed32(value):
        return (value + 2**31) % 2**32 - 2**31
    # Native snprintf("%d%d%d%d"), then std::string::resize(16).
    text = "".join(str(signed32(value)) for value in
                   (place_id, 0xdc498537, 0xff3383cb, 0x8fe1aee5))
    return text.encode("ascii")[:16].ljust(16, b"\0")


def authentication(info):
    """Recovered 0.744 application ticket candidate; acceptance unverified."""
    ticket = info._join_script.get("ClientTicket")
    if not isinstance(ticket, str) or not ticket.isascii() or len(ticket) > 8192:
        raise CryptoError("Missing or unsupported application ticket.")
    session = info._join_script.get("SessionId")
    try:
        if not isinstance(session, str) or not isinstance(json.loads(session), dict):
            raise ValueError
    except (ValueError, TypeError):
        raise CryptoError("Missing or unsupported authentication SessionId.") from None
    check = ticket_check(ticket_hash(ticket.encode("ascii")))
    body = (b"\x8a" + varuint(info.account.user_id * 2) + string(ticket) +
            struct.pack("<I", PROTOCOL_VERSION) + string(version_hash()) + string("Win32") +
            string("?") + varuint(check) + varuint((check + 0xf4520ff3) & 0xffffffff) +
            # PlayerConfigurer 0x1057d0294 reads SessionId and passes it to
            # NetworkClient::setter 0x1056e9e3e, which stores it at +0xee8.
            string("") + string(session) + struct.pack("<I", 0xc001cafe))
    return seal(body, login_key(info.place_id))
