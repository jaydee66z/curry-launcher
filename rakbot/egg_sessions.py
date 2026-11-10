"""Persistent scanner sessions with bounded same-server recovery."""
from contextlib import nullcontext
import queue
import threading
import time

from .bootstrap import BootstrapError, JoinPending, JoinRefused, InstanceMismatch, NetworkUnavailable, RateLimited, RobloxBootstrap
from .egg_client import EggClient
from .persistent_client import BrainrotClient
from .luau_worker import Worker
from .native_crypto import CryptoError
from .shared_cache import for_place

RECONNECT_LIMIT=5


class SharedVM:
    """One isolated native VM per process group, not one per game session."""
    def __init__(self):
        self.lock=threading.Lock()
        self.worker=None

    @property
    def last_elapsed_ms(self):
        return self.worker.last_elapsed_ms if self.worker is not None else None

    def reply(self,*args):
        with self.lock:
            try:
                if self.worker is None:
                    self.worker=Worker().__enter__()
                return self.worker.reply(*args)
            except (ValueError,OSError):
                if self.worker is not None:
                    self.worker.close()
                    self.worker=None
                raise CryptoError('Isolated VM unavailable; retry the game connection.') from None

    def close(self):
        with self.lock:
            if self.worker is not None:
                self.worker.close()
                self.worker=None


