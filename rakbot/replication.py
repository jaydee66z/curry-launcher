"""Bounded native Data reader. Replicated scripts are never executed.

Stops each message at unsupported items instead of searching bytes for IDs.
"""

from collections import Counter, OrderedDict
import hashlib
import struct

from .native_crypto import CryptoError
from .player_probe import _value
from .schema import Reader
from .node_store import NodeStore


IMPORTANT_CLASSES = frozenset(('Player', 'Players', 'Workspace', 'Model', 'Humanoid',
    'Folder', 'RemoteEvent', 'RemoteFunction', 'Team', 'Teams', 'ReplicatedStorage',
    'Chat', 'TextChatService', 'TextChannel', 'TextSource'))


def important_node(node):
    return (node['class'] in IMPORTANT_CLASSES or
            node['props'].get('Name') == b'HumanoidRootPart')


class Inspector:
    @property
    def nodes(self):
        return self._nodes

    @nodes.setter
    def nodes(self, values):
        self._nodes = values if isinstance(values, NodeStore) else NodeStore(values)
        self._evictable = OrderedDict((key, None) for key, node in self._nodes.items()
                                      if not self._important_node(node))

    def _important_node(self, node):
        return important_node(node)

    def keep_property(self, class_name, name):
        """Projection after decoding; discarded values still validate on wire."""
        return True

    def discard_value(self, reader, kind, pending, **options):
        self.value(reader, kind, pending, **options)

    def __init__(self, schema, user_id, *, retain_world=True, capabilities=0, max_nodes=65536):
        if type(max_nodes) is not int or not 1 <= max_nodes <= 65536:
            raise ValueError('World retention limit must be 1..65536.')
        self.max_nodes = max_nodes
        self.schema, self.user_id = schema, user_id
        self.retain_world = retain_world
        self.nodes, self.shared = {}, {hashlib.blake2b(b"", digest_size=16).digest()}
        self.items, self.stops = Counter(), Counter()
        self.property_names = Counter()
        self.event_names = Counter()
        self.appearance_events = []
        self.messages = self.complete = 0
        self.own = None
        self.initial_states = []
        self.unresolved_shared = set()
        self.capabilities = capabilities
        self.isr_frames = {}
        self.isr_property_frames = {}
        self.last_isr_frame = None
        self._property_projection = {}

    def _forget_node(self, key):
        self.nodes.pop(key, None)
        self._evictable.pop(key, None)
        self.isr_frames.pop(key, None)
        self.isr_property_frames.pop(key, None)
        self.removal_value(key)

    def _remember_node(self, key, node):
        if key not in self.nodes and len(self.nodes) >= self.max_nodes:
            if self._important_node(node):
                while self._evictable and len(self.nodes) >= self.max_nodes:
                    victim, _ = self._evictable.popitem(last=False)
                    if victim not in self.nodes:
                        continue
                    self._forget_node(victim)
                    self.items['WorldInstanceEvicted'] += 1
                if (len(self.nodes) >= self.max_nodes and
                        (node['class'] in ('Chat', 'TextChatService', 'TextChannel', 'TextSource') or
                         node['class'] == 'Folder' and node['props'].get('Name') == b'TextChannels')):
                    # Large maps can exhaust even the Model/Folder budget.
                    # Keep chat identities and their one folder over map models,
                    # while preserving every observed Player.Character reference.
                    characters = {p['props'].get('Character') for _, p in self.nodes.class_items('Player')}
                    victim = next((k for k, n in self.nodes.class_items('Model')
                                   if k not in characters and not n['props'].get('Tags') and
                                   not n['props'].get('AttributesReplicate')), None)
                    if victim is not None:
                        self._forget_node(victim)
                        self.items['WorldInstanceEvicted'] += 1
            if len(self.nodes) >= self.max_nodes:
                # The wire record was fully decoded. Retention pressure is not
                # a wire-format error and must not drop the rest of this packet.
                self.items['WorldInstanceNotRetained'] += 1
                return
        self.nodes[key] = node
        self._evictable.pop(key, None)
        if not self._important_node(node):
            self._evictable[key] = None

    def variant(self, reader, pending, depth, cached_content):
        kind = reader.take(1)[0]
        if kind == 0:
            return None
        if kind == 7:
            enum = reader.u16()
            if enum >= len(self.schema.enums):
                raise CryptoError("variant enum index out of range")
        return self.value(reader, kind, pending, depth=depth + 1, cached_content=cached_content)

    def content_id(self, reader, cached):
        if not cached:
            return reader.take(reader.var(8192))
        code = reader.take(1)[0]
        index = code >> 1
        if not self.schema.string_tables or index >= len(self.schema.string_tables[0]):
            raise CryptoError("ContentId prefix index out of range")
        prefix = self.schema.string_tables[0][index].encode('utf-8')
        if code & 1:
            value = reader.var(2**64 - 1)
            suffix = str((value >> 1) ^ -(value & 1)).encode('ascii')
        else:
            suffix = reader.take(reader.var(8192))
        return prefix + suffix

    @staticmethod
    def guid(reader):
        scope = reader.var(2**32 - 1)
        return None if scope == 0 else (scope, reader.u32())

    def value(self, reader, kind, pending, *, depth=0, cached_content=False):
        if depth > 16:
            raise CryptoError("variant nesting exceeds bound")
        if kind == 56:
            # Native 0x105823e1a: compressed/expanded varuints; zero
            # compressed size carries raw bytes, otherwise a zstd frame.
            compressed, expanded = reader.var(1048576), reader.var(1048576)
            if not compressed:
                return reader.take(expanded)
            from compression import zstd
            decoder = zstd.ZstdDecompressor()
            try:
                blob = decoder.decompress(reader.take(compressed), max_length=expanded + 1)
            except zstd.ZstdError:
                raise CryptoError('Invalid Buffer zstd stream') from None
            if len(blob) != expanded or not decoder.eof or decoder.unused_data:
                raise CryptoError('Buffer zstd size mismatch')
            return blob
        if kind in (29, 30, 31):
            count = reader.var(4096)
            if kind in (29, 30):
                return [self.variant(reader, pending, depth, cached_content) for _ in range(count)]
            result = {}
            for _ in range(count):
                key = reader.take(reader.var(8192))
                if key in result:
                    raise CryptoError("duplicate dictionary key")
                result[key] = self.variant(reader, pending, depth, cached_content)
            return result
        if kind == 33:
            return self.content_id(reader, cached_content)
        if kind == 13:
            return struct.unpack("<fi", reader.take(8))
        if kind == 14:
            return struct.unpack("<fifi", reader.take(16))
        if kind == 37:
            return struct.unpack("<ff", reader.take(8))
        if kind == 40:
            return struct.unpack("<ffff", reader.take(16))
        if kind == 35:
            count = reader.u32()
            if count > 20:
                raise CryptoError("NumberSequence exceeds bound")
            reader.take(count * 12)
            return None
        if kind == 38:
            count = reader.u32()
            if count > 20:
                raise CryptoError("ColorSequence exceeds bound")
            reader.take(count * 20)
            return None
        if kind == 41:
            flags = reader.take(1)[0]
            if flags & 1:
                reader.take(24 if flags >= 2 else 20)
            return None
        if kind == 54:
            weight = reader.u16()
            style = reader.take(1)[0]
            if weight > 1000 or style > 1:
                raise CryptoError("unsupported Font enum")
            for _ in range(2):
                size = reader.u32()
                if size > 8192:
                    raise CryptoError("Font string exceeds bound")
                reader.take(size)
            return None
        if kind == 69:
            return self.guid(reader)
        if kind in (46, 47):
            digest = reader.take(16)
            if digest not in self.shared:
                pending.add(digest)
            return None  # preserve no source, tags or other opaque content
        if kind == 49:
            code = reader.take(1)[0]
            if code & 128:
                index = code & 127
                if index == 127:
                    index += reader.var()
                if len(self.schema.string_tables) < 2 or index >= len(self.schema.string_tables[1]):
                    raise CryptoError("unsupported cached name")
                return self.schema.string_tables[1][index].encode("utf-8")
            return reader.take(code if code < 127 else reader.var(8192))
        if kind == 21:
            return struct.unpack("<ff", reader.take(8))
        if kind == 12:
            return struct.unpack("<d", reader.take(8))[0]
        if kind == 19:
            return struct.unpack("<fff", reader.take(12))
        if kind == 20:
            return reader.take(3)
        if kind == 34:
            return reader.var(2**32 - 1)
        if kind == 27:
            position = struct.unpack("<fff", reader.take(12))
            rotation = reader.take(1)[0]
            if rotation == 0:
                reader.take(6)  # 0x10571eafc: LE16 + LE32 packed quaternion
            return {"position": position, "rotation_code": rotation}
        if kind == 51:
            rotation = reader.take(1)[0]
            if not rotation & 128:
                return None
            if not rotation & 127:
                reader.take(6)
            return {"position": struct.unpack("<fff", reader.take(12)), "rotation_code": rotation & 127}
        if kind == 61:
            variant = reader.var(3)
            if variant == 0:
                return None
            if variant in (1, 3):
                return reader.take(reader.var(1048576))
            raise CryptoError("unsupported Content variant")
        if kind == 60:
            # Native 0x10582415a, unmapped dynamic type table: packed
            # resource key, revision varint, then a raw LE64 type ID.
            key = reader.take(8)
            revision = reader.var(2**32 - 1)
            type_id = int.from_bytes(reader.take(8), 'little')
            if type_id not in {row[0] for row in self.schema.dynamic_types}:
                raise CryptoError("unsupported dynamic resource type")
            return {'resource_key': key, 'revision': revision, 'type_id': type_id}
        return _value(reader, kind)

    def flush_shared(self, reader, pending):
        while pending:
            digest, cached = reader.take(16), reader.take(1)[0]
            if digest not in pending:
                raise CryptoError("unresolved shared string order")
            if cached == 0:
                blob = reader.take(reader.var(1048576))
                if hashlib.blake2b(blob, digest_size=16).digest() != digest:
                    raise CryptoError("shared string checksum mismatch")
                self.shared_value(digest, blob)
            elif cached == 1:
                self._resolve_shared_cache(digest, 'unresolved shared string cache')
            else:
                raise CryptoError("unresolved shared string cache")
            pending.remove(digest)
            self.shared.add(digest)

    def shared_value(self, digest, blob):
        """Verified opaque value callback; the default reader retains no source."""
        pass

    def cached_shared_value(self, digest):
        return None

    def _resolve_shared_cache(self, digest, error):
        if digest not in self.shared:
            blob = self.cached_shared_value(digest)
            if blob is None:
                raise CryptoError(error)
            self.shared_value(digest, blob)

    def new(self, reader, *, joined=False, deferred_shared=None):
        key = self.guid(reader)
        cid = reader.u16()
        if key is None or cid >= len(self.schema.classes):
            raise CryptoError("unsupported new instance header")
        descriptor = self.schema.classes[cid]
        retained = self._property_projection.get(cid)
        if retained is None:
            retained = tuple(self.keep_property(descriptor['name'], p['name']) for p in descriptor['properties'])
            self._property_projection[cid] = retained
        props, pending = {}, set()
        # JoinData reader 0x1057fdcee has one property list; ordinary
        # NewInstance has two and then resolves deferred shared strings.
        for list_index in range(1 if joined else 2):
            previous = -1
            while True:
                index = reader.u8()
                if index == 255:
                    break
                if index <= previous or index >= len(descriptor["properties"]):
                    raise CryptoError("unsupported property index")
                previous = index
                prop = descriptor["properties"][index]
                try:
                    # Native NewInstance 0x10580a4dd passes cached-content=1
                    # for list 0, then 0 at 0x10580a4fe. JoinData has one
                    # uncached list (0x1057fe013).
                    if retained[index]:
                        props[prop['name']] = self.value(reader, prop['type'], pending,
                            cached_content=not joined and list_index == 0)
                    else:
                        self.discard_value(reader, prop['type'], pending,
                            cached_content=not joined and list_index == 0)
                except CryptoError as error:
                    raise CryptoError(f"new:{descriptor['name']}:{prop['name']}:type{prop['type']}:{error}") from None
        if not joined:
            self.flush_shared(reader, pending)
        parent = self.guid(reader)
        self._commit_new(key, cid, props, parent, pending, joined=joined, deferred_shared=deferred_shared)

    def _commit_new(self, key, cid, props, parent, pending, *, joined=False, deferred_shared=None):
        descriptor = self.schema.classes[cid]
        if joined and pending:
            # A reference is a fixed-size hash regardless of cache availability.
            # Preserve the structural record without inventing its opaque value;
            # it can arrive in a later SharedString block. No code is executed.
            self._joined_shared(pending, deferred_shared)
        if self.retain_world or descriptor["name"] == "Player":
            self._remember_node(key, {"class": descriptor["name"], "parent": parent, "props": props})
        else:
            if key in self.nodes:
                self._forget_node(key)  # Reused GUID must not retain a former Player.
        if descriptor["name"] == "Player" and props.get("UserId") == self.user_id:
            self.own = key
        self.items["NewInstance"] += 1
        if key in self.nodes:
            self.isr_frames.pop(key, None)
            self.isr_property_frames.pop(key, None)
            self.instance_value(key, self.nodes[key])

    def _joined_shared(self, pending, deferred_shared=None):
        remaining = set()
        for digest in pending:
            # JoinData can bind a global cache entry when its instance is
            # declared. StreamData instead has its own deferred wire trailer:
            # even an advertised hash must consume that trailer's record.
            blob = self.cached_shared_value(digest) if deferred_shared is None else None
            if blob is not None:
                # Native 0x1057fe0a1..0x1057fe0e4 binds a cached reference
                # after the joined instance declares it. This is different
                # from pre-seeding all hashes before ordinary inline records.
                self.shared.add(digest)
                self.shared_value(digest, blob)
            else:
                remaining.add(digest)
        pending = remaining
        if len(self.unresolved_shared | pending) > 65536:
            raise CryptoError("unresolved shared reference limit")
        self.unresolved_shared.update(pending)
        if deferred_shared is not None:
            deferred_shared.update(pending)

    def instance_value(self, key, node):
        """Called only after a complete instance record has been decoded."""
        pass

    def new_many(self, reader, count, *, deferred_shared=None):
        for _ in range(count):
            self.new(reader, joined=True, deferred_shared=deferred_shared)

    def property_value(self, key, name, value):
        """Called only after a complete property update has been decoded."""
        pass

    def removal_value(self, key):
        """Instance removal callback after its complete record is decoded."""
        pass

    def atomic_value(self, first, second):
        """The two validated references of ResolveNewInstanceAtomicTreeItem."""
        pass

    def changed(self, reader):
        key, pid = self.guid(reader), reader.u16()
        if pid == len(self.schema.properties):
            prop = {"name": "Parent", "type": 28}
        elif pid < len(self.schema.properties):
            prop = self.schema.properties[pid]
        else:
            raise CryptoError("property ID out of range")
        reader.take(1)  # ClientReplicator callback +458 / 0x10570eb60
        pending = set()
        node = self.nodes.get(key)
        retain = node is not None and self.keep_property(node['class'], prop['name'])
        try:
            # DeserializedPropertyItem 0x1057f8883 sets cached-content=1.
            if retain:
                value = self.value(reader, prop['type'], pending, cached_content=True)
            else:
                self.discard_value(reader, prop['type'], pending, cached_content=True)
        except CryptoError as error:
            raise CryptoError(f"change:{prop['name']}:type{prop['type']}:{error}") from None
        self.flush_shared(reader, pending)
        self.property_names[prop["name"]] += 1
        if key in self.nodes:
            if not retain:
                self.items['ChangedProperty'] += 1
                return
            if prop["name"] == "Parent":
                self.nodes.reparent(key, value)
            else:
                self.nodes[key]["props"][prop["name"]] = value
                if prop['name'] == 'Name':
                    if self._important_node(self.nodes[key]):
                        self._evictable.pop(key, None)
                    else:
                        self._evictable.setdefault(key, None)
            self.property_value(key, prop['name'], value)
        self.items["ChangedProperty"] += 1

    def event(self, reader):
        key = self.guid(reader)
        eid = reader.u16()
        if eid >= len(self.schema.events):
            raise CryptoError("event ID out of range")
        event = self.schema.events[eid]
        pending = set()
        arguments = []
        for arg in event["arguments"]:
            try:
                # Native Event reader 0x1057f8883 passes cache flag 1.
                arguments.append(self.value(reader, arg["type"], pending, cached_content=True))
            except CryptoError as error:
                raise CryptoError(f"event:{event['name']}:type{arg['type']}:{error}") from None
        self.flush_shared(reader, pending)
        name = self.schema.classes[event["class_id"]]["name"] + "." + event["name"]
        self.event_names[name] += 1
        self.event_value(name, key, arguments)
        if name == "Player.CharacterAppearanceLoaded":
            self.appearance_events.append((key, arguments))
        self.items["Event"] += 1

    def event_value(self, name, key, arguments):
        """Decoded event callback; default retains only event counters."""
        pass

    def ping_value(self, kind, flags, timestamp, tick, large):
        """Parsed Data/Ping callback, separate from the transport ping."""
        pass

    def ping(self, reader, kind):
        flags = reader.take(1)[0]
        if flags not in (0, 1):
            raise CryptoError("unsupported ping flags")
        timestamp = int.from_bytes(reader.take(8), 'little')
        tick = reader.u32()
        if flags & 1:
            reader.take(24)
        reader.take(8)
        large = reader.take(1)[0]
        if large > 1:
            raise CryptoError("invalid ping boolean")
        self.items["Ping"] += 1
        self.ping_value(kind, flags, timestamp, tick, bool(large))

    def join_v2(self, reader):
        from compression import zstd
        mode = reader.take(1)[0]
        compressed, expanded = reader.u32(), reader.u32()
        if not 0 < compressed <= 16 * 1024 * 1024 or not 0 <= expanded <= 16 * 1024 * 1024:
            raise CryptoError("JoinData block size exceeds bound")
        decoder = zstd.ZstdDecompressor()
        try:
            raw = decoder.decompress(reader.take(compressed), max_length=expanded + 1)
        except zstd.ZstdError:
            raise CryptoError("invalid JoinData compressed stream") from None
        if len(raw) != expanded or not decoder.eof or decoder.unused_data:
            raise CryptoError("JoinData compressed stream size mismatch")
        if mode == 1:
            block = Reader(raw)
            while block.at < len(raw):
                digest, cached = block.take(16), block.take(1)[0]
                if cached == 0:
                    blob = block.take(block.var(1048576))
                    if hashlib.blake2b(blob, digest_size=16).digest() != digest:
                        raise CryptoError("JoinData shared string checksum mismatch")
                    self.shared_value(digest, blob)
                elif cached == 1:
                    self._resolve_shared_cache(digest, 'unresolved JoinData shared cache')
                else:
                    raise CryptoError("unresolved JoinData shared cache")
                self.shared.add(digest)
                self.items["SharedString"] += 1
        elif mode in (2, 3, 4):
            count = reader.u32()
            if count > 65535:
                raise CryptoError("JoinData instance count exceeds bound")
            ranges = []
            for _ in range(reader.var()):
                offset, size = reader.var(2**32 - 1), reader.var(2**32 - 1)
                if offset + size > len(raw):
                    raise CryptoError("JoinData cache range exceeds block")
                ranges.append((offset, size))
            # Native 0x1057ffb83..0x1057ffbac sorts invalidation ranges by
            # offset before traversing the instance stream. The server's
            # serialized invalidation list is not necessarily ordered.
            ranges.sort()
            if any(first + size > following for (first, size), (following, _) in zip(ranges, ranges[1:])):
                raise CryptoError('Overlapping JoinData cache ranges')
            block = Reader(raw)
            at_range = 0
            if not ranges:
                self.new_many(block, count)
            else:
                for _ in range(count):
                    while at_range < len(ranges) and ranges[at_range][0] == block.at:
                        block.take(ranges[at_range][1])
                        at_range += 1
                    self.new(block, joined=True)
            while at_range < len(ranges) and ranges[at_range][0] == block.at:
                block.take(ranges[at_range][1])
                at_range += 1
            if block.at != len(raw):
                # The compressed block is already bounded and fully consumed
                # from the outer stream. Do not search its trailing bytes for
                # records; continue only at the validated outer item boundary.
                self.stops['JoinData instance block has trailing data'] += 1
        else:
            raise CryptoError(f"unsupported JoinData mode:{mode}")
        self.items["JoinDataV2"] += 1

    def stream_instances(self, reader):
        """Client Data 0x0d: 0x105924d78 / 0x105921a92.

        The compressed instance list uses one property list per instance,
        followed by the shared strings and the outer region descriptors.
        """
        from compression import zstd
        if self.capabilities & ((1 << 42) | (1 << 52)):
            raise CryptoError('unsupported extended stream instance capabilities')
        count = reader.u32()
        if count > 65535:
            raise CryptoError("stream instance count exceeds bound")
        if count:
            compressed, expanded = reader.u32(), reader.u32()
            if not 0 < compressed <= 16 * 1024 * 1024 or not 0 <= expanded <= 16 * 1024 * 1024:
                raise CryptoError("stream instance block size exceeds bound")
            decoder = zstd.ZstdDecompressor()
            try:
                raw = decoder.decompress(reader.take(compressed), max_length=expanded + 1)
            except zstd.ZstdError:
                raise CryptoError("invalid stream instance compressed block") from None
            if len(raw) != expanded or not decoder.eof or decoder.unused_data:
                raise CryptoError("stream instance compressed size mismatch")
            block = Reader(raw)
            pending = set()
            self.new_many(block, count, deferred_shared=pending)
            self.flush_shared(block, pending - self.shared)
            if block.at != len(raw):
                raise CryptoError("stream instance block has trailing data")
        # 0x105924ba6: bit 3 continues the region list; other bits are
        # region commands. Only command zero carries a Vector3int32.
        for _ in range(4096):
            flags = reader.take(1)[0]
            if flags & 0xf7 == 0:
                large = reader.take(1)[0]
                if large > 1:
                    raise CryptoError("invalid stream region vector flag")
                reader.take(12 if large else 3)
            if not flags & 8:
                self.items['StreamData'] += 1
                return
        raise CryptoError("stream region descriptor count exceeds bound")

    def push_isr(self, packet):
        from .isr import decode
        try:
            result = decode(packet, self.schema)
        except CryptoError as error:
            self.stops[f'ISR:{error}'] += 1
            return
        self.items['ISRPacket'] += 1
        frame = result['frame']
        if self.last_isr_frame is None or ((frame - self.last_isr_frame) & 0xffffffff) < 0x80000000:
            self.last_isr_frame = frame
        for kind, count in result['skipped'].items():
            self.stops[f'ISR:{kind}'] += count
        for key, cid, frame, values in result['updates']:
            node = self.nodes.get(key)
            if node is None or node['class'] != self.schema.classes[cid]['name']:
                continue
            previous = self.isr_frames.get(key)
            if previous is None or ((frame - previous) & 0xffffffff) < 0x80000000:
                self.isr_frames[key] = frame
            versions = self.isr_property_frames.setdefault(key, {})
            for name, value in values.items():
                previous_property = versions.get(name)
                if previous_property is not None and (frame == previous_property or
                        ((frame - previous_property) & 0xffffffff) >= 0x80000000):
                    continue
                versions[name] = frame
                node['props'][name] = value
                self.property_value(key, name, value)
                self.items['ISRProperty'] += 1

    def stream_region_info(self, reader):
        # Client-only Data 0x14, 0x105961ab0 / 0x1059e90fc.
        large = reader.take(1)[0]
        if large > 1:
            raise CryptoError('invalid stream region info vector flag')
        reader.take(12 if large else 3)
        reader.take(8)
        if self.capabilities & (1 << 56):
            reader.take(4)
        self.items['StreamRegionInfo'] += 1

    def changed_attribute(self, reader):
        # DeserializedChangeAttributeItem, native 0x1057f1abc. Ordinary
        # player connections have no Studio-only tail from virtual +0x468.
        key = self.guid(reader)
        name = reader.take(reader.var(1048576))
        blob = reader.take(reader.var(1048576))
        self.attribute_value(key, name, blob)
        self.items['ChangedAttribute'] += 1

    def attribute_value(self, key, name, blob):
        """Complete attribute-change record; blob serialization is separate."""
        pass

    def push(self, packet):
        if not packet or packet[0] != 0x83:
            raise CryptoError("not a Data packet")
        self.messages += 1
        reader = Reader(packet)
        reader.take(1)
        try:
            while reader.at < len(packet):
                kind = reader.take(1)[0]
                if kind == 0:
                    if reader.at == len(packet):
                        self.complete += 1
                    else:
                        self.stops["trailing bytes"] += 1
                    return
                if kind == 2:
                    self.new(reader)
                elif kind == 3:
                    self.changed(reader)
                elif kind == 1:
                    key = self.guid(reader)
                    self._forget_node(key)
                    self.items["Removal"] += 1
                elif kind == 0x1b:
                    # DeserializedDestroyInstanceItem, native reader 0x1058d276a:
                    # raw LE32 count, then ordinary GUIDs.
                    count = reader.u32()
                    if count > 65536:
                        raise CryptoError("destroy instance count exceeds bound")
                    removed = [self.guid(reader) for _ in range(count)]
                    for key in removed:
                        self._forget_node(key)
                    self.items["DestroyInstance"] += count
                elif kind == 4:
                    reader.take(4)
                    self.items["Marker"] += 1
                elif kind == 7:
                    self.event(reader)
                elif kind == 0x13:
                    # Native 0x105806196 reads exactly two ordinary GUIDs.
                    # Their engine-side relationship is not applied here; keep
                    # parsing subsequent, independently delimited records.
                    first, second = self.guid(reader), self.guid(reader)
                    self.atomic_value(first, second)
                    self.items['AtomicReferences'] += 1
                elif kind in (0x10, 0x23):
                    value = reader.u32()
                    if kind == 0x10 and len(self.initial_states) < 32:
                        self.initial_states.append(value)
                    self.items[f"Item:{kind:#x}"] += 1
                elif kind == 0x16:
                    self.join_v2(reader)
                elif kind == 0x0d:
                    self.stream_instances(reader)
                elif kind == 0x14:
                    self.stream_region_info(reader)
                elif kind == 0x15:
                    self.changed_attribute(reader)
                elif kind == 0x19:
                    # Client dispatcher 0x105703c68 -> 0x105961c80:
                    # three raw f32, one raw f64, one raw u32 (24 bytes).
                    reader.take(24)
                    self.items['Item:0x19'] += 1
                elif kind in (5, 6):
                    self.ping(reader, kind)
                else:
                    self.stops[f"item:{kind:#x}"] += 1
                    return
        except CryptoError as error:
            self.stops[str(error)] += 1

    def character_evidence(self):
        own = self.nodes.get(self.own)
        if own and (own["class"] != "Player" or own["props"].get("UserId") != self.user_id):
            own = None
        ref = own["props"].get("Character") if own else None
        char = self.nodes.get(ref)
        children = [node for _, node in self.nodes.children(ref)] if ref is not None else []
        root = any(node["class"] in ("Part", "MeshPart") and
                   node["props"].get("Name") == b"HumanoidRootPart" for node in children)
        humanoid = any(node["class"] == "Humanoid" for node in children)
        return {"own_player_decoded": own is not None,
                "own_appearance_event_count": sum(key == self.own for key, _ in self.appearance_events),
                "character_reference_received": ref is not None,
                "character_model_received": bool(char and char["class"] == "Model"),
                "character_humanoid_received": humanoid, "character_root_received": root,
                "character_parent_received": bool(char and char["parent"] in self.nodes),
                "character_parent_is_workspace": bool(char and self.nodes.get(char["parent"], {}).get("class") == "Workspace"),
                "character_spawn_confirmed": bool(own and char and char["class"] == "Model" and humanoid and root and
                                                   self.nodes.get(char["parent"], {}).get("class") == "Workspace"),
                }

    def report(self):
        return {"messages": self.messages, "complete_messages": self.complete,
                "decoded_items": dict(self.items), "known_nodes": len(self.nodes),
                "world_node_limit": self.max_nodes,
                "known_node_classes": dict(Counter(node["class"] for node in self.nodes.values())),
                "unsupported": dict(self.stops), "events": dict(self.event_names),
                "initial_replication_states": self.initial_states,
                "unresolved_shared_references": len(self.unresolved_shared - self.shared),
                **self.character_evidence(),
                "scope": "Partial Data reader; unsupported items stop the current message."}

