"""Unit tests for mm2_inventory.read_candies, snapshot_owned, EmbersickleWatcher."""

from __future__ import annotations

import unittest

from rakbot import mm2_inventory


class _NodeStore(dict):
    def children(self, parent_key):
        return [(k, n) for k, n in self.items() if n.get('parent') == parent_key]

    def items(self):
        return list(super().items())


class _FakeInspector:
    def __init__(self, with_candies=0, owned_weapons=None):
        self.nodes = _NodeStore()
        rs = (1, 1)
        mods = (1, 2)
        pd = (1, 3)
        mats = (1, 4)
        owned_mats = (1, 5)
        candies = (1, 6)
        weps = (1, 7)
        owned_weps = (1, 8)
        self.nodes[rs] = {'class': 'ReplicatedStorage',
                          'props': {'Name': b'ReplicatedStorage'}, 'parent': None}
        self.nodes[mods] = {'class': 'Folder',
                            'props': {'Name': b'Modules'}, 'parent': rs}
        self.nodes[pd] = {'class': 'ModuleScript',
                          'props': {'Name': b'ProfileData'}, 'parent': mods}
        self.nodes[mats] = {'class': 'Folder',
                            'props': {'Name': b'Materials'}, 'parent': pd}
        self.nodes[owned_mats] = {'class': 'Folder',
                                  'props': {'Name': b'Owned'}, 'parent': mats}
        self.nodes[candies] = {'class': 'NumberValue',
                               'props': {'Name': b'Candies2026',
                                         'Value': with_candies},
                               'parent': owned_mats}
        self.nodes[weps] = {'class': 'Folder',
                            'props': {'Name': b'Weapons'}, 'parent': pd}
        self.nodes[owned_weps] = {'class': 'Folder',
                                  'props': {'Name': b'Owned'}, 'parent': weps}
        for i, name in enumerate(owned_weapons or ()):
            self.nodes[(10, i + 1)] = {'class': 'BoolValue',
                                       'props': {'Name': name.encode('utf-8'), 'Value': True},
                                       'parent': owned_weps}


class TestReadCandies(unittest.TestCase):

    def test_reads_value(self):
        insp = _FakeInspector(with_candies=250)
        self.assertEqual(mm2_inventory.read_candies(insp), 250)

    def test_zero(self):
        insp = _FakeInspector(with_candies=0)
        self.assertEqual(mm2_inventory.read_candies(insp), 0)

    def test_missing_profile_data(self):
        insp = _FakeInspector()
        insp.nodes.clear()
        self.assertIsNone(mm2_inventory.read_candies(insp))


class TestSnapshotWeapons(unittest.TestCase):

    def test_captures_all(self):
        insp = _FakeInspector(owned_weapons=['DefaultKnife', 'Embersickle', 'Skulls_K_2026'])
        snap = mm2_inventory.snapshot_owned_weapons(insp)
        self.assertEqual(snap, {'DefaultKnife', 'Embersickle', 'Skulls_K_2026'})

    def test_empty_when_missing(self):
        insp = _FakeInspector(owned_weapons=[])
        snap = mm2_inventory.snapshot_owned_weapons(insp)
        self.assertEqual(snap, set())


class TestEmbersickleWatcher(unittest.TestCase):

    def test_baseline_not_notified(self):
        insp = _FakeInspector(owned_weapons=['Embersickle'])  # already owned
        events = []
        watcher = mm2_inventory.EmbersickleWatcher(
            insp, username='test', user_id=123,
            webhook_url='http://example.invalid/', emit=events.append)
        watcher._poll_once()
        drops = [e for e in events if e.get('event') == 'rare_drop']
        self.assertEqual(drops, [], "baseline items should not trigger notify")

    def test_new_drop_notified(self):
        insp = _FakeInspector(owned_weapons=['DefaultKnife'])  # baseline
        events = []
        watcher = mm2_inventory.EmbersickleWatcher(
            insp, username='test', user_id=123,
            webhook_url='http://example.invalid/', emit=events.append)
        # Add Embersickle to the replicated world after baseline
        insp.nodes[(10, 99)] = {'class': 'BoolValue',
                                'props': {'Name': b'Embersickle', 'Value': True},
                                'parent': (1, 8)}
        watcher._poll_once()
        drops = [e for e in events if e.get('event') == 'rare_drop']
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]['item'], 'Embersickle')
        self.assertEqual(drops[0]['variant'], 'common')

    def test_chroma_variant(self):
        insp = _FakeInspector(owned_weapons=[])
        events = []
        watcher = mm2_inventory.EmbersickleWatcher(
            insp, username='test', user_id=123,
            webhook_url='http://example.invalid/', emit=events.append)
        insp.nodes[(10, 99)] = {'class': 'BoolValue',
                                'props': {'Name': b'EmbersickleChroma', 'Value': True},
                                'parent': (1, 8)}
        watcher._poll_once()
        drops = [e for e in events if e.get('event') == 'rare_drop']
        self.assertEqual(len(drops), 1)
        self.assertEqual(drops[0]['variant'], 'chroma')

    def test_notify_deduplicated(self):
        insp = _FakeInspector()
        events = []
        watcher = mm2_inventory.EmbersickleWatcher(
            insp, username='test', user_id=123,
            webhook_url='http://example.invalid/', emit=events.append)
        insp.nodes[(10, 99)] = {'class': 'BoolValue',
                                'props': {'Name': b'Embersickle', 'Value': True},
                                'parent': (1, 8)}
        watcher._poll_once()
        watcher._poll_once()  # second poll
        drops = [e for e in events if e.get('event') == 'rare_drop']
        self.assertEqual(len(drops), 1, "same drop should not re-notify")


if __name__ == '__main__':
    unittest.main()
