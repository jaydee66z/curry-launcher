"""Character initialization with structural spawn evidence from replication."""
import math
import queue
import time

from .native_client import NativeClient, milliseconds
from .native_crypto import CryptoError
from .replication import Inspector
from .data_ping import pong
from .player_probe import request_character
from .heli_wars import team_request
from .commands import CommandError, PlayerUnavailable, execute, position_for, resolve_player, root_for
from .physics import stationary_packet


CHAT_ACCESS_EVENTS = {
    'Chat.ReconcileCommunicationAccessCompleted': ('Chat', 'communication_status'),
    'TextChatService.ServerToClientPresetChatUserAccessChangedSignal': ('TextChatService', 'preset_chat_status'),
}
_PLAIN_WIRE_SIZES = {9: 1, 11: 4, 12: 8, 13: 8, 14: 16, 18: 2,
                     19: 12, 20: 3, 21: 8, 22: 12, 37: 8, 40: 16, 55: 8}
_SCAN_CLASSES = frozenset(('Player', 'DataModel', 'Workspace', 'ReplicatedStorage', 'Model', 'Folder',
    'ModuleScript', 'RemoteEvent', 'RemoteFunction', 'BillboardGui', 'Frame',
    'TextLabel', 'TextButton', 'TextBox', 'Chat', 'TextChatService', 'TextChannel', 'TextSource'))
_SCAN_NAMES = {
    'Folder': (b'Packages', b'Datas', b'Synchronizer', b'Channel', b'__ReplicatorInternal', b'Debris', b'TextChannels'),
    'ModuleScript': (b'Animals', b'Mutations', b'Traits', b'Synchronizer', b'Channel'),
}


