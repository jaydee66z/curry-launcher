"""Receive-side nodes indexed by class and parent; updates stay on one thread."""
from collections import defaultdict


class NodeStore(dict):
    def __init__(self, values=()):
        super().__init__()
        self.by_class = defaultdict(set)
        self.by_parent = defaultdict(set)
        self.update(values)

    def _discard(self, key, node):
        for index, value in ((self.by_class, node['class']), (self.by_parent, node['parent'])):
            bucket = index.get(value)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    del index[value]

    def __setitem__(self, key, node):
        if key in self:
            self._discard(key, self[key])
        super().__setitem__(key, node)
        self.by_class[node['class']].add(key)
        self.by_parent[node['parent']].add(key)

    def __delitem__(self, key):
        self._discard(key, self[key])
        super().__delitem__(key)

    def pop(self, key, *default):
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default:
            return default[0]
        raise KeyError(key)

    def clear(self):
        super().clear()
        self.by_class.clear()
        self.by_parent.clear()

    def update(self, values=(), **kwargs):
        for key, value in (values.items() if hasattr(values, 'items') else values):
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def reparent(self, key, parent):
        node = self[key]
        old = node['parent']
        if old != parent:
            bucket = self.by_parent[old]
            bucket.discard(key)
            if not bucket:
                del self.by_parent[old]
            self.by_parent[parent].add(key)
            node['parent'] = parent

    def class_items(self, name):
        return ((key, self[key]) for key in self.by_class.get(name, ()))

    def children(self, parent):
        return ((key, self[key]) for key in self.by_parent.get(parent, ()))
