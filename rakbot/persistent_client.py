"""Persistent transport shared by scanners and the character Joiner."""
from collections import deque
import struct
import time

from .game_client import GameClient, milliseconds


class PersistentTransport:
    profile='scanner'

    def __init__(self,*args,persistent=False,initial_timeout=60,**options):
        self.persistent_scan=persistent
        self.initial_timeout=initial_timeout
        self._execution_times=deque()
        self._last_message_at=time.monotonic()
        self._keepalive_at=self._last_message_at
        super().__init__(*args,**options)
        if persistent:
            # A short NAK burst must not spend the entire retry budget.
            # Keep retries/storage bounded, with room for a transient stall.
            self.reliable_retry_limit=20
            self.nak_retry_floor=.25
            self.assembler.ttl=60

    def _execution_allowed(self):
        if not self.persistent_scan:
            return super()._execution_allowed()
        now=time.monotonic()
        while self._execution_times and now-self._execution_times[0]>=60:
            self._execution_times.popleft()
        if len(self._execution_times)>=16:
            return False
        self._execution_times.append(now)
        return True

    def _message(self,payload):
        self._last_message_at=time.monotonic()
        return super()._message(payload)

    def _poll(self):
        if not super()._poll():
            return False
        if not self.persistent_scan:
            return True
        now=time.monotonic()
        if not self.scan_complete and now-self._started_at>=self.initial_timeout:
            self.reason=f'{self.profile}_initial_timeout'
            return False
        if now-max(self._last_message_at,self.last_received_at)>=60:
            self.reason=f'{self.profile}_connection_silent'
            return False
        if self.transport_accepted and now-self._keepalive_at>=10:
            self._send(b'\0'+struct.pack('>Q',milliseconds()),0)
            self._keepalive_at=now
        return True


class BrainrotClient(PersistentTransport,GameClient):
    profile='brainrot'
    scan_interval=30.0

    def __init__(self,info,*,persistent=True,**options):
        self._sync_maintenance_at=0
        self._base_players={}
        self._pending_bases=set()
        self._base_watch={}
        self._join_poll_at=0
        self._full_scan_at=None
        self._full_scan_pending=False
        self._full_retry_at=0
        super().__init__(info,persistent=persistent,**options)

    def _brainrot_player_changed(self,key,node):
        if key not in self._base_players and (not node or node['class']!='Player'):
            return
        before=set(self._base_players.values())
        self._base_players.pop(key,None)
        if node and node['class']=='Player':
            user_id=node['props'].get('UserId')
            if type(user_id) is int and 0<user_id<2**63:
                self._base_players[key]=user_id
        current=set(self._base_players.values())
        self._pending_bases.intersection_update(current)
        self._base_watch={user:watch for user,watch in self._base_watch.items() if user in current}
        self._pending_bases.update(current-before-{self.info.account.user_id})
        self._join_poll_at=0

    def _poll_brainrots(self):
        if not self.persistent_scan or not self.scan_complete:
            result=super()._poll_brainrots()
            if self.persistent_scan and self.scan_complete and self._full_scan_at is None:
                self._full_scan_at=time.monotonic()+self.scan_interval
            return result
        if self.world is None or not self.on_brainrots:
            return
        now=time.monotonic()
        sync=self.world.brainrot_sync
        if self._full_scan_at is None:
            self._full_scan_at=now+self.scan_interval
        if now>=self._full_scan_at:
            # Keep the full-scan cadence independent of player-join scans.
            # Skip missed slots after a stall instead of a catch-up burst.
            missed=int((now-self._full_scan_at)//self.scan_interval)+1
            self._full_scan_at+=missed*self.scan_interval
            self._full_scan_pending=True
        if self._full_scan_pending and now>=self._full_retry_at:
            self._full_retry_at=now+.25
            sync.poll()
            if sync.live_ready():
                self._brainrot_poll_at=0
                super()._poll_brainrots()
                self._full_scan_pending=False
                return
        # A base may stream in several batches. For five seconds after its
        # first result, follow actual new data for that base only; no timer
        # driven row rebuilds and no scans of unrelated plots/road.
        for user_id,(until,versions) in list(self._base_watch.items()):
            if now>=until:
                del self._base_watch[user_id]
            elif any(sync._plot_changed_at.get(channel)!=stamp for channel,stamp in versions.items()):
                self._pending_bases.add(user_id)
        if self._pending_bases or now>=self._sync_maintenance_at:
            sync.poll()
            self._sync_maintenance_at=now+1
        if not self._pending_bases or now<self._join_poll_at:
            return
        self._join_poll_at=now+.05
        updates={}
        completed=[]
        for user_id in sorted(self._pending_bases):
            result=sync.joined_plot_rows(user_id,now)
            if result is None:
                continue
            channels,rows=result
            until=self._base_watch.get(user_id,(now+5,None))[0]
            self._base_watch[user_id]=(until,{channel:sync._plot_changed_at.get(channel) for channel in channels})
            updates.update((channel,[row for row in rows if row['id'].startswith('sync:'+channel+':')]) for channel in channels)
            completed.append(user_id)
        self._pending_bases.difference_update(completed)
        if not updates:
            return
        from .brainrot import ordered
        prefixes=tuple('sync:'+channel+':' for channel in updates)
        rows=[row for row in self._brainrot_rows or [] if not str(row.get('id','')).startswith(prefixes)]
        rows=ordered(rows+[row for changed in updates.values() for row in changed])
        if rows!=self._brainrot_rows:
            self._brainrot_rows=rows
            self.on_brainrots(dict(server_id=self.info._join_script.get('GameId'),rows=rows,complete=True,
                trigger='player_join',joined_user_ids=completed))