class World(Inspector):
    native_scan_projection = True
    scan_projection_retention = True

    def __init__(self, schema, user_id, client):
        self.brainrot_mode = bool(getattr(client, 'on_brainrots', None))
        self.scan_only = self.brainrot_mode and getattr(client, 'scan_once', False) is True
        self._scan_native_plan = None
        self._scan_native_names = None
        self._scan_native_dynamic = None
        self._scan_change_plan = None
        capabilities = getattr(getattr(client, 'open', None), '_negotiated_capabilities', 0)
        super().__init__(schema, user_id, capabilities=capabilities if type(capabilities) is int else 0)
        self.client = client
        self.chat_source_order = {}
        self._chat_source_serial = 0
        self.position_observed = {}
        self.position_sources = {}
        self.region_observed = {}
        self.isr_received_at = None
        from .brainrot import Scanner
        self.brainrot_scanner = Scanner(self) if self.brainrot_mode else None
        from .brainrot_data import Sync
        self.brainrot_sync = Sync(self) if self.brainrot_mode else None

    def new(self, reader, *, joined=False, deferred_shared=None):
        if self.scan_only and self.native_scan_projection and joined and hasattr(reader, 'project_new'):
            self._init_scan_plan()
            record = reader.project_new(self._scan_native_plan, self._scan_native_names)
            if record is not None:
                key, cid, props, parent, hashes = record
                self._commit_new(key, cid, props, parent, set(hashes) - self.shared,
                                 joined=True, deferred_shared=deferred_shared)
                return
        super().new(reader, joined=joined, deferred_shared=deferred_shared)

    def _init_scan_plan(self):
        if self._scan_native_plan is None:
            dynamic_types = tuple(row[0] for row in getattr(self.schema, 'dynamic_types', ()))
            self._scan_native_dynamic = dynamic_types
            self._scan_native_plan = tuple((bytes(p['type'] for p in c['properties']),
                bytes(self.keep_property(c['name'], p['name']) for p in c['properties']),
                tuple(p['name'] for p in c['properties']),
                self.scan_class_policy(c['name']), dynamic_types)
                for c in self.schema.classes)
            self._scan_native_names = tuple(n.encode('utf-8') for n in self.schema.string_tables[1])
            properties = self.schema.properties + [{'name': 'Parent', 'type': 28}]
            self._scan_change_plan = (bytes(p['type'] for p in properties), tuple(p['name'] for p in properties))

    def scan_class_policy(self, name):
        return _SCAN_NAMES.get(name, name in _SCAN_CLASSES) if self.scan_projection_retention else True

    def changed(self, reader):
        if (self.scan_only and self.native_scan_projection and self._scan_change_plan is not None
                and hasattr(reader, 'skip_changes')):
            types, names = self._scan_change_plan
            skipped, counts = reader.skip_changes(types, names, self.nodes, self._scan_native_names,
                                                  self._scan_native_dynamic, self.shared)
            if skipped:
                self.items['ChangedProperty'] += skipped
                self.property_names.update(counts)
                return
        super().changed(reader)

    def new_many(self, reader, count, *, deferred_shared=None):
        if not (self.scan_only and self.native_scan_projection and hasattr(reader, 'project_many')):
            return super().new_many(reader, count, deferred_shared=deferred_shared)
        self._init_scan_plan()
        while count:
            rows, parsed = reader.project_many(self._scan_native_plan, self._scan_native_names, count, self.nodes)
            for record in rows:
                if len(record) == 3:
                    dropped, keys, hashes = record
                    pending = hashes - self.shared
                    if pending:
                        self._joined_shared(pending, deferred_shared)
                    for key in keys:
                        if key in self.nodes:
                            self._forget_node(key)
                    self.items['NewInstance'] += dropped
                    self.items['WorldInstanceProjectedOut'] += dropped
                else:
                    key, cid, props, parent, hashes = record
                    pending = set(hashes) - self.shared if hashes else set()
                    self._commit_new(key, cid, props, parent, pending,
                                     joined=True, deferred_shared=deferred_shared)
            self.items['NativeProjectedInstance'] += parsed
            count -= parsed
            if count:
                # Exact boundary fallback; never search for the next record.
                super().new(reader, joined=True, deferred_shared=deferred_shared)
                count -= 1

    def _remember_node(self, key, node):
        if self.scan_only and self.scan_projection_retention and (node['class'] not in _SCAN_CLASSES or
                node['class'] in _SCAN_NAMES and node['props'].get('Name') not in _SCAN_NAMES[node['class']]):
            if node['props'].get('Name') != b'FastOverheadTemplate':
                if key in self.nodes:
                    self._forget_node(key)
                self.items['WorldInstanceProjectedOut'] += 1
                return
        super()._remember_node(key, node)

    def keep_property(self, class_name, name):
        if not self.scan_only or class_name == 'Player':
            return True
        if name in ('Parent', 'Name', 'Visible', 'Enabled'):
            return True  # All ancestor paths and visibility remain available.
        if class_name == 'Model' and name in ('AttributesReplicate', 'Tags'):
            return True
        if class_name == 'ModuleScript' and name == 'Source':
            return True
        return class_name in ('TextLabel', 'TextButton', 'TextBox') and name == 'Text'

    def discard_value(self, reader, kind, pending, **options):
        if not self.scan_only:
            return super().discard_value(reader, kind, pending, **options)
        if self.native_scan_projection and self._scan_native_names is not None and hasattr(reader, 'skip_value'):
            hashes = reader.skip_value(kind, self._scan_native_names, self._scan_native_dynamic,
                                       options.get('cached_content', False))
            if hashes is not None:
                pending.update(h for h in hashes if h not in self.shared)
                return
        # Only types whose ordinary reader has no additional semantic checks.
        # Complex/cached/shared values still go through the complete reader.
        size = _PLAIN_WIRE_SIZES.get(kind)
        if size is not None:
            reader.skip(size)
        elif kind in (2, 8):
            reader.skip(reader.var(1048576))
        elif kind in (7, 10, 34, 44):
            reader.var(2**64 - 1 if kind == 44 else 2**32 - 1)
        elif kind == 28:
            if reader.var(2**32 - 1):
                reader.skip(4)
        elif kind == 27:
            reader.skip(12)
            if reader.u8() == 0:
                reader.skip(6)
        elif kind == 51:
            rotation = reader.u8()
            if rotation & 128:
                if not rotation & 127:
                    reader.skip(6)
                reader.skip(12)
        else:
            super().discard_value(reader, kind, pending, **options)

    def _important_node(self, node):
        # Overheads must survive maps that exceed the ordinary retention budget.
        return (super()._important_node(node) or self.brainrot_mode and
                (node['class'] in ('ModuleScript', 'BillboardGui', 'Frame', 'TextLabel', 'TextButton', 'TextBox') or
                 node['props'].get('Name') in (b'FastOverheadTemplate', b'AnimalOverhead', b'Animals', b'Mutations', b'Traits')))

    def value(self, reader, kind, pending, **options):
        if self.brainrot_mode and kind in (46, 47):
            digest = reader.take(16)
            if digest not in self.shared:
                pending.add(digest)
            return digest
        return super().value(reader, kind, pending, **options)

    def shared_value(self, digest, blob):
        cache = getattr(self.client, 'shared_cache', None)
        if self.scan_only and cache is not None:
            cache.add(digest, blob)
        if self.brainrot_sync is not None:
            self.brainrot_sync.shared(digest, blob)

    def cached_shared_value(self, digest):
        # Advertised cache knowledge is not the per-connection wire set.
        # The first cached=1 record still has to be consumed from its stream.
        if self.scan_only:
            return getattr(self.client, 'shared_cache_advertised', {}).get(digest)
        return None

    def push_isr(self, packet):
        if self.scan_only:
            return  # Physics has no input into catalog/channel/overhead scans.
        before = self.items['ISRPacket']
        super().push_isr(packet)
        if self.items['ISRPacket'] > before:
            self.isr_received_at = time.monotonic()

    def instance_value(self, key, node):
        # JoinData may contain a second Player with this UserId. The initial
        # authenticated record identifies this connection's local Player.
        local_key = getattr(self.client, 'local_player_guid', None)
        local_node = self.nodes.get(local_key)
        if (local_node is not None and local_node['class'] == 'Player' and
                local_node['props'].get('UserId') == self.user_id):
            self.own = local_key
        joined=getattr(self.client,'_brainrot_player_changed',None)
        if joined is not None:
            joined(key,node)
        if node['class'] == 'TextSource' and node['props'].get('UserIdReplicated') == self.user_id:
            self._chat_source_serial += 1
            self.chat_source_order[key] = self._chat_source_serial
        if self.brainrot_scanner is not None:
            self.brainrot_scanner.observe(key, node)
            self.brainrot_sync.observe(key, node)
            source = node['props'].get('Source')
            if (node['class'] == 'ModuleScript' and node['props'].get('Name') in (b'Animals', b'Mutations', b'Traits')
                    and isinstance(source, bytes) and len(source) == 16):
                self.brainrot_sync.sources[key] = source
        if self.scan_only:
            return
        self.isr_frames.pop(key, None)
        if 'ChararacterRegionId' in node['props']:
            self.region_observed[key] = time.monotonic()
        else:
            self.region_observed.pop(key, None)
        if isinstance(node['props'].get('CFrame'), dict):
            self.position_observed[key] = time.monotonic()
            self.position_sources[key] = 'CFrame'
        else:
            self.position_observed.pop(key, None)
            self.position_sources.pop(key, None)

    def removal_value(self, key):
        joined=getattr(self.client,'_brainrot_player_changed',None)
        if joined is not None:
            joined(key,None)
        self.chat_source_order.pop(key, None)
        if self.brainrot_scanner is not None:
            self.brainrot_scanner.observe(key)
            self.brainrot_sync.observe(key, None)
        self.position_observed.pop(key, None)
        self.position_sources.pop(key, None)
        self.isr_frames.pop(key, None)
        self.region_observed.pop(key, None)

    def property_value(self, key, name, value):
        if name=='UserId':
            joined=getattr(self.client,'_brainrot_player_changed',None)
            if joined is not None:
                joined(key,self.nodes.get(key))
        if self.brainrot_scanner is not None:
            self.brainrot_scanner.changed(key, name)
            if name in ('AttributesReplicate', 'Tags'):
                if name == 'AttributesReplicate':
                    self.brainrot_sync.observe(key, self.nodes.get(key))
                else:
                    self.brainrot_sync.dirty = True
        if name == 'ChararacterRegionId':
            self.region_observed[key] = time.monotonic()
        if name in ('CFrame', 'ReplicationPV') and isinstance(value, dict):
            self.position_observed[key] = time.monotonic()
            self.position_sources[key] = name
            self.client._observe_position(key, value.get('position'))

    def ping_value(self, kind, flags, timestamp, tick, large):
        if kind == 5 and flags == 0 and self.client.own_player_record_received:
            prepared = milliseconds() & 0xffffffff
            self.client._send(pong(timestamp, tick, self.client.received_tick, prepared,
                                   milliseconds() & 0xffffffff, large=large), 3)
            self.client.data_pongs_sent += 1

    def attribute_value(self, key, name, blob):
        if self.brainrot_sync is not None:
            self.brainrot_sync.attribute(key, name, blob)

    def event_value(self, name, key, arguments):
        if self.brainrot_sync is not None:
            self.brainrot_sync.event(name, key, arguments)
        self.client._observe_chat_event(name, key, arguments)
        request = self.client.team_request
        if request and key == request['remote'] and arguments and arguments[0] == request['invocation_id']:
            if name == 'RemoteFunction.RemoteOnInvokeSuccess':
                self.client.team_reply = 'success'
            elif name == 'RemoteFunction.RemoteOnInvokeError':
                self.client.team_reply = 'error'


