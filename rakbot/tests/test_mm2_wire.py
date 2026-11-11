"""Unit tests for mm2_wire payload encoders.

These validate byte-level output against the heli_wars pattern so a
regression in opcode encoding is caught at test time.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any

from rakbot import mm2_wire
from rakbot.application import varuint, string
from rakbot.heli_wars import wire_guid


# ───────────────────────────────────────────────
# Minimal stand-in types for Inspector + schema
# ───────────────────────────────────────────────

@dataclass
class _ClassDescriptor:
    name: str


@dataclass
class _Event:
    class_id: int
    name: str
    arguments: list


class _Schema:
    def __init__(self):
        # class 0 = RemoteEvent, class 1 = RemoteFunction
        self.classes = [{'name': 'RemoteEvent'}, {'name': 'RemoteFunction'}]
        self.events = [
            {'class_id': 0, 'name': 'RemoteOnReceive',
             'arguments': [{'type': 29}]},
            {'class_id': 1, 'name': 'RemoteOnInvokeServer',
             'arguments': [{'type': 10}, {'type': 28}, {'type': 29}]},
        ]


class _NodeStore(dict):
    def items(self):
        return list(super().items())


class _Inspector:
    def __init__(self):
        self.schema = _Schema()
        self.own = (99, 1)   # dummy player key
        self.nodes = _NodeStore()
        # Build: ReplicatedStorage → Remotes → Gameplay → GetCoin
        rs_key = (1, 1)
        rem_key = (1, 2)
        gp_key = (1, 3)
        getcoin_key = (1, 4)
        shop_key = (1, 5)
        opencrate_key = (1, 6)
        self.nodes[rs_key] = {'class': 'ReplicatedStorage',
                              'props': {'Name': b'ReplicatedStorage'}, 'parent': None}
        self.nodes[rem_key] = {'class': 'Folder',
                               'props': {'Name': b'Remotes'}, 'parent': rs_key}
        self.nodes[gp_key] = {'class': 'Folder',
                              'props': {'Name': b'Gameplay'}, 'parent': rem_key}
        self.nodes[getcoin_key] = {'class': 'RemoteEvent',
                                   'props': {'Name': b'GetCoin'}, 'parent': gp_key}
        self.nodes[shop_key] = {'class': 'Folder',
                                'props': {'Name': b'Shop'}, 'parent': rem_key}
        self.nodes[opencrate_key] = {'class': 'RemoteFunction',
                                     'props': {'Name': b'OpenCrate'}, 'parent': shop_key}
        self.getcoin_key = getcoin_key
        self.opencrate_key = opencrate_key


# ───────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────

class TestVariantEncoders(unittest.TestCase):

    def test_variant_instance_shape(self):
        out = mm2_wire.variant_instance((5, 7))
        self.assertEqual(out[:1], b'\x1c')
        self.assertEqual(out[1:], wire_guid((5, 7)))

    def test_variant_string_shape(self):
        out = mm2_wire.variant_string("Halloween2026Box")
        self.assertEqual(out[:1], b'\x02')
        self.assertEqual(out[1:], string("Halloween2026Box"))

    def test_variant_array_terminator(self):
        v1 = mm2_wire.variant_string("a")
        v2 = mm2_wire.variant_string("b")
        out = mm2_wire.variant_array([v1, v2])
        self.assertTrue(out.endswith(b'\0'),
                        "variant_array must end with 0x00 terminator")
        self.assertEqual(out[:len(varuint(2))], varuint(2))

    def test_variant_array_empty(self):
        out = mm2_wire.variant_array([])
        self.assertEqual(out, varuint(0) + b'\0')


class TestRemoteDiscovery(unittest.TestCase):

    def test_find_getcoin(self):
        insp = _Inspector()
        key, eid = mm2_wire.find_remote(insp, mm2_wire.REMOTE_GETCOIN_PATH,
                                        class_name='RemoteEvent')
        self.assertEqual(key, insp.getcoin_key)
        self.assertEqual(eid, 0)

    def test_find_opencrate(self):
        insp = _Inspector()
        key, eid = mm2_wire.find_remote(insp, mm2_wire.REMOTE_OPENCRATE_PATH,
                                        class_name='RemoteFunction')
        self.assertEqual(key, insp.opencrate_key)
        self.assertEqual(eid, 1)

    def test_missing_remote(self):
        insp = _Inspector()
        key, eid = mm2_wire.find_remote(
            insp, (b'ReplicatedStorage', b'Remotes', b'DoesNotExist'),
            class_name='RemoteEvent')
        self.assertIsNone(key)
        self.assertIsNone(eid)


class TestPayloadStructure(unittest.TestCase):

    def test_getcoin_header_opcodes(self):
        insp = _Inspector()
        coin_key = (1, 100)
        insp.nodes[coin_key] = {'class': 'Part',
                                'props': {'Name': b'Coin_Server'}, 'parent': None}
        payload = mm2_wire.getcoin_payload(insp, coin_key)
        self.assertIsNotNone(payload)
        self.assertEqual(payload[:2], b'\x83\x07',
                         "payload must start with Data(0x83) + Event(0x07)")

    def test_opencrate_header_opcodes(self):
        insp = _Inspector()
        payload = mm2_wire.opencrate_payload(insp, invocation_id=5)
        self.assertIsNotNone(payload)
        self.assertEqual(payload[:2], b'\x83\x07')

    def test_getcoin_contains_coin_guid(self):
        insp = _Inspector()
        coin_key = (1, 100)
        insp.nodes[coin_key] = {'class': 'Part',
                                'props': {'Name': b'Coin_Server'}, 'parent': None}
        payload = mm2_wire.getcoin_payload(insp, coin_key)
        # Coin ref appears as a variant kind 28 (0x1c) somewhere after
        # the player ref. Easy check: 0x1c appears in the body.
        self.assertIn(b'\x1c', payload)

    def test_opencrate_contains_strings(self):
        insp = _Inspector()
        payload = mm2_wire.opencrate_payload(insp, invocation_id=1,
                                             box_id='X', type_name='Y',
                                             currency='Z')
        # Kind 2 (0x02) + string('X')/('Y')/('Z') should all appear.
        self.assertIn(b'\x02' + string('X'), payload)
        self.assertIn(b'\x02' + string('Y'), payload)
        self.assertIn(b'\x02' + string('Z'), payload)

    def test_opencrate_increments_invocation(self):
        insp = _Inspector()
        p1 = mm2_wire.opencrate_payload(insp, invocation_id=1)
        p2 = mm2_wire.opencrate_payload(insp, invocation_id=2)
        self.assertNotEqual(p1, p2,
                            "different invocation_ids must produce different payloads")


if __name__ == '__main__':
    unittest.main()