class PersistentSessions:
    def __init__(self,pool):
        self.pool=pool
        self.vm=SharedVM()

    def close(self):
        self.vm.close()

    def worker(self,slot):
        from .scan_pool import ScanHTTP, ScanAttemptTimeout
        from .scanner_health import failure_code
        pool=self.pool
        request_id=0
        eggs=pool.place_id==107778070777162
        joiner=pool.join_target is not None
        profile='joiner' if joiner else 'egg' if eggs else 'brainrot'
        while not pool._stopping():
            try:
                index=pool.tasks.get_nowait()
            except queue.Empty:
                return
            record=pool.accounts[index]
            pool._account_slots[index]=slot
            leased=False
            server=None
            def release():
                nonlocal leased
                if leased:
                    leased=False
                    if pool.release_admission is not None:
                        pool.release_admission(index)
            try:
                # Account ownership persists across recovery and server changes.
                record.update(state='waiting_turn',phase_since=time.monotonic())
                if pool.admission is not None:
                    if not pool.admission(index):
                        break
                    leased=True
                record.update(state='authenticating',phase_since=time.monotonic())
                bootstrap=RobloxBootstrap(pool.credentials[index],http=ScanHTTP(timeout=10))
                while not pool._stopping():
                    try:
                        account=bootstrap.authenticate()
                        break
                    except (NetworkUnavailable,RateLimited) as error:
                        pause=error.retry_after if isinstance(error,RateLimited) else 2
                        record.update(state='rate_limited' if isinstance(error,RateLimited) else 'network_wait',
                            phase_since=time.monotonic())
                        if isinstance(error,RateLimited) and pool.on_rate_limit is not None:
                            pool.on_rate_limit(error.retry_after)
                        pool.stop.wait(pause)
                        record.update(state='authenticating',phase_since=time.monotonic())
                else:
                    break
                with pool.lock:
                    owner=pool.identities.setdefault(account.user_id,index)
                if owner!=index or pool.identity_claim is not None and not pool.identity_claim(account.user_id,index):
                    record.update(state='skipped_duplicate',exit_code=0)
                    continue
                record.update(user_id=account.user_id,state='waiting_server')
                request_id+=1
                server=pool._assignment(slot,request_id)
                if server is None:
                    break
                record['current_job']=server
                failures=0
                reconnects=0
                recovering=False
                while not pool._stopping():
                    client=None
                    retry_attempt=recovering
                    try:
                        record.update(state='waiting_turn',phase_since=time.monotonic())
                        if pool.admission is not None and not leased:
                            if not pool.admission(index):
                                break
                            leased=True
                        record.update(state='joining',phase_since=time.monotonic())
                        record['attempts']+=1
                        if retry_attempt:
                            reconnects+=1
                        record['consecutive_reconnects']=reconnects
                        bootstrap._http.deadline=time.monotonic()+30
                        try:
                            if joiner and pool.join_target.get('vip_link'):
                                info=bootstrap.prepare_vip(pool.join_target['vip_link'],attempts=pool.attempts)
                            else:
                                info=bootstrap.prepare_instance(pool.place_id,server,attempts=pool.attempts)
                        finally:
                            bootstrap._http.deadline=None
                        if info.account.user_id!=account.user_id:
                            raise BootstrapError('Account identity changed during startup.')
                        if joiner and pool.join_target.get('vip_link'):
                            from .bootstrap import job_id
                            actual=job_id(info._join_script.get('GameId'))
                            if actual!=server:
                                server=actual
                                record['current_job']=server
                                pool.events.put((index+1,dict(event='joiner_target',job_id=server,place_id=info.place_id)))
                        if pool._stopping():
                            break
                        def report(value):
                            nonlocal failures,reconnects,recovering
                            if value.get('complete') is not True:
                                return
                            failures=0
                            reconnects=0
                            recovering=False
                            record.update(state='active',phase_since=time.monotonic(),
                                scans_completed=record['scans_completed']+1,last_snapshot_at=time.monotonic(),
                                consecutive_reconnects=0)
                            release()  # Admission limits initial loads, not active sockets.
                            pool.events.put((index+1,{**value,'event':'joiner_ready' if joiner else profile+'_snapshot',
                                'sample_id':record['scans_completed'],'server_id':server}))
                        client_type=EggClient if eggs else BrainrotClient
                        extra={'egg_settings':pool.egg_settings} if eggs else {}
                        if joiner:
                            from .joiner import JoinerClient
                            client_type=JoinerClient
                            def command_result(value):
                                if value.get('command')=='looptp':
                                    record['loop_target']=value.get('target') if value.get('active') else None
                                pool.events.put((index+1,dict(event='joiner_command',result=value)))
                            extra=dict(on_ready=report,
                                observe_roster=lambda:pool._roster_observer==index,
                                on_roster=lambda rows:pool.events.put((index+1,dict(event='joiner_roster',players=rows,server_id=server))),
                                on_command=command_result,
                                on_character=lambda value:record.update(character_spawned=value['character_spawned']))
                        else:
                            extra.update(scan_once=True,persistent=True,on_brainrots=report)
                        client=client_type(info,commands=pool.commands[slot],
                            initial_timeout=max(60,pool.scan_timeout),worker_factory=lambda:nullcontext(self.vm),
                            **extra)
                        if joiner and record.get('loop_target'):
                            client.start_loop(record['loop_target'])
                        client.batch_acks=True
                        client.shared_cache=for_place(info.place_id)
                        client.shared_cache_snapshot=client.shared_cache.snapshot()
                        client.open.enable_shared_cache()
                        client.on_scan_progress=lambda value:record.update(progress=value)
                        record.update(state='scanning',phase_since=time.monotonic())
                        if joiner:
                            record['character_spawned']=False
                        client.run(duration=None)
                        if pool._stopping():
                            break
                        failures+=1
                        record['last_disconnect_reason']=client.reason
                    except RateLimited as error:
                        if retry_attempt:
                            reconnects=max(0,reconnects-1)
                        failures+=1
                        record['retry_after_seconds']=error.retry_after
                        if pool.on_rate_limit is not None:
                            pool.on_rate_limit(error.retry_after)
                        release()
                        record.update(state='rate_limited',phase_since=time.monotonic())
                        pool.stop.wait(error.retry_after)
                    except (CryptoError,OSError,NetworkUnavailable,JoinPending,InstanceMismatch,ScanAttemptTimeout) as error:
                        failures+=1
                        record['last_disconnect_reason']=str(error) if isinstance(error,CryptoError) else type(error).__name__
                    except JoinRefused as error:
                        if error.status not in (5,6,10):
                            raise
                        failures+=1
                        record['last_disconnect_reason']='server_unavailable'
                    finally:
                        release()
                        if client is not None:
                            record['received_bytes']+=client.received_bytes
                            if client.world is not None:
                                for name in ('brainrot_sync','brainrot_scanner'):
                                    observer=getattr(client.world,name,None)
                                    if observer is not None:
                                        observer.world=None
                                client.world.client=None
                                client.world=None
                    if not pool._stopping():
                        recovering=True
                        record['consecutive_reconnects']=reconnects
                        if reconnects>=RECONNECT_LIMIT and not joiner:
                            previous=server
                            pool.coordinator.release(slot)
                            record.update(state='waiting_server',phase_since=time.monotonic())
                            request_id+=1
                            server=pool._assignment(slot,request_id)
                            if server is None:
                                break
                            record.update(current_job=server,consecutive_reconnects=0,
                                server_switches=record.get('server_switches',0)+1)
                            pool.events.put((index+1,dict(event='session_server_changed',
                                previous_job=previous,job_id=server,reconnect_limit=RECONNECT_LIMIT)))
                            reconnects=failures=0
                            recovering=False
                            continue
                        pause=min(30,2**min(failures,5))+(index%7)*.1
                        if getattr(client,'disconnect_code',None)==273:
                            pause=max(60,pause)
                        record.update(state='reconnecting',phase_since=time.monotonic())
                        pool.events.put((index+1,dict(event='session_connection',job_id=server,
                            message='Connection lost; reconnecting to the same JobID.',retry_seconds=pause,
                            reason=record.get('last_disconnect_reason'),
                            disconnect_code=getattr(client,'disconnect_code',None))))
                        pool.stop.wait(pause)
            except Exception as error:
                code=failure_code(error)
                record.update(failure_stage=record['state'],state='failed',exit_code=1,
                    failure_type=type(error).__name__,failure_code=code)
                message=str(error) if isinstance(error,BootstrapError) else f'Scanner session failed ({type(error).__name__}; {code}).'
                pool.events.put((index+1,dict(event='error',message=message)))
            finally:
                pool._account_slots.pop(index,None)
                release()
                pool.coordinator.release(slot)
                if record['state'] not in ('failed','skipped_duplicate'):
                    record.update(state='finished',exit_code=0)


EggSessions=PersistentSessions
