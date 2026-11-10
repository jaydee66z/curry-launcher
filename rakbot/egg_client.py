"""Read-only Steal An Egg field snapshots through the existing native transport."""
import math
import socket
import struct
import time

from .application import varuint
from .brainrot import ordered
from .brainrot_wire import attributes
from .egg_catalog import Catalog, finite
from .egg_filter import settings, UNFILTERED_GAME
from .egg_schedule import CycleSchedule
from .game_client import GameClient, World
from .persistent_client import PersistentTransport
from .heli_wars import wire_guid
from .replication import Inspector

PLACE_ID = 107778070777162
REMOTE_ROOT = ('ReplicatedStorage','Packages','Networking')
FIELDS = ('Uid','AssetCategory','AssetScale','Mutations','AssetEyeColor',
          'AssetColorSeed','AssetColorIndex','AreaId','State','Version')
CLASSES = frozenset(('DataModel','Player','Workspace','ReplicatedStorage','Folder',
                     'ModuleScript','RemoteEvent','RemoteFunction','Configuration'))


def field_record(value):
    if not isinstance(value,dict):
        raise ValueError('Invalid egg record')
    record = {name.encode():value.get(name.encode(),value.get(name)) for name in FIELDS}
    for key in (b'Uid',b'AssetCategory'):
        if not isinstance(record[key],(bytes,str)) or not 0<len(record[key])<=128:
            raise ValueError('Invalid egg identity')
    scale, version = record[b'AssetScale'], record.get(b'Version')
    if not finite(scale) or not 0 < scale <= 100000 or version is not None and (not finite(version) or version<0):
        raise ValueError('Invalid egg size/version')
    mutations = record[b'Mutations'] or []
    if not isinstance(mutations,list) or len(mutations)>32 or any(not isinstance(v,(bytes,str)) or len(v)>128 for v in mutations):
        raise ValueError('Invalid egg mutations')
    record[b'Mutations'] = mutations
    return record


def snapshot_records(snapshot):
    if not isinstance(snapshot,dict):
        raise ValueError('Missing egg snapshot')
    records = snapshot.get(b'Records',snapshot.get('Records'))
    clock = snapshot.get(b'ServerTime',snapshot.get('ServerTime'))
    if not isinstance(records,(list,dict)) or len(records)>10000 or not finite(clock) or clock<=0:
        raise ValueError('Invalid egg snapshot')
    result = {}
    for value in records.values() if isinstance(records,dict) else records:
        record = field_record(value)
        uid = record[b'Uid']
        if uid in result:
            raise ValueError('Duplicate egg uid')
        result[uid] = record
    return result, clock


def cycle(clock, attrs, defaults):
    period = attrs.get(b'AreaEggCyclePeriodSeconds',defaults.get('PERIOD_SECONDS',300))
    night = attrs.get(b'AreaEggCycleNightSeconds',attrs.get(b'AreaEggCycleDefaultNightSeconds',defaults.get('NIGHT_SECONDS_DEFAULT',10)))
    anchor = attrs.get(b'AreaEggCycleAnchorAt',0)
    stopped = attrs.get(b'AreaEggCycleDisabledAt')
    if not finite(period) or not 0<period<=86400 or not finite(night) or not finite(anchor):
        raise ValueError('Invalid egg cycle')
    if finite(stopped):
        clock = min(clock,stopped)
    reset = anchor+(math.floor((clock-anchor)/period)+1)*period
    remaining = max(0,reset-clock)
    return dict(reset_at=reset,seconds_until_reset=remaining,night_seconds=max(0,night),
                in_night=remaining<=night,running=not finite(stopped))


