"""Pinned-server joins, one roster observer, and a persistent character client."""
import threading
import time
from urllib.parse import urlparse,parse_qs
import re
import shlex

from .bootstrap import BootstrapError,NetworkUnavailable,RateLimited,RobloxBootstrap,parse_vip_link,job_id
from .persistent_client import PersistentTransport
from .game_client import GameClient


def target_settings(place_id='',server_id='',vip_link=''):
    place=str(place_id or '').strip()
    server=str(server_id or '').strip()
    vip=str(vip_link or '').strip()
    if place.startswith('https://'):
        parsed=urlparse(place)
        match=re.fullmatch(r'/games/([0-9]+)(?:/[^/]*)?/?',parsed.path)
        if parsed.hostname in ('www.roblox.com','roblox.com') and match and 'privateServerLinkCode' not in parse_qs(parsed.query):
            place=match[1]
        else:
            if vip:
                raise ValueError('Укажи одну VIP-ссылку.')
            vip,place=place,''
    if vip:
        parse_vip_link(vip)
        if server:
            raise ValueError('Выбери JobID или VIP-ссылку.')
    try:
        number=int(place) if place else None
    except ValueError:
        raise ValueError('Place ID должен быть положительным числом или ссылкой на игру.') from None
    if number is not None and not 0<number<2**63:
        raise ValueError('Недопустимый Place ID.')
    if not vip and number is None:
        raise ValueError('Для входа по JobID укажи также Place ID; либо вставь VIP-ссылку.')
    return dict(place_id=number,server_id=job_id(server) if server else None,vip_link=vip or None)


def validate_command(line):
    if not isinstance(line,str) or not 1<=len(line)<=1024 or '\n' in line or '\r' in line:
        raise ValueError('Недопустимая команда Joiner.')
    head=line.lstrip().split(None,1)
    if head and head[0].casefold()=='chat' and len(head)==2:
        return line
    parts=shlex.split(line)
    if not parts:
        raise ValueError('Введи команду.')
    name=parts[0].casefold()
    if name in ('stoploop','status','players') and len(parts)==1:
        return name
    if name in ('teleport','looptp','where') and len(parts)==2 and re.fullmatch(r'[A-Za-z0-9_]{1,20}',parts[1]):
        return name+' '+parts[1]
    raise ValueError('Команды: teleport ник, looptp ник, stoploop, where ник, chat текст, status.')


def visible_players(rows,bot_ids):
    return sorted((dict(user_id=r['user_id'],username=r['username'],display_name=r.get('display_name') or r['username'])
        for r in rows if type(r.get('user_id')) is int and r['user_id'] not in bot_ids and not r.get('is_self')
        and isinstance(r.get('username'),str)),key=lambda r:(r['username'].casefold(),r['user_id']))


class PinnedCoordinator:
    """Resolve once; every account receives the same server, never a hop pool."""
    def __init__(self,pool,target):
        self.owner=pool
        self.target=target
        self.assignment_sink=lambda slot,event:pool.assignments[slot].put_nowait(event)
        self.lock=threading.Lock()
        self.waiting={}
        self.server=target['server_id']
        self.stop=threading.Event()
        self.thread=None

    def start(self):
        if self.server:
            self.owner.resolved_target=dict(place_id=self.target['place_id'],job_id=self.server)
            return
        self.thread=threading.Thread(target=self._resolve,daemon=True,name='rakbot-join-target')
        self.thread.start()

    def _resolve(self):
        from .scan_pool import ScanHTTP
        for credential in self.owner.credentials[:self.owner.workers]:
            auth=RobloxBootstrap(credential,http=ScanHTTP(timeout=10))
            while not self.stop.is_set() and not self.owner._stopping():
                try:
                    info=(auth.prepare_vip(self.target['vip_link']) if self.target['vip_link']
                          else auth.prepare(self.target['place_id']))
                    server=job_id(info._join_script.get('GameId'))
                    with self.lock:
                        self.server=server
                        self.owner.resolved_target=dict(place_id=info.place_id,job_id=server)
                        for slot,request in self.waiting.items():
                            self.assignment_sink(slot,dict(event='hop_assignment',request_id=request,job_id=server))
                        self.waiting.clear()
                    return
                except (NetworkUnavailable,RateLimited) as error:
                    self.stop.wait(error.retry_after if isinstance(error,RateLimited) else 3)
                except BootstrapError:
                    break  # A refused account does not choose a server for others.
        if not self.stop.is_set() and not self.owner._stopping():
            self.owner.events.put((1,dict(event='error',message='Joiner could not resolve the target with the selected accounts. Check account errors and game access.')))
            self.owner.stop.set()

    def request(self,slot,request_id):
        with self.lock:
            if self.server:
                self.assignment_sink(slot,dict(event='hop_assignment',request_id=request_id,job_id=self.server))
            else:
                self.waiting[slot]=request_id

    def release(self,slot):
        with self.lock:
            self.waiting.pop(slot,None)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=.2)


class JoinerClient(PersistentTransport,GameClient):
    profile='joiner'

    def __init__(self,info,*,on_ready=None,on_roster=None,observe_roster=None,**options):
        self.on_ready=on_ready
        self.on_roster=on_roster
        self.observe_roster=observe_roster or (lambda:False)
        self._roster_at=0
        self._ready=False
        super().__init__(info,persistent=True,scan_once=False,**options)

    def _player_data(self,payload):
        if self.world is None:
            return super()._player_data(payload)
        self.world.push(payload)
        self.player_roster._source=self.world

    def _poll(self):
        if (not self._ready and self.world is not None and self.own_player_record_received
                and self.world.own and 13 in self.world.initial_states):
            self._ready=self.scan_complete=True
            if self.on_ready:
                self.on_ready(dict(complete=True,rows=[]))
        if not super()._poll():
            return False
        now=time.monotonic()
        if self.player_roster and self.observe_roster() and now>=self._roster_at:
            self._roster_at=now+1
            if self.on_roster:
                self.on_roster(self.player_roster.players())
        return True
