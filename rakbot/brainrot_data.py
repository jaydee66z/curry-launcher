"""Literal catalog facts and the game's read-only Synchronizer client protocol."""
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import math
import re
import struct
import time
import threading
from types import MappingProxyType

from .application import string, varuint
from .brainrot import text, ordered
from .heli_wars import wire_guid
from .luau_bytecode import unpack_rsb
from .luau_static import parse


ROOT = ('ReplicatedStorage', 'Packages', 'Synchronizer')
CATALOGS = ('Animals', 'Mutations', 'Traits')
SHARED_BLOB_BUDGET = 8 * 1024 * 1024
_catalog_cache = OrderedDict()
_wire_catalog_cache = OrderedDict()
_catalog_lock = threading.Lock()


def catalog_facts(blob):
    """Share immutable facts by actual source content, bounded across versions."""
    digest = hashlib.sha256(blob).digest()
    with _catalog_lock:
        if digest in _catalog_cache:
            _catalog_cache.move_to_end(digest)
            return _catalog_cache[digest]
        facts = literals(parse(unpack_rsb(blob)))
        facts = MappingProxyType({name: MappingProxyType(row) for name, row in facts.items()})
        _catalog_cache[digest] = facts
        while len(_catalog_cache) > 12:
            _catalog_cache.popitem(last=False)
        return facts


def literals(bytecode):
    """Read literal table assignments, without running calls, loops or closures."""
    main = bytecode['functions'][bytecode['main']]
    constants = main['constants']
    returns = [i['a'] for i in main['instructions'] if i['op'] == 'RETURN' and i['b'] == 2]
    if not returns or len(set(returns)) != 1:
        raise ValueError('Unsupported catalog return shape')
    root = returns[-1]
    regs, result, conflicts = {}, {}, set()

    def constant(index):
        value = constants[index]
        return value.decode('utf-8', 'replace') if isinstance(value, bytes) else value if not isinstance(value, dict) else None

    for ins in main['instructions']:
        op, a, b = ins['op'], ins['a'], ins['b']
        if op == 'DUPTABLE':
            spec = constants[ins['d']]
            regs[a] = {constant(k): constant(v) for k, v in spec.get('table_values', []) if v >= 0}
        elif op == 'NEWTABLE':
            regs[a] = {}
        elif op == 'SETTABLEKS':
            value = regs.get(a)
            member = ins['member'].decode('utf-8', 'replace')
            parent = regs.get(b)
            if member == 'OverheadDisplayName' and isinstance(parent, dict) and isinstance(value, tuple):
                function = bytecode['functions'][value[1]]
                code = function['instructions']
                if (function['parameters'] == 1 and [i['op'] for i in code] ==
                        ['LOADK', 'MOVE', 'NAMECALL', 'CALL', 'RETURN'] and
                        code[1]['b'] == 0 and code[2].get('member') == b'format' and
                        isinstance(code[0].get('constant'), bytes)):
                    pattern = code[0]['constant'].decode('utf-8', 'replace')
                    if pattern.count('%*') == 1:
                        parent['overhead_name_format'] = pattern
            if b == root and isinstance(value, dict):
                if member in result and result[member] != value:
                    conflicts.add(member)
                result[member] = value
        elif op == 'DUPCLOSURE':
            regs[a] = ('closure', ins['constant']['closure'])
        elif op in ('GETIMPORT', 'GETTABLEKS', 'GETTABLE', 'GETTABLEN', 'GETUPVAL', 'NAMECALL',
                    'LOADK', 'LOADN', 'LOADNIL', 'LOADB', 'NEWCLOSURE', 'DUPCLOSURE'):
            regs.pop(a, None)
        elif op in ('CALL', 'CALLFB'):
            for register in range(a, a + max(1, ins['c'] - 1)):
                regs.pop(register, None)
        elif op == 'MOVE':
            if b in regs:
                regs[a] = regs[b]
            else:
                regs.pop(a, None)
    return {k: {field: value for field, value in row.items() if isinstance(field, str) and
                (value is None or type(value) in (str, int, float, bool))}
            for k, row in result.items() if k not in conflicts}


def number(value):
    if type(value) not in (int, float, Decimal) or not math.isfinite(value):
        return None
    return Decimal(str(value))