class EggWorld(World):
    native_scan_projection = True

    def __init__(self,*args):
        super().__init__(*args)
        self.scan_only = True
        self.catalog = Catalog()
        self.blobs, self.blob_bytes = {}, 0
        self.modules, self.loaded = {}, {}
        self.records, self.pending_updates = {}, []
        self.snapshot_received = False
        self.snapshot_serial = 0
        self.catalog_dirty = True
        self.server_time, self.received_at = None, None
        self.request_id, self.request_remote, self.request_at = 61320, None, 0
        self.requests = 0
        self.workspace_attrs = {}
        self.invalid_snapshots = 0
        self.catalog_at = 0
        self.live_balance = {}

    def scan_class_policy(self,name):
        # Egg catalogs/remotes use different names from the Brainrot profile.
        return name in CLASSES

    def _important_node(self,node):
        return node['class'] in CLASSES

    def _remember_node(self,key,node):
        if node['class'] in CLASSES:
            Inspector._remember_node(self,key,node)
        else:
            if key in self.nodes:
                self._forget_node(key)
            self.items['WorldInstanceProjectedOut'] += 1

    def keep_property(self,cls,name):
        return (name in ('Name','Parent') or cls=='Player' and name=='UserId' or
                cls=='ModuleScript' and name=='Source' or
                cls in ('Workspace','ReplicatedStorage') and name=='AttributesReplicate')

    def value(self,reader,kind,pending,**options):
        if kind in (46,47):
            digest = reader.take(16)
            if digest not in self.shared:
                pending.add(digest)
            return digest
        return super().value(reader,kind,pending,**options)

    def path(self,key):
        result,seen=[],set()
        while key in self.nodes and key not in seen and len(result)<40:
            seen.add(key)
            node=self.nodes[key]
            name=node['props'].get('Name') or node['class']
            result.append(name.decode('utf-8','replace') if isinstance(name,bytes) else name)
            key=node['parent']
        return tuple(reversed(result))

    def shared_value(self,digest,blob):
        super().shared_value(digest,blob)
        self.catalog_dirty = True
        if digest not in self.blobs and self.blob_bytes+len(blob)<=16*1024*1024:
            self.blobs[digest]=blob
            self.blob_bytes+=len(blob)

    def module_blob(self,digest):
        # Asset blobs can fill the world's small retention buffer before a
        # source arrives. Only a reference resolved on this connection may
        # use the verified cache; advertised knowledge alone is insufficient.
        if digest not in self.shared:
            return None
        blob=self.blobs.get(digest)
        if blob is None:
            blob=getattr(self.client,'shared_cache_advertised',{}).get(digest)
        if blob is None:
            cache=getattr(self.client,'shared_cache',None)
            if cache is not None:
                blob=cache.get(digest)
        return blob

    def instance_value(self,key,node):
        super().instance_value(key,node)
        if node['class'] in ('ModuleScript','Folder','ReplicatedStorage','DataModel'):
            self.catalog_dirty = True
        if node['class']=='ModuleScript':
            self.modules[key]=node['props'].get('Source')
        if node['class']=='Workspace':
            self._attributes(node)

    def _attributes(self,node):
        try:
            self.workspace_attrs=attributes(node['props'].get('AttributesReplicate',b''))
        except ValueError:
            pass

    def property_value(self,key,name,value):
        super().property_value(key,name,value)
        if name in ('Name','Parent','Source'):
            self.catalog_dirty = True
        node=self.nodes.get(key)
        if node and name=='AttributesReplicate' and node['class']=='Workspace':
            self._attributes(node)
        if node and name=='Source' and node['class']=='ModuleScript':
            self.modules[key]=value

    def removal_value(self,key):
        super().removal_value(key)
        if hasattr(self,'modules'):
            self.modules.pop(key,None)
            self.loaded.pop(key,None)

    def begin_scan(self):
        self.snapshot_received=False
        self.requests=0
        self.request_at=0
        self.pending_updates.clear()

    def _update(self,record):
        uid=record[b'Uid']
        old=self.records.get(uid)
        if old is None and len(self.records)>=10000:
            self.begin_scan()
            raise ValueError('Egg record limit reached; refreshing snapshot.')
        if old is None or (record.get(b'Version') or 0)>=(old.get(b'Version') or 0):
            self.records[uid]=record

    def event_value(self,name,key,args):
        super().event_value(name,key,args)
        path=self.path(key)
        if name=='RemoteEvent.OnClientEvent' and 'SharedFastFlags' in path:
            self._balance(args)
            return
        if name=='RemoteFunction.RemoteOnInvokeSuccess' and key==self.request_remote and args and args[0]==self.request_id:
            try:
                values=args[1]
                snapshot=values[0] if isinstance(values,list) and len(values)==1 else None
                records,clock=snapshot_records(snapshot)
                self.records,self.server_time,self.received_at=records,clock,time.monotonic()
                for kind,value in self.pending_updates:
                    if kind=='remove':
                        self.records.pop(value,None)
                    else:
                        self._update(value)
                self.pending_updates.clear()
                self.snapshot_received=True
                self.snapshot_serial+=1
            except (ValueError,IndexError,TypeError):
                self.invalid_snapshots+=1
            return
        if name!='RemoteEvent.OnClientEvent' or len(path)<4 or path[-4:-1]!=REMOTE_ROOT:
            return
        values=args[0] if args and isinstance(args[0],list) else []
        remote=path[-1]
        try:
            if remote=='RE/EggWorld/FieldEggShifted' and len(values)==1:
                record=field_record(values[0])
                self._update(record)
                if not self.snapshot_received and self.requests and len(self.pending_updates)<20000:
                    self.pending_updates.append(('update',record))
            elif remote=='RE/EggWorld/FieldEggGone' and values:
                uid=values[0]
                if isinstance(uid,(bytes,str)):
                    self.records.pop(uid,None)
                    if not self.snapshot_received and self.requests and len(self.pending_updates)<20000:
                        self.pending_updates.append(('remove',uid))
            elif remote=='RE/EggWorld/FieldEggBatchShifted' and len(values)==1 and isinstance(values[0],dict):
                batch=values[0]
                removed=batch.get(b'RemovedUids',[]) or []
                updated=batch.get(b'UpdatedRecords',[]) or []
                if not isinstance(removed,list) or not isinstance(updated,list) or len(removed)+len(updated)>10000:
                    raise ValueError('Invalid egg batch')
                validated=[field_record(value) for value in updated]
                if any(not isinstance(uid,(bytes,str)) for uid in removed):
                    raise ValueError('Invalid egg removal')
                for uid in removed:
                    self.records.pop(uid,None)
                    if not self.snapshot_received and self.requests and len(self.pending_updates)<20000:
                        self.pending_updates.append(('remove',uid))
                for record in validated:
                    self._update(record)
                    if not self.snapshot_received and self.requests and len(self.pending_updates)<20000:
                        self.pending_updates.append(('update',record))
            elif 'SharedFastFlags.Update' in remote:
                self._balance(values)
        except (ValueError,TypeError):
            self.invalid_snapshots+=1

    def _balance(self,value,depth=0):
        if depth>3:
            return
        if isinstance(value,dict):
            for key,setting in value.items():
                if key in (b'Game.Balance.Earnings',b'Game.Balance.AreaEggCycle') and isinstance(setting,dict):
                    target=self.catalog.earnings if key==b'Game.Balance.Earnings' else self.catalog.area_cycle
                    for field,number in setting.items():
                        if isinstance(field,bytes) and finite(number):
                            target[field.decode('utf-8','replace')]=number
                            self.live_balance.setdefault(key,{})[field.decode('utf-8','replace')]=number
                else:
                    self._balance(setting,depth+1)
        elif isinstance(value,list):
            for item in value[:10]:
                self._balance(item,depth+1)

    def poll(self):
        now=time.monotonic()
        self._request_snapshot(now)
        if self.catalog_dirty and now>=self.catalog_at:
            self.catalog_at=now+.1
            self.catalog_dirty=False
            for key,digest in self.modules.items():
                if self.loaded.get(key)==digest:
                    continue
                blob=self.module_blob(digest)
                if blob is None:
                    continue
                node=self.nodes.get(key)
                if node is None:
                    continue
                path='.'.join(self.path(key))
                if not path.startswith('DataModel.ReplicatedStorage.') and not path.startswith('ReplicatedStorage.'):
                    continue
                name=node['props'].get('Name',b'').decode('utf-8','replace')
                self.catalog.module(name,path,blob)
                self.loaded[key]=digest
            self.catalog.earnings.update(self.live_balance.get(b'Game.Balance.Earnings',{}))
            self.catalog.area_cycle.update(self.live_balance.get(b'Game.Balance.AreaEggCycle',{}))
        if self.catalog.earnings:
            self.client.scan_milestones.setdefault('egg_balance',round(time.monotonic()-self.client._started_at,4))

    def _request_snapshot(self,now):
        milestones=self.client.scan_milestones
        elapsed=round(now-self.client._started_at,4)
        if self.own is not None:
            milestones.setdefault('egg_player',elapsed)
        if 13 in self.initial_states:
            milestones.setdefault('state13',elapsed)
        if self.snapshot_received:
            milestones.setdefault('egg_snapshot',elapsed)
        if self.snapshot_received or self.requests>=3 or self.own is None or now-self.request_at<5:
            return
        remotes=[k for k,n in self.nodes.class_items('RemoteFunction')
            if self.path(k)[-4:]==REMOTE_ROOT+('RF/EggWorld/AskFieldEggSnapshot',)]
        events=[i for i,e in enumerate(self.schema.events)
            if self.schema.classes[e['class_id']]['name']=='RemoteFunction' and e['name']=='RemoteOnInvokeServer'
            and [a['type'] for a in e['arguments']]==[10,28,29]]
        if len(remotes)==len(events)==1:
            self.request_id+=1
            self.requests+=1
            self.request_at=now
            self.request_remote=remotes[0]
            self.pending_updates.clear()
            milestones.setdefault('egg_request',elapsed)
            self.client._send(b'\x83\x07'+wire_guid(remotes[0])+struct.pack('<H',events[0])+
                varuint(self.request_id*2)+wire_guid(self.own)+b'\0',3)

    def snapshot(self):
        if not self.snapshot_received:
            return None
        rows=[]
        unresolved=0
        candidates=0
        options=getattr(getattr(self,'client',None),'egg_settings',UNFILTERED_GAME)
        for record in self.records.values():
            state=record.get(b'State')
            if isinstance(state,bytes):
                state=state.decode('utf-8','replace')
            if state not in options['states']:
                continue
            candidates+=1
            try:
                row=self.catalog.row(record,earnings_mode=options['earnings_mode'],
                    mutation_multipliers=options['mutation_multipliers'])
            except (ValueError,OverflowError):
                row=None
            if row:
                if row['income']>=options['min_value']:
                    rows.append(row)
            else:
                unresolved+=1
        if unresolved or options['earnings_mode']=='game' and not self.catalog.earnings:
            return None
        clock=self.server_clock()
        return dict(rows=ordered(rows),complete=True,record_count=len(self.records),
                    candidate_count=candidates,earnings_mode=options['earnings_mode'],
                    cycle=self.current_cycle(),server_time=clock)

    def server_clock(self):
        if self.server_time is None or self.received_at is None:
            return None
        return self.server_time+time.monotonic()-self.received_at

    def current_cycle(self):
        clock=self.server_clock()
        if clock is None:
            return {}
        try:
            return cycle(clock,self.workspace_attrs,self.catalog.area_cycle)
        except ValueError:
            options=self.client.egg_settings
            return dict(reset_at=None,seconds_until_reset=options['cycle_fallback'],
                night_seconds=options['night_fallback'],in_night=False,running=True)


