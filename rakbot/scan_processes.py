"""A bounded number of Python interpreters, each owning several account sessions.

The parent alone owns public-server selection and console output. Credentials
cross an anonymous spawn pipe only to their account's interpreter; never argv,
temporary files, logs, result snapshots or the server-browser process.
"""
import math
from collections import deque
import multiprocessing
from multiprocessing.connection import wait
import os
import queue
import sys
import threading
import time

from .bootstrap import BootstrapError
from .scan_pool import ScanPool


def process_count(workers, requested=None, *, cpus=None):
    if requested is not None:
        if type(requested) is not int or requested < 1:
            raise ValueError('Scan processes must be a positive integer.')
        return min(workers, requested)
    cores = (os.cpu_count() or 1) if cpus is None else cpus
    if workers <= 2:
        return 1
    return min(workers, 8, max(1, cores // 2), math.ceil(workers / 4))


class _Channel:
    def __init__(self, connection):
        self.connection = connection
        self.lock = threading.Lock()

    def send(self, message):
        with self.lock:
            self.connection.send(message)


class _RemoteCoordinator:
    def __init__(self, pool, channel, commands):
        self.pool, self.channel, self.commands = pool, channel, commands
        self.claims = [queue.Queue(maxsize=1) for _ in pool.credentials]
        self.admissions = [queue.Queue(maxsize=1) for _ in pool.credentials]
        self.stop = threading.Event()

    def start(self):
        self.reader = threading.Thread(target=self._read, daemon=True, name='rakbot-scan-parent')
        self.reader.start()

    def _read(self):
        try:
            while not self.stop.is_set():
                message = self.channel.connection.recv()
                kind = message[0]
                if kind == 'assignment':
                    self.pool.assignments[message[1]].put_nowait(message[2])
                elif kind == 'claim_result':
                    self.claims[message[1]].put_nowait(message[2])
                elif kind == 'admitted':
                    self.admissions[message[1]].put_nowait(True)
                elif kind == 'observer':
                    self.pool._roster_observer=message[1]
                elif kind == 'account_command':
                    slot=self.pool._account_slots.get(message[1])
                    if slot is not None:
                        try:
                            self.pool.commands[slot].put_nowait(message[2])
                        except queue.Full:
                            self.pool.events.put((message[1]+1,dict(event='joiner_command',
                                result=dict(command='error',message='Очередь команд аккаунта заполнена.'))))
                elif kind == 'stop':
                    break
        except (OSError, EOFError, queue.Full):
            pass
        finally:
            self.stop.set()
            try:
                self.commands.put_nowait('quit')
            except queue.Full:
                pass

    def claim(self, user_id, index):
        self.channel.send(('claim', index, user_id))
        while not self.pool._stopping() and not self.stop.is_set():
            try:
                return self.claims[index].get(timeout=0.2)
            except queue.Empty:
                pass
        return False

    def request(self, slot, request_id):
        self.channel.send(('request', slot, request_id))

    def admit(self, index):
        self.channel.send(('admit', index))
        while not self.pool._stopping() and not self.stop.is_set():
            try:
                return self.admissions[index].get(timeout=0.2)
            except queue.Empty:
                pass
        return False

    def release(self, slot):
        self.channel.send(('release', slot))

    def close(self):
        self.stop.set()


class _RemotePool(ScanPool):
    def __init__(self, credentials, options, channel, commands):
        super().__init__(credentials, **options)
        self.channel = channel
        self.coordinator = _RemoteCoordinator(self, channel, commands)
        self.identity_claim = self.coordinator.claim
        self.admission = self.coordinator.admit
        self.release_admission = lambda index: channel.send(('admission_release', index))
        self.on_rate_limit = lambda seconds: channel.send(('rate_limit', seconds))
        self._snapshot_at = 0

    def _drain(self):
        for _ in range(256):
            try:
                index, event = self.events.get_nowait()
            except queue.Empty:
                break
            self.channel.send(('event', index, event))
        now = time.monotonic()
        if now >= self._snapshot_at:
            self._snapshot_at = now + 1
            self.channel.send(('snapshot', self.summary()))

    def report_idle(self):
        pass  # The parent reports aggregate health and owns the console.


def _group_main(connection, credentials, options):
    channel = _Channel(connection)
    try:
        # Parent attaches the process to a Windows kill-on-close job first.
        if connection.recv() != ('start',):
            return
        commands = queue.Queue(maxsize=4)
        pool = _RemotePool(credentials, options, channel, commands)
        result = pool.run(commands)
        channel.send(('done', result))
    except (OSError, EOFError):
        pass
    except BaseException as error:
        # Never serialize exception repr/arguments: they can hold HTTP state.
        try:
            from .scanner_health import failure_code
            channel.send(('error', failure_code(error)))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class _ProcessJob:
    """Keep descendants bounded even if a scanner interpreter crashes."""
    def __init__(self):
        self.handle = None
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', w.DWORD), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t),
                ('active', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops',
                                                            'read_bytes', 'write_bytes', 'other_bytes')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, w.LPCWSTR)
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = (w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD)
        self.kernel.AssignProcessToJobObject.argtypes = (w.HANDLE, w.HANDLE)
        self.kernel.CloseHandle.argtypes = (w.HANDLE,)
        handle = self.kernel.CreateJobObjectW(None, None)
        if not handle:
            raise BootstrapError('Unable to create the scanner process cleanup job.')
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.kernel.CloseHandle(handle)
            raise BootstrapError('Unable to configure scanner process cleanup.')
        self.handle = handle

    def assign(self, process):
        if self.handle and not self.kernel.AssignProcessToJobObject(self.handle, process.sentinel):
            raise BootstrapError('Unable to attach a scanner process to its cleanup job.')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class MultiProcessScanPool(ScanPool):
    def __init__(self, credentials, *, processes=None, process_target=None, join_rate=6, inflight=None, **options):
        super().__init__(credentials, **options)
        if not math.isfinite(join_rate) or join_rate <= 0:
            raise ValueError('Join rate must be finite and positive.')
        self.join_rate = join_rate
        self._admissions = deque()
        self._admit_at = 0
        self.process_count = process_count(self.workers, processes)
        if inflight is not None and (type(inflight) is not int or inflight < 1):
            raise ValueError('Concurrent world loads must be a positive integer.')
        self._adaptive_inflight = inflight is None
        automatic_loads=self.process_count if self.sessions is not None else max(2,self.process_count*3)
        self.inflight = min(self.workers,automatic_loads if inflight is None else inflight)
        self._leased = set()
        self.process_target = process_target or _group_main
        self.children = []
        self._by_slot = {}
        self._by_account={}
        self._observer_account=None
        self._job = None
        self.coordinator.assignment_sink = self._assignment_to_child
        self.coordinator.prefetch = max(10, self.workers * 2)
        self._options = dict(place_id=self.place_id, attempts=self.attempts,
            scan_timeout=self.scan_timeout, hop_timeout=self.hop_timeout,
            adaptive_timeouts=self.adaptive_timeouts, scan_status=False, duration=None,egg_settings=self.egg_settings,
            stay_connected=self.sessions is not None,join_target=self.join_target)
        if self.workers > 2 and self.adaptive_timeouts:
            # Aggregate throughput needs complete maps, rather than throwing
            # away megabytes whenever concurrent transfers exceed 3 seconds.
            self._options.update(scan_timeout=20, hop_timeout=20)

    def _assignment_to_child(self, slot, event):
        child, local_slot = self._by_slot[slot]
        try:
            child['channel'].send(('assignment', local_slot, event))
        except (OSError, EOFError):
            self.coordinator.release(slot)

    def _snapshot(self, child, result):
        if child['done']:
            return  # A queued pre-crash snapshot must not resurrect dead sessions.
        for local, record in enumerate(result['accounts']):
            index = child['indices'][local]
            self.accounts[index] = {**record, 'account': index + 1}

    def _failure(self, child, message, code='process_exit'):
        if child['done']:
            return
        child['done'] = True
        self._leased = {key for key in self._leased if key[0] != id(child)}
        affected=0
        for index in child['indices']:
            if self.accounts[index]['state'] not in ('failed', 'skipped_duplicate', 'finished', 'unused'):
                affected+=1
                self.accounts[index]['failure_stage']=self.accounts[index]['state']
                self.accounts[index].update(state='failed', exit_code=1,failure_code=code,
                    failure_type='ProcessGroupFailure')
        for slot in child['slots']:
            self.coordinator.release(slot)
        exit_code=child['process'].exitcode
        details=f" Affected accounts: {affected}; cause: {code}."
        if exit_code is not None:
            details+=f' Process exit code: {exit_code}.'
        self._event(child['indices'][0] + 1, {'event': 'error', 'message': message+details})

    def _event(self, index, event):
        try:
            self.events.put_nowait((index, event))
        except queue.Full:
            self._drain()
            self.events.put_nowait((index, event))

    def _receive(self, child):
        connection = child['channel'].connection
        try:
            # Bound a turn so one active group cannot starve console/cancel.
            for _ in range(64):
                if not connection.poll():
                    break
                message = connection.recv()
                kind = message[0]
                if kind == 'request':
                    self.coordinator.request(child['slots'][message[1]], message[2])
                elif kind == 'admit':
                    self._admissions.append((child, message[1]))
                elif kind == 'admission_release':
                    self._leased.discard((id(child), message[1]))
                elif kind == 'rate_limit':
                    self._admit_at = max(self._admit_at, time.monotonic() + message[1])
                elif kind == 'release':
                    self.coordinator.release(child['slots'][message[1]])
                elif kind == 'claim':
                    index = child['indices'][message[1]]
                    user_id = message[2]
                    owner = self.identities.setdefault(user_id, index)
                    child['channel'].send(('claim_result', message[1], owner == index))
                elif kind == 'event':
                    if message[2].get('event')=='joiner_roster' and child['indices'][message[1]-1]!=self._observer_account:
                        continue
                    if message[2].get('event')=='joiner_target' and self.join_target and self.join_target.get('vip_link'):
                        event=message[2]
                        with self.coordinator.lock:
                            self.coordinator.server=event['job_id']
                            self.resolved_target=dict(job_id=event['job_id'],place_id=event['place_id'])
                        source=child['indices'][message[1]-1]
                        for index,record in enumerate(self.accounts):
                            if index!=source and record['state']=='active' and record.get('current_job')!=event['job_id']:
                                self.join_command('quit',index+1)
                        continue
                    if (message[2].get('event')=='joiner_roster' and self.resolved_target and
                            message[2].get('server_id')!=self.resolved_target['job_id']):
                        continue
                    if message[2].get('event') in ('egg_snapshot','brainrot_snapshot'):
                        child['warm']=True
                    if message[2].get('event') == 'scan_metrics' and message[2].get('cache_available', 0) >= 512:
                        child['warm'] = True
                    self._event(child['indices'][message[1] - 1] + 1, message[2])
                elif kind in ('snapshot', 'done'):
                    self._snapshot(child, message[1])
                    if kind == 'done':
                        child['done'] = True
                        self._leased = {key for key in self._leased if key[0] != id(child)}
                elif kind == 'error':
                    from .scanner_health import FAILURES
                    code=message[1] if message[1] in FAILURES else 'process_exit'
                    self._failure(child, 'Scanner process failed; other groups continue.',code)
                    break
        except (EOFError, OSError):
            if not child['done']:
                self._failure(child, 'Scanner process exited unexpectedly; other groups continue.')

    def _service(self, timeout=0.05):
        children = [c for c in self.children if not c['done']]
        if children:
            ready = wait([c['channel'].connection for c in children], timeout=timeout)
            for child in children:
                if child['channel'].connection in ready:
                    self._receive(child)
                elif not child['process'].is_alive():
                    self._receive(child)
                    if not child['done']:
                        self._failure(child, 'Scanner process exited unexpectedly; other groups continue.')
        self._grant_admission()
        if self.join_target is not None:
            self._update_observer()
        self._drain()

    def _update_observer(self):
        current=self._observer_account
        if current is not None and self.accounts[current]['state']=='active':
            return
        chosen=next((i for i,a in enumerate(self.accounts) if a['state']=='active'),None)
        if chosen==current:
            return
        self._observer_account=chosen
        for child in self.children:
            if child['done']:
                continue
            local=child['indices'].index(chosen) if chosen in child['indices'] else None
            try:
                child['channel'].send(('observer',local))
            except (EOFError,OSError):
                pass
        if self.on_roster is not None:
            self.on_roster(0,dict(players=[],server_id=self.resolved_target['job_id'] if self.resolved_target else None,
                observer_changed=True))

    def join_command(self,line,account=None):
        # Only the GUI host invokes this with validated game commands.
        sent=0
        for index,record in enumerate(self.accounts):
            if record['state']!='active' or account is not None and index+1!=account:
                continue
            target=self._by_account.get(index)
            if target is None:
                continue
            child,local=target
            try:
                child['channel'].send(('account_command',local,line))
                sent+=1
            except (EOFError,OSError):
                pass
        return sent

    def _grant_admission(self):
        now = time.monotonic()
        if self._stopping() or now < self._admit_at or len(self._leased) >= self.inflight:
            return
        while self._admissions:
            # Keep the admitted maps distributed across CPU groups. A group
            # that spawned first must not fill every network/CPU slot.
            eligible = [i for i, (child, _) in enumerate(self._admissions)
                        if not self._adaptive_inflight or sum(key[0] == id(child) for key in self._leased)
                        < (3 if child.get('warm') else 1)]
            if not eligible:
                return
            pos = min(eligible, key=lambda i:
                (sum(key[0] == id(self._admissions[i][0]) for key in self._leased), i))
            self._admissions.rotate(-pos)
            child, index = self._admissions.popleft()
            self._admissions.rotate(pos)
            if child['done']:
                continue
            try:
                child['channel'].send(('admitted', index))
            except (EOFError, OSError):
                continue
            self._leased.add((id(child), index))
            self._admit_at = now + 1 / self.join_rate
            break

    def run(self, commands):
        if not self.workers:
            return self.summary()
        origin = time.monotonic()
        self._run_started_at = origin
        self.title.started = origin
        self.refresh_title(force=True)
        self.deadline = None if self.duration is None else origin + self.duration
        self._last_best_at, self._idle_notice_at = origin, origin + 15
        context = multiprocessing.get_context('spawn')
        groups = [[] for _ in range(self.process_count)]
        for slot in range(self.workers):
            groups[slot % self.process_count].append(slot)
        for index in range(self.workers, len(self.credentials)):
            groups[index % self.process_count].append(index)
        self._job = _ProcessJob()
        self.coordinator.start()
        try:
            for number, indices in enumerate(groups):
                slots = [i for i in indices if i < self.workers]
                parent_conn, child_conn = context.Pipe()
                options = {**self._options, 'workers': len(slots)}
                process = context.Process(target=self.process_target,
                    args=(child_conn, [self.credentials[i] for i in indices], options),
                    name=f'rakbot-scan-group-{number + 1}')
                child = dict(process=process, channel=_Channel(parent_conn),
                             indices=indices, slots=slots, done=False)
                process.start()
                child_conn.close()
                self.children.append(child)
                for local,index in enumerate(indices):
                    self._by_account[index]=(child,local)
                for local_slot, slot in enumerate(slots):
                    self._by_slot[slot] = (child, local_slot)
                self._job.assign(process)
                child['channel'].send(('start',))
            while not self._stopping() and any(not c['done'] for c in self.children):
                self._service()
                self.report_idle()
                if self.scan_status and time.monotonic() >= self._status_at:
                    self.show_status()
                    self._status_at = time.monotonic() + 5
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    continue
                if isinstance(command,dict) and self.join_target is not None:
                    self.join_command(command['line'],command.get('account'))
                    continue
                command=command.strip().casefold()
                if command in ('quit', 'exit'):
                    break
                if command == 'status':
                    self.show_status()
        finally:
            self.stop.set()
            for child in self.children:
                if not child['done']:
                    try:
                        child['channel'].send(('stop',))
                    except (EOFError, OSError):
                        pass
            close_deadline = time.monotonic() + 15
            while any(c['process'].is_alive() for c in self.children) and time.monotonic() < close_deadline:
                self._service()
                for child in self.children:
                    child['process'].join(timeout=0)
            for child in self.children:
                if child['process'].is_alive():
                    self._failure(child, 'Scanner process did not stop within its cleanup deadline.')
                    child['process'].terminate()
                child['process'].join(timeout=2)
                self._receive(child)
                child['channel'].connection.close()
            self.coordinator.close()
            self._job.close()  # Also closes any descendants of a crashed group.
            self._drain()
            self.refresh_title(force=True)
            for record in self.accounts:
                if record['state'] == 'queued':
                    record['state'] = 'unused'
        return self.summary()

    def summary(self):
        result = super().summary()
        result.update(started_workers=min(self.workers, sum(len(c['slots']) for c in self.children)),
            python_subprocesses=len(self.children), process_groups=len(self.children),
            processes_still_running=sum(c['process'].is_alive() for c in self.children),
            join_rate_limit=self.join_rate)
        result.update(world_load_limit=self.inflight, active_world_loads=len(self._leased))
        return result