def money(value):
    value = Decimal(value)
    units = ('', 'K', 'M', 'B', 'T', 'Qa', 'Qi', 'Sx', 'Sp', 'Oc', 'No', 'Dc')
    unit = 0
    while abs(value) >= 1000 and unit < len(units) - 1:
        value /= 1000
        unit += 1
    value = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    rendered = format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')
    return '$' + rendered + units[unit]


class Sync:
    def __init__(self, world):
        self.world = world
        self.catalog = {name: {} for name in CATALOGS}
        self.sources = {}
        self.blobs, self.blob_bytes = OrderedDict(), 0
        self.announced, self.channels, self.pending, self.requested = set(), {}, {}, set()
        self.next_request = 0
        self.invocation = 20000
        self.dirty = True
        self.models = {}
        self.replicator_started = False
        self.replicators = {}
        self.replicator_names = {}
        self.queued = {}
        self.catalog_ready = False
        self.manifest_changed_at = time.monotonic()
        self._road_population = frozenset()
        self._road_population_at = time.monotonic()
        self._replicator_events = self._request_events = None
        self.inventory_extra = None
        self._plot_changed_at={}
        self._plot_animals_ready={}

    def observe(self, key, node):
        if node is None:
            self.models.pop(key, None)
        elif node['class'] == 'Model':
            from .brainrot_wire import attributes
            try:
                props = attributes(node['props'].get('AttributesReplicate', b''))
            except ValueError:
                props = {}
            if isinstance(props.get(b'Index'), bytes):
                self.models[key] = props
            else:
                self.models.pop(key, None)
        self.dirty = True

    def attribute(self, key, name, blob):
        node = self.world.nodes.get(key)
        if node is None or node['class'] != 'Model':
            return
        from .brainrot_wire import attributes
        props = dict(self.models.get(key, {}))
        try:
            if blob in (b'', b'\0'):
                props.pop(name, None)
            else:
                props.update(attributes(struct.pack('<II', 1, len(name)) + name + blob))
        except ValueError:
            return
        if isinstance(props.get(b'Index'), bytes):
            self.models[key] = props
        else:
            self.models.pop(key, None)
        self.dirty = True

    def path(self, key):
        parts, seen = [], set()
        while key in self.world.nodes and key not in seen and len(parts) < 32:
            seen.add(key)
            node = self.world.nodes[key]
            if node['class'] == 'DataModel':
                break  # Service paths do not depend on retention of the root.
            parts.append(text(node['props'].get('Name')) or node['class'])
            key = node['parent']
        return tuple(reversed(parts))

    def shared(self, digest, blob):
        if digest in self.blobs or len(blob) > 1048576:
            return
        if self.catalog_ready and len(blob) > 256:
            return
        protected = set(self.sources.values())
        while self.blobs and self.blob_bytes + len(blob) > SHARED_BLOB_BUDGET:
            # Large cached scripts/meshes can arrive before their catalog
            # instance paths. Do not evict the tiny Animal tag behind them.
            victim = next((key for key, value in self.blobs.items()
                           if key not in protected and len(value) > 256), None)
            if victim is None:
                victim = next((key for key in self.blobs if key not in protected), None)
            if victim is None:
                return  # All retained blobs are required source facts.
            previous = self.blobs.pop(victim)
            self.blob_bytes -= len(previous)
        self.blobs[digest] = blob
        self.blob_bytes += len(blob)
        self.dirty = True
        if digest in self.sources.values():
            # A large SharedString block can otherwise evict an already known
            # catalog before the next network-loop poll gets a chance to parse it.
            self.load_catalogs()

    def load_catalogs(self):
        for key in tuple(self.sources):
            node = self.world.nodes.get(key)
            if node is None:
                del self.sources[key]
                continue
            path = self.path(key)
            if len(path) != 3 or path[:2] != ('ReplicatedStorage', 'Datas') or path[2] not in CATALOGS:
                continue
            digest = self.sources[key]
            cache_key = (path[2], digest)
            with _catalog_lock:
                table = _wire_catalog_cache.get(cache_key)
                if table is not None:
                    _wire_catalog_cache.move_to_end(cache_key)
            if table is not None:
                self.catalog[path[2]] = table
                del self.sources[key]
                self.dirty = True
                continue
            blob = self.blobs.get(digest)
            if blob is None:
                # Source was declared by this server, but its verified bytes
                # can already be on disk; no redundant wire record is needed.
                blob = getattr(self.world.client, 'shared_cache_advertised', {}).get(digest)
            if blob is None:
                continue
            try:
                table = catalog_facts(blob)
            except (ValueError, IndexError, KeyError, UnicodeError, TypeError, AttributeError):
                table = {}
            self.catalog[path[2]] = table
            if (isinstance(table, MappingProxyType) and len(digest) == 16 and
                    hashlib.blake2b(blob, digest_size=16).digest() == digest):
                with _catalog_lock:
                    _wire_catalog_cache[cache_key] = table
                    _wire_catalog_cache.move_to_end(cache_key)
                    while len(_wire_catalog_cache) > 12:
                        _wire_catalog_cache.popitem(last=False)
            del self.sources[key]
            self.dirty = True
        if not self.catalog_ready and all(self.catalog.values()):
            self.catalog_ready = True
            # Catalogs are facts now; release opaque script/mesh blobs. Keep
            # small tag strings needed by the indexed road-animal records.
            for digest, blob in list(self.blobs.items()):
                if len(blob) > 256:
                    del self.blobs[digest]
                    self.blob_bytes -= len(blob)

    def event(self, name, key, arguments):
        path = self.path(key)
        if name == 'RemoteEvent.OnClientEvent' and path == ROOT + ('CommunicationRoute',):
            for action in (arguments[0] if arguments and isinstance(arguments[0], list) else []):
                if not isinstance(action, list):
                    continue
                for item in action:
                    if not isinstance(item, list) or len(item) != 2 or not isinstance(item[1], bytes):
                        continue
                    channel = text(item[1])
                    if not re.fullmatch(r'[0-9a-fA-F-]{36}', channel):
                        continue
                    if item[0] == b'ListenerAdded' and len(self.announced) < 64:
                        if channel not in self.announced:
                            self.manifest_changed_at = time.monotonic()
                        self.announced.add(channel)
                    elif item[0] == b'ListenerRemoved':
                        self.manifest_changed_at = time.monotonic()
                        self.announced.discard(channel)
                        self.channels.pop(channel, None)
                        self._plot_changed_at.pop(channel,None)
                        self._plot_animals_ready.pop(channel,None)
                        self.requested.discard(channel)
                        self.queued.pop(channel, None)
                        self.pending = {i: c for i, c in self.pending.items() if c != channel}
                        self.dirty = True
        elif name == 'RemoteFunction.RemoteOnInvokeSuccess' and path == ROOT + ('RequestData',):
            if arguments and arguments[0] in self.pending:
                channel = self.pending.pop(arguments[0])
                values = arguments[1] if len(arguments) == 2 else []
                if channel in self.announced and isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict):
                    self.channels[channel] = values[0]
                    previous_owner=values[0].get(b'Owner')
                    animals_changed=False
                    for action in self.queued.pop(channel, []):
                        if apply_diff(self.channels[channel], action):
                            path=action[0].split(b'.') if isinstance(action[0],bytes) else action[0]
                            animals_changed|=bool(path and path[0] in (b'AnimalList','AnimalList'))
                    self._plot_changed_at[channel]=time.monotonic()
                    self._plot_animals_ready[channel]=previous_owner==values[0].get(b'Owner') or animals_changed
                    self.dirty = True
        elif name == 'RemoteFunction.RemoteOnInvokeError' and path == ROOT + ('RequestData',) and arguments:
            self.pending.pop(arguments[0], None)
        elif (name == 'RemoteEvent.OnClientEvent' and len(path) == 5 and
                path[:4] == ROOT + ('Channel',) and path[4] in self.announced):
            channel = path[4]
            queue = arguments[0][0] if arguments and isinstance(arguments[0], list) and arguments[0] else []
            if isinstance(queue, list):
                state=self.channels.get(channel,{})
                previous_owner=state.get(b'Owner')
                animals_changed=False
                for action in queue:
                    if isinstance(action, list):
                        if channel in self.channels:
                            if apply_diff(self.channels[channel], action) and action:
                                path=action[0].split(b'.') if isinstance(action[0],bytes) else action[0]
                                animals_changed|=bool(path and path[0] in (b'AnimalList','AnimalList'))
                        elif len(self.queued.setdefault(channel, [])) < 64:
                            self.queued[channel].append(action)
                if previous_owner!=state.get(b'Owner') or animals_changed:
                    self._plot_changed_at[channel]=time.monotonic()
                    # Owner can arrive ahead of the replacement AnimalList.
                    # Do not report the previous owner's pets as the new base.
                    self._plot_animals_ready[channel]=animals_changed
                self.dirty = True
        elif name == 'RemoteEvent.OnClientEvent' and path == ('ReplicatedStorage', '__ReplicatorInternal', 'RemoteEvent'):
            from .brainrot_wire import buff
            values = arguments[0] if arguments and isinstance(arguments[0], list) else []
            if values and isinstance(values[0], bytes):
                try:
                    packets = buff(values[0], values[1] if len(values) > 1 and isinstance(values[1], list) else ())
                except ValueError:
                    return
                for packet in packets if isinstance(packets, list) else []:
                    if not isinstance(packet, list) or len(packet) < 2:
                        continue
                    if type(packet[1]) not in (bytes, int):
                        continue
                    if packet[0] == b'\0' and len(packet) == 4:
                        self.replicator_names[packet[1]] = packet[2]
                        if packet[2] == b'AnimalTraits' and isinstance(packet[3], dict):
                            self.replicators[b'AnimalTraits'] = packet[3]
                            self.dirty = True
                    elif packet[0] == b'\1' and len(packet) == 3 and self.replicator_names.get(packet[1]) == b'AnimalTraits':
                        try:
                            self.replicators[b'AnimalTraits'] = merge_patch(self.replicators.get(b'AnimalTraits', {}), packet[2])
                        except ValueError:
                            continue
                        self.dirty = True
                    elif packet[0] == b'\2' and self.replicator_names.pop(packet[1], None) == b'AnimalTraits':
                        self.replicators.pop(b'AnimalTraits', None)
                        self.dirty = True

    def poll(self):
        self.load_catalogs()
        now = time.monotonic()
        fast = getattr(self.world.client, 'scan_once', False) is True
        if now < self.next_request or self.world.own is None or not fast and 13 not in self.world.initial_states:
            return
        if not self.replicator_started:
            remotes = [key for key, node in self.world.nodes.class_items('RemoteEvent')
                       if self.path(key) == ('ReplicatedStorage', '__ReplicatorInternal', 'RemoteEvent')]
            if self._replicator_events is None:
                self._replicator_events = [i for i, event in enumerate(self.world.schema.events)
                    if self.world.schema.classes[event['class_id']]['name'] == 'RemoteEvent'
                    and event['name'] == 'OnRemoteServerEvent' and [a['type'] for a in event['arguments']] == [29]]
            events = self._replicator_events
            if len(remotes) == len(events) == 1:
                self.world.client._send(b'\x83\x07' + wire_guid(remotes[0]) + struct.pack('<H', events[0]) + b'\0\0', 3)
                self.replicator_started = True
        waiting = self.announced - self.requested
        if not waiting or len(self.pending) >= 16:
            return
        remotes = [key for key, node in self.world.nodes.class_items('RemoteFunction')
                   if node['props'].get('Name') == b'RequestData' and self.path(key) == ROOT + ('RequestData',)]
        if self._request_events is None:
            self._request_events = [i for i, event in enumerate(self.world.schema.events)
                if self.world.schema.classes[event['class_id']]['name'] == 'RemoteFunction'
                and event['name'] == 'RemoteOnInvokeServer'
                and [a['type'] for a in event['arguments']] == [10, 28, 29]]
        events = self._request_events
        if len(remotes) != 1 or len(events) != 1:
            return
        count = min(16 if fast else 1, 16 - len(self.pending))
        records = []
        for channel in sorted(waiting)[:count]:
            self.invocation += 1
            packet = (b'\x83\x07' + wire_guid(remotes[0]) + struct.pack('<H', events[0]) +
                      varuint(self.invocation * 2) + wire_guid(self.world.own) + varuint(1) + b'\x02' + string(channel) + b'\0')
            records.append(packet[1:-1])
            self.requested.add(channel)
            self.pending[self.invocation] = channel
        # One ordinary Data stream with several Event items, not one encrypted
        # UDP datagram and ACK bookkeeping round-trip per channel.
        self.world.client._send(b'\x83' + b''.join(records) + b'\0', 3)
        self.next_request = now + (0.05 if fast else 0.5)

    def rows(self):
        result = []
        for channel, state in self.channels.items():
            result.extend(self.plot_rows(channel))
        traits_state = self.replicators.get(b'AnimalTraits')
        if isinstance(traits_state, dict):
            traits = traits_state.get(b'traits', {})
            for key, animal in self.models.items():
                node = self.world.nodes.get(key)
                if node is None or b'Animal' not in self.blobs.get(node['props'].get('Tags'), b'').split(b'\0'):
                    continue
                uid = node['props'].get('Name')
                if not isinstance(uid, bytes):
                    continue
                animal = {**animal, b'Traits': traits.get(uid, []) if isinstance(traits, dict) else []}
                row = self.row(animal, 'road:' + text(uid), 'replicated-animal')
                if row:
                    result.append(row)
        self.dirty = False
        return ordered(result)

    def plot_rows(self,channel):
        animals=self.channels[channel].get(b'AnimalList')
        values=enumerate(animals,1) if isinstance(animals,list) else animals.items() if isinstance(animals,dict) else ()
        result=[]
        for slot,animal in values:
            if not isinstance(animal,dict) or animal.get(b'Steal') or animal.get(b'Machine'):
                continue
            row=self.row(animal,'sync:'+channel+':'+str(slot),'synchronizer')
            if row:
                result.append(row)
        return result

    def joined_plot_rows(self,user_id,now):
        channels=[]
        for channel,state in self.channels.items():
            owner=state.get(b'Owner')
            if not isinstance(owner,(tuple,list)) or len(owner)!=2:
                continue
            try:
                player=self.world.nodes.get(tuple(owner))
            except TypeError:
                continue
            if not player or player['class']!='Player' or player['props'].get('UserId')!=user_id:
                continue
            if (not self._plot_animals_ready.get(channel,False) or
                    not isinstance(state.get(b'AnimalList'),(list,dict)) or
                    now-self._plot_changed_at.get(channel,now)<.15):
                return None
            channels.append(channel)
        if not channels:
            return None
        return channels,[row for channel in channels for row in self.plot_rows(channel)]

    def initial_ready(self, now=None):
        now = time.monotonic() if now is None else now
        complete = bool(self.catalog_ready and 13 in self.world.initial_states and self.announced and
                        self.announced <= self.channels.keys() and not self.pending and
                        b'AnimalTraits' in self.replicators)
        if not complete:
            return False
        minimum = getattr(self.world.client, 'scan_min_road_models', 0)
        if type(minimum) is int and minimum > 0:
            population = self.road_population()
            if population != self._road_population:
                self._road_population, self._road_population_at = population, now
            settle = getattr(self.world.client, 'scan_settle_seconds', 0.3)
            if len(population) < minimum or now - self._road_population_at < settle:
                return False
        if now - self.manifest_changed_at >= 2:
            return True
        if getattr(self.world.client, 'scan_once', False) is not True:
            return False
        # Only the server-announced listeners belong to this client's sync.
        # Other replicated channel remotes can exist without an accessible
        # listener; do not query them or block the completed announced set.
        inventory = set()
        for key, node in self.world.nodes.class_items('RemoteEvent'):
            name = node['props'].get('Name')
            if isinstance(name, bytes) and re.fullmatch(rb'[0-9a-fA-F-]{36}', name):
                channel = name.decode('ascii')
                if self.path(key) == ROOT + ('Channel', channel):
                    inventory.add(channel)
        self.inventory_extra = len(inventory - self.announced)
        return self.announced <= inventory and now - self.manifest_changed_at >= 0.1

    def live_ready(self):
        # A changing conveyor can legitimately have fewer than the initial
        # population threshold. Preserve channel completeness after startup.
        return bool(self.catalog_ready and 13 in self.world.initial_states and self.announced and
            self.announced<=self.channels.keys() and not self.pending and b'AnimalTraits' in self.replicators)

    def road_population(self):
        return frozenset(key for key in self.models
            if key in self.world.nodes and b'Animal' in self.blobs.get(
                self.world.nodes[key]['props'].get('Tags'), b'').split(b'\0'))

    def row(self, animal, identity, source):
        name = text(animal.get(b'Index'))
        data = self.catalog['Animals'].get(name)
        if not data or data.get('HideOverhead') or data.get('HideGeneration'):
            return None
        base = number(data.get('Generation'))
        if base is None or base < 0:
            return None
        mutation = text(animal.get(b'Mutation'))
        modifier = Decimal(1)
        if mutation:
            definition = self.catalog['Mutations'].get(mutation)
            if not definition or number(definition.get('Modifier')) is None:
                return None
            modifier += number(definition['Modifier'])
        traits = animal.get(b'Traits') or []
        if not isinstance(traits, (list, dict)):
            return None
        sleepy = False
        display_name = data.get('DisplayName') or name
        for trait in (traits.values() if isinstance(traits, dict) else traits):
            trait_name = text(trait)
            definition = self.catalog['Traits'].get(trait_name)
            if not definition or trait_name != 'Sleepy' and number(definition.get('MultiplierModifier')) is None:
                return None
            if trait_name == 'Sleepy':
                sleepy = True
            else:
                modifier += number(definition['MultiplierModifier'])
            if definition.get('overhead_name_format'):
                display_name = definition['overhead_name_format'].replace('%*', display_name)
        income = (base * modifier * (Decimal('0.5') if sleepy else 1)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return {'id': identity, 'DisplayName': display_name,
            'Generation': money(income) + '/s', 'generation_value': str(income),
            'Mutation': self.catalog['Mutations'].get(mutation, {}).get('DisplayText') if mutation else None,
            'Price': money(data['Price']) if not data.get('HidePrice') and number(data.get('Price')) is not None else None,
            'Rarity': None if data.get('HideRarity') else data.get('Rarity'),
            'Stolen': None, 'source': source}


def apply_diff(state, action):
    """Channel's Changed/Array*/Dictionary* queue, with one-based array indices."""
    if len(action) < 2 or not isinstance(action[0], (bytes, list)):
        return False
    path = action[0].split(b'.') if isinstance(action[0], bytes) else action[0]
    if not 1 <= len(path) <= 24:
        return False
    current, parent, key = state, None, None
    for part in path:
        parent = current
        key = int(part) - 1 if isinstance(parent, list) and (type(part) is int or isinstance(part, bytes) and part.isdigit()) else part
        if isinstance(parent, dict) and isinstance(key, str):
            key = key.encode()
        if isinstance(parent, dict):
            current = parent.get(key)
        elif isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
            current = parent[key]
        else:
            return False
    value = action[2] if len(action) > 2 else None
    index = action[3] if len(action) > 3 else None
    if type(index) is float and math.isfinite(index) and index.is_integer():
        index = int(index)
    if action[1] == b'Changed':
        if isinstance(parent, dict):
            if value is None:
                parent.pop(key, None)
            else:
                parent[key] = value
        elif isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
            parent[key] = value
        else:
            return False
    elif action[1] in (b'ArrayInsert', b'ArrayRemoved'):
        if not isinstance(current, list) or type(index) is not int or not 1 <= index <= len(current) + (action[1] == b'ArrayInsert'):
            return False
        if action[1] == b'ArrayInsert' and len(current) < 4096:
            current.insert(index - 1, value)
        elif action[1] == b'ArrayRemoved':
            current.pop(index - 1)
    elif action[1] in (b'DictionaryInsert', b'DictionaryRemoved'):
        if not isinstance(current, dict) or type(index) not in (bytes, int, float, bool):
            return False
        if action[1] == b'DictionaryInsert' and len(current) < 4096:
            current[index] = value
        elif action[1] == b'DictionaryRemoved':
            current.pop(index, None)
    else:
        return False
    return True


def merge_patch(previous, patch, depth=0):
    if depth > 24:
        raise ValueError('Replicator patch nesting limit')
    if isinstance(patch, dict) and patch.get(b'__none') == b'__none':
        return None
    if not isinstance(previous, (dict, list)) or not isinstance(patch, (dict, list)):
        return patch
    result = previous.copy()
    values = enumerate(patch, 1) if isinstance(patch, list) else patch.items()
    for key, value in values:
        if isinstance(result, list):
            if isinstance(key, bytes) and key.isdigit():
                key = int(key)
            if type(key) is not int or not 1 <= key <= len(result) + 1 or key > 4096:
                raise ValueError('Unsupported array patch')
            old = result[key - 1] if key <= len(result) else None
            updated = merge_patch(old if old is not None else {}, value, depth + 1)
            if key <= len(result):
                result[key - 1] = updated
            else:
                result.append(updated)
        elif len(result) <= 4096:
            updated = merge_patch(result.get(key, {}), value, depth + 1)
            if updated is None:
                result.pop(key, None)
            else:
                result[key] = updated
        else:
            raise ValueError('Replicator dictionary size limit')
    return result