class EggClient(PersistentTransport,GameClient):
    profile='egg'
    def __init__(self,info,*,on_brainrots=None,persistent=False,rescan_seconds=None,
                 initial_timeout=60,egg_settings=None,**options):
        if rescan_seconds is not None and (not finite(rescan_seconds) or rescan_seconds<=0):
            raise ValueError('Invalid Egg rescan interval.')
        self.egg_settings=settings(egg_settings if egg_settings is not None else UNFILTERED_GAME)
        self.rescan_seconds=rescan_seconds
        self.egg_schedule=CycleSchedule(self.egg_settings,interval=rescan_seconds)
        self._egg_reported_serial=0
        self.on_eggs=on_brainrots
        self._egg_poll_at=0
        super().__init__(info,persistent=persistent,initial_timeout=initial_timeout,
            on_brainrots=None,world_factory=EggWorld,**options)

    def _poll_brainrots(self):
        now=time.monotonic()
        if self.world is None or now<self._egg_poll_at:
            return
        self._egg_poll_at=now+(.5 if self.persistent_scan and self.scan_complete else .05)
        if self.persistent_scan:
            role=self.egg_schedule.due(now,self.world.server_clock(),self.world.current_cycle())
            if role is not None:
                self.world.begin_scan()
                self.egg_schedule.request(role)
        self.world.poll()
        if self.on_scan_progress:
            self.on_scan_progress(dict(elapsed=round(now-self._started_at,3),
                catalogs=int(bool(self.world.catalog.earnings)),announced=len(self.world.records),
                received=len(self.world.catalog.pets),road=0,road_required=0))
        if self.persistent_scan and self.world.requests>=3 and not self.world.snapshot_received and now-self.world.request_at>=10:
            # A failed refresh must not close a healthy game connection.
            self.egg_schedule.retry(now)
            self.world.requests=0
            self.world.request_at=now+30
        if self.world.snapshot_serial==self._egg_reported_serial:
            return
        if self.persistent_scan and self.egg_schedule.phase not in ('requesting','retry'):
            self._egg_reported_serial=self.world.snapshot_serial
            return
        if self.persistent_scan and self.world.snapshot_received and self.egg_schedule.role=='cycle':
            # This read is only for post-reset timing, not a second report.
            self._egg_reported_serial=self.world.snapshot_serial
            self.egg_schedule.after_cycle(self.world.current_cycle(),now)
            return
        snapshot=self.world.snapshot()
        if snapshot is not None and (self.persistent_scan or not self.scan_complete):
            self.scan_milestones.setdefault('egg_complete',round(now-self._started_at,4))
            snapshot['server_id']=self.info._join_script.get('GameId')
            self.scan_complete=True
            self._egg_reported_serial=self.world.snapshot_serial
            if self.persistent_scan:
                self.egg_schedule.after_report(snapshot['cycle'],now,snapshot['server_time'])
                snapshot['schedule']=self.egg_schedule.status(now)
                if getattr(self,'sock',None) is not None:
                    self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,512*1024)
            if self.on_eggs:
                self.on_eggs(snapshot)
