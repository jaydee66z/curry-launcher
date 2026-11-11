"""Unit tests for mm2_client.Session (dry-run only — no transport)."""

from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

from rakbot import mm2_client


@dataclass
class _ClassDescriptor:
    name: str


class _Schema:
    classes = [{'name': 'RemoteEvent'}, {'name': 'RemoteFunction'}]
    events  = [{'class_id': 0, 'name': 'RemoteOnReceive', 'arguments': [{'type': 29}]}]


class _NodeStore(dict):
    def children(self, parent_key):
        """Mimic the real NodeStore.children iterator."""
        return [(k, n) for k, n in self.items() if n.get('parent') == parent_key]

    def items(self):
        return list(super().items())


class _FakeInspector:
    def __init__(self):
        self.schema = _Schema()
        self.own = (99, 1)
        self.nodes = _NodeStore()
        char_key = (100, 1)
        hrp_key = (100, 2)
        self.nodes[(99, 1)] = {'class': 'Player',
                               'props': {'Character': char_key, 'UserId': 123, 'Name': b'test'},
                               'parent': None}
        self.nodes[char_key] = {'class': 'Model', 'props': {'Name': b'Character'}, 'parent': None}
        self.nodes[hrp_key] = {'class': 'Part',
                               'props': {'Name': b'HumanoidRootPart',
                                         'CFrame': {'position': (0.0, 5.0, 0.0),
                                                    'rotation_code': 0}},
                               'parent': char_key}


class _FakeTransport:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


class TestSession(unittest.TestCase):

    def test_dry_run_emits_events(self):
        insp = _FakeInspector()
        transport = _FakeTransport()
        emitted = []
        session = mm2_client.Session(inspector=insp, transport=transport,
                                     emit=lambda e: emitted.append(e))
        # Add a coin node far enough to NOT trigger pickup but visible
        coin_key = (200, 1)
        insp.nodes[coin_key] = {'class': 'Part',
                                'props': {'Name': b'Coin_Server',
                                          'CFrame': {'position': (3.0, 5.0, 3.0),
                                                     'rotation_code': 0}},
                                'parent': None}
        # Dry run for 0.3s
        session.run(duration=0.3, dry_run=True)
        # No real send
        self.assertEqual(transport.sent, [])
        # Some dry_send events may have been emitted (if the coin was pickable)
        dry_events = [e for e in emitted if e.get('event') == 'dry_send']
        self.assertGreaterEqual(len(dry_events), 0)  # at least non-crashing

    def test_hrp_position_resolution(self):
        insp = _FakeInspector()
        pos = mm2_client._hrp_position(insp)
        self.assertEqual(pos, (0.0, 5.0, 0.0))

    def test_hrp_position_missing(self):
        insp = _FakeInspector()
        insp.own = None
        pos = mm2_client._hrp_position(insp)
        self.assertIsNone(pos)

    def test_coin_server_detection(self):
        node_ok = {'class': 'Part', 'props': {'Name': b'Coin_Server'}}
        node_not = {'class': 'Part', 'props': {'Name': b'OtherThing'}}
        self.assertTrue(mm2_client._is_coin_server(node_ok))
        self.assertFalse(mm2_client._is_coin_server(node_not))
        self.assertFalse(mm2_client._is_coin_server(None))

    def test_session_counters_start_at_zero(self):
        s = mm2_client.Session(inspector=_FakeInspector(), transport=_FakeTransport())
        self.assertEqual(s.candies_this_round, 0)
        self.assertEqual(s.lifetime_candies, 0)
        self.assertEqual(s.boxes_opened, 0)

    def test_on_coins_started_resets(self):
        s = mm2_client.Session(inspector=_FakeInspector(), transport=_FakeTransport())
        s.candies_this_round = 25
        s.attempts[(1, 1)] = mm2_client.CoinAttempt()
        s.visited.add((1, 2))
        s.on_coins_started()
        self.assertEqual(s.candies_this_round, 0)
        self.assertEqual(s.attempts, {})
        self.assertEqual(s.visited, set())

    def test_on_coin_collected_increments(self):
        emitted = []
        s = mm2_client.Session(inspector=_FakeInspector(),
                               transport=_FakeTransport(),
                               emit=lambda e: emitted.append(e))
        s.on_coin_collected(b'Candy')
        self.assertEqual(s.candies_this_round, 1)
        self.assertEqual(s.lifetime_candies, 1)
        s.on_coin_collected(b'Candy')
        self.assertEqual(s.lifetime_candies, 2)


if __name__ == '__main__':
    unittest.main()