class GameClient(NativeClient):
    def __init__(self, info, *, on_player=None, on_character=None, worker_factory=None,
                 commands=None, on_command=None, on_brainrots=None, scan_once=False, world_factory=None):
        super().__init__(info, application_stage='ticket', on_player=on_player)
        self.world = None
        self.worker = None
        self.worker_factory = worker_factory
        self.world_factory = world_factory
        self.on_character = on_character
        self.on_brainrots = on_brainrots
        self._brainrot_poll_at = 0
        self._brainrot_rows = None
        self.scan_once = scan_once
        # Observed profile: an established road population of about 13 models.
        # Do not publish a plots-only snapshot while the initial road streams in.
        self.scan_min_road_models = 12 if scan_once and info.place_id == 109983668079237 else 0
        self.scan_settle_seconds = 0.05 if scan_once else 0.3
        self.scan_complete = False
        self.scan_milestones = {}
        self.scan_stalled = False
        self._scan_progress = None
        self._scan_progress_at = 0
        self._scan_road_highwater = 0
        self.on_scan_progress = None
        self._scan_progress_emit_at = 0
        self._brainrot_complete = False
        self.received_tick = 0
        self.data_pongs_sent = 0
        self.execution_responses_sent = 0
        self.character_request_sent = False
        self.team_request = None
        self.team_reply = None
        self.spawn_ever_confirmed = False
        self._announced_character = None
        self.commands = commands
        self.on_command = on_command
        self.last_teleport = None
        self._pending_teleport = None
        self._physics_sequence = 0
        self._last_teleport_at = float('-inf')
        self._physics_intent = None
        self._physics_at = 0
        self._isr_out_frame = None
        self._refine_teleport = None
        self.physics_packets_sent = 0
        self._loop_tp = None
        self._physics_layout = {}
        self._pending_chat = {}
        self._queued_chat = {}
        self._chat_poll_at = 0
        self.last_chat = None
        self._last_chat_at = float('-inf')
        self._last_chat_wire_at = float('-inf')
        self._chat_loaded_service = None
        self.chat_messages_sent = 0
        self.chat_messages_confirmed = 0
        self.chat_access = {'communication_status': None, 'preset_chat_status': None}
        self._chat_universe_service = None

    def _command_result(self, result):
        if result is not None and self.on_command:
            self.on_command(result)

    def _poll(self):
        if self.commands is not None:
            for _ in range(8):
                try:
                    line = self.commands.get_nowait()
                except queue.Empty:
                    break
                try:
                    result = execute(self, line)
                except CommandError as error:
                    result = {'command': 'error', 'message': str(error)}
                self._command_result(result)
                if result and result.get('state') == 'closing':
                    self.stop_loop()
                    return False
        if not self.scan_once:
            self._poll_loop()
            self._maintain_physics()
            self._poll_refinement()
            self._expire_chat()
            self._poll_chat()
        self._poll_brainrots()
        if self.scan_once and self.scan_complete and not getattr(self, 'persistent_scan', False):
            self.reason = 'scan_complete'
            return False
        if self.scan_once and self.scan_stalled:
            self.reason = 'initial_scan_stalled'
            return False
        if self._pending_teleport and time.monotonic() >= self._pending_teleport['deadline']:
            self.last_teleport['state'] = 'unconfirmed'
            self._pending_teleport = None
            self._command_result({'command': 'teleport', **self.last_teleport})
        return True

    def _poll_brainrots(self):
        now = time.monotonic()
        if not self.on_brainrots or self.world is None or now < self._brainrot_poll_at:
            return
        interval=getattr(self,'scan_interval',0.5)
        self._brainrot_poll_at = now + (interval if getattr(self,'persistent_scan',False) and self.scan_complete else 0.025 if self.scan_once else 1)
        scanner = self.world.brainrot_scanner
        sync = self.world.brainrot_sync
        sync.poll()
        if self.scan_once:
            elapsed = round(now - self._started_at, 4)
            self._scan_road_highwater = max(self._scan_road_highwater,
                                           min(len(sync.road_population()), self.scan_min_road_models))
            conditions = {'catalogs': sync.catalog_ready, 'state13': 13 in self.world.initial_states,
                          'manifest': bool(sync.announced), 'traits': b'AnimalTraits' in sync.replicators,
                          'channels': bool(sync.announced and sync.announced <= sync.channels.keys() and not sync.pending),
                          'road_population': len(sync.road_population()) >= self.scan_min_road_models}
            for name, arrived in conditions.items():
                if arrived:
                    self.scan_milestones.setdefault(name, elapsed)
            progress = (tuple(len(sync.catalog[name]) for name in ('Animals', 'Mutations', 'Traits')),
                        bool(self.world.own), 13 in self.world.initial_states,
                        frozenset(sync.announced), frozenset(sync.channels), frozenset(sync.pending),
                        b'AnimalTraits' in sync.replicators, self._scan_road_highwater)
            if progress != self._scan_progress:
                self._scan_progress, self._scan_progress_at = progress, now
            elif (not getattr(self,'persistent_scan',False) and
                  13 in self.world.initial_states and now - self._scan_progress_at >= 5):
                self.scan_stalled = True
            if self.on_scan_progress is not None and now >= self._scan_progress_emit_at:
                self._scan_progress_emit_at = now + 0.5
                self.on_scan_progress({'elapsed': elapsed,
                    'catalogs': sum(bool(value) for value in sync.catalog.values()),
                    'announced': len(sync.announced), 'received': len(sync.channels),
                    'road': len(sync.road_population()), 'road_required': self.scan_min_road_models})
        ready = (sync.live_ready() if getattr(self,'persistent_scan',False) and self.scan_complete
                 else sync.initial_ready(now))
        if self.scan_once and not ready:
            return  # Only build/sort rows once all initial data has arrived.
        if scanner is None or not scanner.dirty:
            if not sync.dirty:
                if ready == self._brainrot_complete:
                    return
        # Actual received GUI takes precedence over the equivalent local
        # overhead data; never duplicate a server with both representations.
        from .brainrot import ordered
        rows = scanner.rows() or sync.rows()
        rows = ordered(rows)
        if rows != self._brainrot_rows or ready != self._brainrot_complete:
            self._brainrot_rows = rows
            self._brainrot_complete = ready
            self.on_brainrots({'server_id': self.info._join_script.get('GameId'), 'rows': rows, 'complete': ready})
        if self.scan_once and ready:
            if not self.scan_complete and getattr(self,'persistent_scan',False):
                self._brainrot_poll_at=now+interval
            self.scan_complete = True
            self.scan_stalled = False

    def chat(self, text):
        from .chat import validate_text, ChatUnavailable, new_message_id
        validate_text(text)
        blocked = self._chat_block_reason()
        if blocked:
            raise CommandError(blocked)
        now = time.monotonic()
        if now - self._last_chat_at < 1 and not self._queued_chat:
            raise CommandError('Espera un segundo entre mensajes de chat.')
        if len(self._pending_chat) + len(self._queued_chat) >= 16:
            raise CommandError('Esperando respuestas del servidor a los mensajes de chat previos.')
        message_id = new_message_id(self.info.account.user_id)
        try:
            request = self._prepare_chat(text, message_id)
        except ChatUnavailable as error:
            request, waiting = None, str(error)
        else:
            waiting = 'Esperando el envío de los mensajes anteriores.'
        self._last_chat_at = now
        if request is None or self._queued_chat or now - self._last_chat_wire_at < 1:
            public = {'state': 'waiting_for_chat', 'message_id': message_id, 'channel': 'Here',
                      'text': text, 'message': waiting}
            self._queued_chat[message_id] = {**public, 'deadline': now + 45}
            self.last_chat = dict(public)
            return public
        return self._submit_chat(request, text, message_id)

    def _prepare_chat(self, text, message_id):
        from .chat import prepare, ChatUnavailable
        # Current servers send access reconciliation after initial chat instances.
        # Do not submit against those early placeholder TextSources.
        if (self.chat_access['communication_status'] is None and self.schema is not None and
                any(e['name'] == 'ReconcileCommunicationAccessCompleted' and
                    self.schema.classes[e['class_id']]['name'] == 'Chat' and
                    [a['type'] for a in e['arguments']] == [2] for e in self.schema.events)):
            raise ChatUnavailable('Esperando a que termine la inicialización del acceso al chat.')
        # Here is the current server's RBXGeneral. Allocation of a universe
        # Global channel must never change the destination of a chat command.
        return prepare(self.world, self.info.account.user_id, text, message_id)

    def _submit_chat(self, request, text, message_id):
        now = time.monotonic()
        if self._chat_loaded_service != request['service'] and request['loaded_packet'] is not None:
            self._send(request['loaded_packet'], 3)
            self._chat_loaded_service = request['service']
        self._send(request['packet'], 3)
        self._last_chat_wire_at = now
        self.chat_messages_sent += 1
        public = {'state': 'sent_unconfirmed', 'message_id': message_id, 'channel': request['channel'],
                  'text': text, 'wire_event': request['wire_event']}
        self._pending_chat[message_id] = {**public, 'deadline': now + 10, 'service': request['service'],
            'source': request['source'], 'channel_ref': request['channel_ref']}
        self.last_chat = dict(public)
        return dict(public)

    def _poll_chat(self):
        if not self._queued_chat:
            return
        now = time.monotonic()
        if now < self._chat_poll_at or now - self._last_chat_wire_at < 1:
            return
        self._chat_poll_at = now + 0.25
        message_id, pending = next(iter(self._queued_chat.items()))
        from .chat import ChatUnavailable
        try:
            blocked = self._chat_block_reason()
            if blocked:
                raise CommandError(blocked)
            request = self._prepare_chat(pending['text'], message_id)
        except ChatUnavailable:
            return
        except CommandError as error:
            del self._queued_chat[message_id]
            self._chat_result(message_id, pending, 'not_sent', message=str(error))
            return
        del self._queued_chat[message_id]
        result = self._submit_chat(request, pending['text'], message_id)
        self._command_result({'command': 'chat', **result})

    def _chat_result(self, message_id, pending, state, **fields):
        result = {k: pending[k] for k in ('message_id', 'channel', 'text', 'wire_event') if k in pending}
        result.update(state=state, **fields)
        if self.last_chat and self.last_chat['message_id'] == message_id:
            self.last_chat = result
        self._command_result({'command': 'chat', **result})

    def _expire_chat(self, *, closing=False):
        if not self._queued_chat and not self._pending_chat:
            return
        now = time.monotonic()
        for message_id, pending in list(self._queued_chat.items()):
            if closing or now >= pending['deadline']:
                self._chat_result(message_id, pending,
                    'not_sent_connection_closed' if closing else 'chat_unavailable_timeout')
                del self._queued_chat[message_id]
        for message_id, pending in list(self._pending_chat.items()):
            if closing or now >= pending['deadline']:
                self._chat_result(message_id, pending,
                                  'connection_closed_unconfirmed' if closing else 'unconfirmed_timeout')
                del self._pending_chat[message_id]

    def _observe_chat_event(self, name, key, arguments):
        if (name == 'TextChatService.ServerToClientUniverseChatChannelAllocatedSignalV1' and
                arguments == [b'global'] and self.world is not None):
            node = self.world.nodes.get(key)
            if node is not None and node['class'] == 'TextChatService':
                self._chat_universe_service = key
        if name in CHAT_ACCESS_EVENTS and len(arguments) == 1 and self.world is not None:
            import re
            expected_class, field = CHAT_ACCESS_EVENTS[name]
            node = self.world.nodes.get(key)
            value = arguments[0]
            if isinstance(value, bytes) and len(value) <= 64:
                try:
                    value = value.decode('ascii')
                except UnicodeError:
                    value = None
            if (node is not None and node['class'] == expected_class and isinstance(value, str) and
                    re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value)):
                self.chat_access[field] = value
        if not self._pending_chat:
            return
        from .chat import receipt, MESSAGE_STATUS, validate_message_id
        update = receipt(name, arguments)
        if update is None:
            return
        message_id = update['message_id']
        if isinstance(message_id, bytes):
            try:
                message_id = message_id.decode('ascii')
            except UnicodeError:
                return
        if not isinstance(message_id, str):
            return
        try:
            validate_message_id(message_id, self.info.account.user_id)
        except CommandError:
            return
        message_id = message_id.upper()
        pending = self._pending_chat.get(message_id)
        status = update['status']
        if (pending is None or key != pending['service'] or type(status) is not int or
                status not in MESSAGE_STATUS or
                pending['source'] is not None and update['source'] is not None and update['source'] != pending['source'] or
                update['channel_ref'] is not None and update['channel_ref'] != pending['channel_ref']):
            return
        if update.get('universe') and (pending['source'] is not None or
                type(update.get('sender_user_id')) is not int or
                update['sender_user_id'] != self.info.account.user_id):
            return
        if pending['source'] is None and update['source'] is not None:
            source = self.world.nodes.get(update['source'])
            if (source is None or source['class'] != 'TextSource' or
                    source['props'].get('UserIdReplicated') != self.info.account.user_id or
                    source['parent'] != pending['channel_ref']):
                return
        if status == 3:
            self._chat_result(message_id, pending, 'server_processing', server_status='Sending')
            return
        fields = {'server_status': MESSAGE_STATUS[status]}
        if type(update.get('for_moderation')) is bool:
            fields['for_moderation'] = update['for_moderation']
        if status == 6:
            fields['message'] = (self._chat_block_reason() or
                'Roblox rechazó el mensaje debido a la configuración de acceso al chat de la cuenta (InvalidPrivacySettings).')
            if self.chat_access['communication_status'] is not None:
                fields['communication_status'] = self.chat_access['communication_status']
        filtered = update.get('text')
        if isinstance(filtered, bytes) and len(filtered) <= 4096:
            try:
                fields['filtered_text'] = filtered.decode('utf-8')
            except UnicodeError:
                pass
        if status == 2:
            self.chat_messages_confirmed += 1
        self._chat_result(message_id, pending, 'server_accepted' if status == 2 else 'server_rejected', **fields)
        del self._pending_chat[message_id]

    def _chat_block_reason(self):
        if self.chat_access['communication_status'] == 'GeoBlocked':
            return 'Roblox desactivó el chat para esta conexión: GeoBlocked (restricción regional).'
        return None

    def _poll_refinement(self):
        refine = self._refine_teleport
        now = time.monotonic()
        if refine is None or now < refine['next_at'] or now - self._last_teleport_at < 1:
            return
        if now > refine['deadline']:
            self._refine_teleport = None
            self._command_result({'command': 'teleport', 'state': 'precise_position_unavailable',
                                  'target': refine['target']})
            return
        refine['next_at'] = now + 0.25
        try:
            _, player, _ = resolve_player(self, refine['target'])
            if player['props']['UserId'] != refine['user_id']:
                return
            target, coarse = self._target_position(refine['target'])
            if coarse or target['age_seconds'] is None or target['age_seconds'] > 5:
                return
            result = self.teleport(refine['target'])
            if not result.get('coarse_target_region'):
                self._refine_teleport = None
            self._command_result({'command': 'teleport', **result})
        except CommandError:
            pass

    def loop_status(self):
        if self._loop_tp is None:
            return {'active': False}
        return {'active': True, **{k: v for k, v in self._loop_tp.items() if k != 'next_at'}}

    def start_loop(self, nickname):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_]{1,20}', nickname):
            raise CommandError('Especifica el username o un prefijo inequívoco.')
        user_id = None
        try:
            _, player, nickname = resolve_player(self, nickname)
            user_id = player['props']['UserId']
        except PlayerUnavailable:
            pass
        if user_id == self.info.account.user_id:
            raise CommandError('Elige otro jugador.')
        self._refine_teleport = None
        self._loop_tp = {'target': nickname, 'user_id': user_id, 'interval_seconds': 1.0,
                         'state': 'starting', 'requests_sent': 0, 'last_error': None, 'next_at': 0}
        return self.loop_status()

    def stop_loop(self):
        previous = self.loop_status()
        self._loop_tp = None
        self._refine_teleport = None
        return {**previous, 'active': False, 'state': 'stopped'}

    def _poll_loop(self):
        loop = self._loop_tp
        now = time.monotonic()
        if loop is None or now + 0.000001 < loop['next_at']:
            return
        loop['next_at'] = now + loop['interval_seconds']  # No catch-up bursts.
        old = (loop['state'], loop['last_error'])
        try:
            _, player, username = resolve_player(self, loop['target'])
            user_id = player['props']['UserId']
            if loop['user_id'] is not None and loop['user_id'] != user_id:
                raise CommandError('El jugador origen abandonó el servidor. Esperando su regreso.')
            loop['target'], loop['user_id'] = username, user_id
            result = self.teleport(username, _loop=True)
            loop['requests_sent'] += 1
            loop['state'] = 'loading_target_region' if result['coarse_target_region'] else 'following'
            loop['last_error'] = None
        except CommandError as error:
            loop['state'], loop['last_error'] = 'waiting', str(error)
        if old != (loop['state'], loop['last_error']):
            self._command_result({'command': 'looptp', **self.loop_status()})

    def _physics_payload(self, root, position):
        from .isr import stationary_packet as isr_packet
        node = self.world.nodes[root]
        layout = self._physics_layout.get(node['class'])
        if layout is None:
            cid = next((i for i, c in enumerate(self.schema.classes) if c['name'] == node['class']), None)
            properties = self.schema.isr.get(cid, [])
            pv = next((i for i, pid in enumerate(properties) if
                       self.schema.properties[pid]['name'] == 'ReplicationPV' and
                       self.schema.properties[pid]['type'] == 57), None)
            layout = (cid, len(properties), pv)
            self._physics_layout[node['class']] = layout
        cid, property_count, pv = layout
        if pv is None:
            raise CommandError('El schema ISR no contiene la física de la root part del personaje.')
        frame = self.world.last_isr_frame
        if self._isr_out_frame is not None and ((frame - self._isr_out_frame) & 0xffffffff) == 0:
            frame = (frame + 1) & 0xffffffff
        elif self._isr_out_frame is not None and ((frame - self._isr_out_frame) & 0xffffffff) >= 0x80000000:
            frame = (self._isr_out_frame + 1) & 0xffffffff
        self._isr_out_frame = frame
        return isr_packet(root, cid, property_count, pv, position, frame, self.world.last_isr_frame)

    def _maintain_physics(self):
        if (self.world is None or self.world.last_isr_frame is None or not getattr(self.schema, 'isr', None) or
                time.monotonic() - self._physics_at < 0.1):
            return
        self._physics_at = time.monotonic()
        try:
            _, own, _ = resolve_player(self)
            root, _ = root_for(self, own)
            if self._physics_intent is None or self._physics_intent['root'] != root:
                self._physics_intent = {'root': root, 'position': position_for(self)['position']}
            self._send(self._physics_payload(root, self._physics_intent['position']), 0)
            self.physics_packets_sent += 1
        except CommandError:
            return

    def _target_position(self, nickname):
        target_key, target_player, target_name = resolve_player(self, nickname)
        region = target_player['props'].get('ChararacterRegionId')
        valid_region = (isinstance(region, (tuple, list)) and len(region) == 3 and
                        all(type(v) in (int, float) and math.isfinite(v) and
                            v == int(v) and abs(v) <= 2**20 for v in region))
        try:
            target = position_for(self, nickname)
            # A newer streamed-region update can invalidate an old root position.
            # Do not follow a player to a cell they have already left.
            region_at = self.world.region_observed.get(target_key)
            position_at = self.world.position_observed.get(target['root'])
            if (valid_region and region_at is not None and position_at is not None and
                    region_at > position_at and tuple(math.floor(v / 64) for v in target['position']) != tuple(region)):
                raise CommandError('Esperando la posición exacta del jugador en la nueva área.')
            return target, False
        except CommandError:
            if not valid_region or self.world.last_isr_frame is None:
                raise
            return {'username': target_name, 'user_id': target_player['props']['UserId'],
                    'position': tuple((v + 0.5) * 64 for v in region), 'age_seconds': None,
                    'source': 'streaming_region_center'}, True

    def teleport(self, nickname, *, _loop=False):
        if not self.world or not self.world.character_evidence()['character_spawn_confirmed']:
            raise CommandError('El personaje del bot aún no está listo: modelo, Humanoid y root part no confirmados. Verifica status.')
        if getattr(self.schema, 'isr', None) and self.world.last_isr_frame is None:
            raise CommandError('Espera la sincronización de física: status debe mostrar movement_ready: true.')
        if not _loop and time.monotonic() - self._last_teleport_at < 1:
            raise CommandError('Espera un segundo entre solicitudes de teleport.')
        target, coarse = self._target_position(nickname)
        _, own, _ = resolve_player(self)
        if target['user_id'] == self.info.account.user_id:
            raise CommandError('Elige otro jugador.')
        recent_isr = (self.world.isr_received_at is not None and
                      time.monotonic() - self.world.isr_received_at <= 3)
        if not coarse and (target['age_seconds'] is None or
                           (target['age_seconds'] > 5 and not (_loop and recent_isr))):
            raise CommandError('La posición del jugador está desactualizada. No se envió teleport con coordenadas viejas.')
        root, _ = root_for(self, own)
        destination = (target['position'][0] + 2.5, target['position'][1] + 0.5, target['position'][2])
        own_position = position_for(self)
        origin = own_position['position']
        own_is_current = (own_position['age_seconds'] is not None and own_position['age_seconds'] <= 1 and
                          (self._physics_intent is None or self._physics_intent['root'] != root or
                           math.dist(origin, self._physics_intent['position']) <= 1))
        if not _loop and not coarse and own_is_current and math.dist(origin, destination) <= 1:
            return {'state': 'already_near_target', 'target': target['username'], 'coarse_target_region': False}
        self._physics_sequence += 1
        packet = stationary_packet(root, destination, milliseconds(), self._physics_sequence,
                                   self.open._negotiated_capabilities)
        wire_format = 'legacy_85'
        if self.world.last_isr_frame is not None and getattr(self.schema, 'isr', None):
            packet = self._physics_payload(root, destination)
            wire_format = 'isr_a1'
        self._send(packet, 0)
        self._last_teleport_at = time.monotonic()
        if wire_format == 'isr_a1':
            self._physics_intent = {'root': root, 'position': destination}
        self.last_teleport = {'state': 'sent_unconfirmed', 'target': target['username'],
                              'target_user_id': target['user_id'], 'destination': destination,
                              'wire_format': wire_format,
                              'coarse_target_region': coarse,
                              'target_position_source': target['source'],
                              'target_position': target['position'],
                              'target_position_age_seconds': target['age_seconds']}
        self._pending_teleport = {'root': root, 'destination': destination,
                                  'origin': origin,
                                  'character': own['props']['Character'],
                                  'sent_at': time.monotonic(),
                                  'deadline': time.monotonic() + 3}
        self._refine_teleport = ({'target': target['username'], 'user_id': target['user_id'],
                                  'deadline': time.monotonic() + 45, 'next_at': time.monotonic() + 0.25}
                                 if coarse and not _loop else None)
        return dict(self.last_teleport)

    def _observe_position(self, root, position):
        pending = self._pending_teleport
        if self._physics_intent and root == self._physics_intent['root']:
            if isinstance(position, (tuple, list)) and len(position) == 3 and all(math.isfinite(v) for v in position):
                # Delayed pre-TP snapshots must not cancel the outgoing request
                # before the server can receive it. Respect corrections after 0.75s.
                if (not pending or root != pending['root'] or
                        time.monotonic() - pending['sent_at'] >= 0.75 or
                        math.dist(position, pending['destination']) <= 2):
                    self._physics_intent['position'] = tuple(position)
        own = self.world.nodes.get(self.world.own) if self.world else None
        if (not pending or root != pending['root'] or not isinstance(position, (tuple, list)) or
                len(position) != 3 or any(not math.isfinite(v) for v in position) or
                not own or own['props'].get('Character') != pending['character']):
            return
        if (math.dist(position, pending['destination']) <= 2 and
                math.dist(position, pending['origin']) >= 1):
            self.last_teleport['state'] = 'server_position_confirmed'
            self._pending_teleport = None
            self._command_result({'command': 'teleport', **self.last_teleport})

    def run(self, *, duration=40):
        from .luau_worker import Worker
        # Start the isolated VM before opening UDP. No process-start latency on
        # a server request; bytecode never runs in Python or with host IO APIs.
        with (self.worker_factory or Worker)() as self.worker:
            try:
                result = super().run(duration=duration)
                self._expire_chat(closing=True)
                return self.summary() if self.last_chat else result
            except CryptoError:
                if self.ack_timeout is None:
                    raise
                self.reason = 'reliable_ack_timeout'
                if self._pending_teleport:
                    self.last_teleport['state'] = 'connection_lost_unconfirmed'
                    self._pending_teleport = None
                self._command_result({'command': 'connection', 'state': 'disconnected',
                                      'message': 'El servidor no confirmó los paquetes reliable; la conexión se terminó.',
                                      'ack_timeout': self.ack_timeout})
                self._expire_chat(closing=True)
                return self.summary()

    def _message(self, payload):
        self.received_tick = milliseconds() & 0xffffffff
        active = super()._message(payload)
        kind = payload[0]
        if self.scan_once and kind in (0x10, 0x97):
            self.scan_milestones.setdefault('transport' if kind == 0x10 else 'schema',
                round(time.monotonic() - self._started_at, 4))
        if kind == 0x9b:
            if self.worker is None or not self._execution_allowed():
                raise CryptoError('Isolated VM unavailable or request limit reached.')
            response = self.worker.reply(payload, self.info._join_script.get('GameId'))
            self._send(response, 3)
            self.execution_responses_sent += 1
        elif kind == 0x97:
            self.world = (self.world_factory or World)(self.schema, self.info.account.user_id, self)
        elif kind == 0x83 and self.world is not None:
            if self.player_roster is None:
                self.world.push(payload)
            if not self.scan_once:
                self._initialize_character()
                self._check_spawn()
        elif kind == 0xa1 and self.world is not None:
            self.world.push_isr(payload)
        return active

    def _execution_allowed(self):
        return self.execution_responses_sent < 16

    def _player_data(self, payload):
        if self.world is not None:
            self.world.push(payload)
            if not self.scan_once:
                self.player_roster.refresh(self.world)
            else:
                self.player_roster._source = self.world
        else:
            super()._player_data(payload)

    def _initialize_character(self):
        own = self.world.nodes.get(self.world.own)
        if (not own or own['class'] != 'Player' or own['props'].get('UserId') != self.info.account.user_id or
                13 not in self.world.initial_states):
            return
        if not self.character_request_sent:
            self._send(request_character(self.world.own), 3)
            self.character_request_sent = True
        # This is the normal Heli-Wars team menu action, recovered from that
        # game's button. Do not send a guessed RPC in other experiences.
        if self.info.place_id == 2336379484 and self.team_request is None:
            request = team_request(self.world)
            if request:
                self.team_request = request
                self._send(request['payload'], 3)

    def _check_spawn(self):
        evidence = self.world.character_evidence()
        if evidence['character_spawn_confirmed']:
            self.spawn_ever_confirmed = True
            ref = self.world.nodes[self.world.own]['props']['Character']
            if self._announced_character != ref:
                self._announced_character = ref
                if self.on_character:
                    self.on_character({'user_id': self.info.account.user_id,
                                       'character_spawned': True,
                                       'movement_ready': bool(self.world.last_isr_frame is not None and
                                                              getattr(self.schema, 'isr', None))})

    def summary(self):
        result = super().summary()
        evidence = self.world.character_evidence() if self.world is not None else None
        spawned = bool(evidence and evidence['character_spawn_confirmed'])
        result.update(application_stage='character', game_session=spawned, character_spawned=spawned,
                      movement_ready=bool(spawned and self.world.last_isr_frame is not None and
                                          getattr(self.schema, 'isr', None)),
                      physics_packets_sent=self.physics_packets_sent,
                      loop_teleport=self.loop_status(),
                      character_spawn_ever_confirmed=self.spawn_ever_confirmed,
                      character_request_sent=self.character_request_sent,
                      data_pongs_sent=self.data_pongs_sent,
                      execution_responses_sent=self.execution_responses_sent,
                      execution_reply_elapsed_ms=self.worker.last_elapsed_ms if self.worker is not None else None,
                      character_evidence=evidence,
                      replication_diagnostics=({'known_nodes': len(self.world.nodes),
                          'node_limit': self.world.max_nodes,
                          'instances_not_retained': self.world.items['WorldInstanceNotRetained'],
                          'instances_evicted': self.world.items['WorldInstanceEvicted'],
                          'decode_stops': dict(self.world.stops)} if self.world is not None else None),
                      last_teleport=dict(self.last_teleport) if self.last_teleport else None,
                      last_chat=dict(self.last_chat) if self.last_chat else None,
                      chat_messages_sent=self.chat_messages_sent,
                      chat_messages_confirmed=self.chat_messages_confirmed,
                      chat_messages_waiting=len(self._queued_chat),
                      chat_access=dict(self.chat_access),
                      team_selection={'sent': self.team_request is not None,
                                      'team': self.team_request['team_name'] if self.team_request else None,
                                      'reply': self.team_reply})
        if spawned and self.reason in ('duration_elapsed', 'client_quit'):
            result['state'] = 'character_spawned'
        result['note'] = ('Own character confirmed; ISR physics sender available. Teleport acceptance needs received position or external observation.'
                          if spawned else 'Character initialization attempted; own character spawn is not yet confirmed.')
        return result
