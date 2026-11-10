"""Persistent account scanners without spawning Python per account."""
from contextlib import nullcontext
from collections import Counter, deque
import math
import queue
import threading
import time

from .bootstrap import BootstrapError, InstanceMismatch, JoinRefused, JoinPending, RateLimited, NetworkUnavailable, RobloxBootstrap, RobloxHTTP
from .brainrot import Output, PLACE_ID
from .game_client import GameClient
from .luau_worker import Worker, HopBridgeError
from .native_crypto import CryptoError
from .server_pool import Coordinator, PublicServers


class ScanAttemptTimeout(BootstrapError):
    pass


class ScanHTTP(RobloxHTTP):
    """Carry one join deadline through identity/CSRF/loading HTTP retries."""
    deadline = None

    def request(self, *args, **kwargs):
        timeout = self.timeout
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise ScanAttemptTimeout('Scanner join deadline elapsed.')
            self.timeout = min(timeout, remaining)
        try:
            return super().request(*args, **kwargs)
        except BootstrapError:
            if self.deadline is not None and time.monotonic() >= self.deadline:
                raise ScanAttemptTimeout('Scanner join deadline elapsed.') from None
            raise
        finally:
            self.timeout = timeout


class ScanPool:
    def __init__(self, credentials, *, place_id, attempts=3, duration=None,
                 workers=4, emit=print, emit_batch=None, scan_timeout=4, hop_timeout=3, scan_status=False,
                 adaptive_timeouts=True, featured_pets=(), set_title=None,egg_settings=None,stay_connected=True,join_target=None):
        if type(workers) is not int or workers < 1:
            raise ValueError('Scan workers must be a positive integer.')
        if type(place_id) is not int or not 0 < place_id < 2**63:
            raise ValueError('Invalid Place ID.')
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError('Attempts must be 1..5.')
        if duration is not None and (not math.isfinite(duration) or not 1 <= duration <= 300):
            raise ValueError('Duration must be finite and in 1..300 seconds.')
        if not math.isfinite(scan_timeout) or not 1 <= scan_timeout <= 75:
            raise ValueError('Scan timeout must be finite and in 1..75 seconds.')
        if not math.isfinite(hop_timeout) or not 1 <= hop_timeout <= 75:
            raise ValueError('Hop timeout must be finite and in 1..75 seconds.')
        self.credentials = credentials
        self.join_target=join_target
        self._roster_observer=None
        self._account_slots={}
        self.on_roster=None
        self.on_join_command=None
        self.resolved_target=None
        self.place_id, self.attempts, self.duration = place_id, attempts, duration
        from .egg_filter import settings
        self.egg_settings=settings(egg_settings) if place_id==107778070777162 else None
        self.workers = min(workers, len(credentials))
        self.emit, self.emit_batch = emit, emit_batch
        self.scan_timeout, self.hop_timeout, self.scan_status = scan_timeout, hop_timeout, scan_status
        self.adaptive_timeouts = adaptive_timeouts and max(scan_timeout, hop_timeout) <= 4
        self._status_at = 0
        self._last_best_at = self._idle_notice_at = 0
        self._run_started_at = None
        self._best_count = 0
        self._best_times = deque(maxlen=2000)
        self.output = Output(only_best=True)
        self.on_scan_metrics = None
        self.on_scan_report = None
        self.on_server_switch = None
        from .scan_title import ScanTitle
        self.title = ScanTitle(featured_pets)
        self.set_title = set_title
        self._title_at = 0
        self.stop = threading.Event()
        self.events = queue.Queue(maxsize=256)
        self.tasks = queue.Queue()
        self.assignments = [queue.Queue(maxsize=1) for _ in range(self.workers)]
        self.coordinator = Coordinator(place_id, self.events, assignment_interval=0,
            browser=PublicServers(place_id, prefer_fast=True, min_players=6 if place_id == PLACE_ID else 0),
            assignment_sink=lambda slot, event: self.assignments[slot].put_nowait(event), preload=True)
        if join_target is not None:
            from .joiner import PinnedCoordinator
            self.coordinator=PinnedCoordinator(self,join_target)
        self.commands = [queue.Queue(maxsize=4) for _ in range(self.workers)]
        self.threads = []
        self.lock = threading.Lock()
        self.identities = {}
        self.identity_claim = None  # Optional cross-process ownership check.
        self.admission = self.on_rate_limit = None
        self.release_admission = None
        self.accounts = [dict(account=i + 1, state='queued', user_id=None, exit_code=None,
                              scans_completed=0, luau_hops=0, luau_hop_requests=0,
                              scans_skipped=0, attempts=0, current_job=None,
                              consecutive_timeouts=0, adaptive_budget_seconds=0,
                              received_bytes=0,
                              network_failures=0,
                              phase_since=0, progress={}) for i in range(len(credentials))]
        self.auth = {}  # Each account task has exactly one owner at a time.
        self.egg_sessions=None
        self.sessions=None
        self._egg_sample_ids={}
        self._egg_servers=set()
        self._session_feature_ids={}
        self._session_best={}
        if stay_connected and (join_target is not None or self.place_id in (107778070777162,PLACE_ID)):
            from .egg_sessions import PersistentSessions
            self.sessions=PersistentSessions(self)
            if self.place_id==107778070777162 and join_target is None:
                self.egg_sessions=self.sessions
        for index in range(len(credentials)):
            self.tasks.put(index)
        self.deadline = None

    def _stopping(self):
        return self.stop.is_set() or self.deadline is not None and time.monotonic() >= self.deadline

    def _remaining(self):
        return 75 if self.deadline is None else min(75, self.deadline - time.monotonic())

    def _assignment(self, slot, request_id):
        self.coordinator.request(slot, request_id)
        while not self._stopping():
            try:
                event = self.assignments[slot].get(timeout=0.2)
            except queue.Empty:
                continue
            if event.get('request_id') == request_id:
                return event['job_id']
        return None

    def _scan(self, slot, index, bootstrap, account, server, vm):
        started = time.monotonic()
        record = self.accounts[index]
        budget = min(self.scan_timeout, self.hop_timeout) if record['attempts'] > 1 else self.scan_timeout
        budget = max(budget, record['adaptive_budget_seconds'])
        deadline = started + budget
        record['last_budget_seconds'] = budget
        if self.deadline is not None:
            deadline = min(deadline, self.deadline)
        http = getattr(bootstrap, '_http', None)
        if isinstance(http, ScanHTTP):
            http.deadline = deadline
        try:
            info = bootstrap.prepare_instance(self.place_id, server, attempts=self.attempts)
        finally:
            if isinstance(http, ScanHTTP):
                http.deadline = None
        self.accounts[index]['last_join_seconds'] = round(time.monotonic() - started, 3)
        if info.account.user_id != account.user_id:
            raise BootstrapError('Account identity changed during startup.')
        if self._stopping():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ScanAttemptTimeout('Scanner join deadline elapsed.')
        snapshot = {}
        client_type = GameClient
        if self.place_id == 107778070777162:
            from .egg_client import EggClient
            client_type = EggClient
        client = client_type(info, commands=self.commands[slot], scan_once=True,
                            worker_factory=lambda: nullcontext(vm),
                            on_brainrots=lambda value: snapshot.update(value))
        # In the 4/3-second mode, a remote server cannot deliver a full world in
        # time. Measure its actual first reply rather than spending the budget.
        client.scan_rtt_limit = 0.11 if budget <= 4 else None
        client.batch_acks = True
        from .shared_cache import for_place
        client.shared_cache = for_place(self.place_id)
        client.shared_cache_snapshot = client.shared_cache.snapshot()
        if budget > 4 and len(client.shared_cache_snapshot) >= 512 and record['consecutive_timeouts'] < 3:
            client.scan_rtt_limit = client.shared_cache.rtt_limit()
        if getattr(client, 'open', None) is not None:
            client.open.enable_shared_cache()
        record = self.accounts[index]
        record.update(state='scanning', phase_since=time.monotonic())
        client.on_scan_progress = lambda value: record.update(progress=value)
        try:
            started = time.monotonic()
            # Native transport accepts sub-second remaining budgets internally.
            client._scan_deadline = deadline
            result = client.run(duration=max(1, remaining))
            self.accounts[index]['last_game_seconds'] = round(time.monotonic() - started, 3)
            self.accounts[index]['last_milestones'] = dict(getattr(client, 'scan_milestones', {}))
            if client.scan_complete and snapshot.get('complete') is True:
                snapshot['server_id'] = server  # prepare_instance verifies canonical GameId.
                self.accounts[index]['scans_completed'] += 1
                record['consecutive_timeouts'] = 0
                self.events.put((index + 1, {'event': 'brainrot_scan', **snapshot}))
                return True
            reason = result.get('stop_reason')
            if reason == 'duration_elapsed':
                reason = 'scan_timeout'
            self._skip(index, server, reason)
            return result.get('transport_accepted') is True
        finally:
            record['received_bytes'] += getattr(client, 'received_bytes', 0)
            client.shared_cache.observe_rtt(getattr(client, 'scan_milestones', {}).get('open_rtt'))
            sync = getattr(client.world, 'brainrot_sync', None) if client.world is not None else None
            tag_counts = Counter()
            if sync is not None and hasattr(sync, 'models'):
                for key in sync.models:
                    node = client.world.nodes.get(key)
                    digest = node['props'].get('Tags') if node else None
                    tag = sync.blobs.get(digest)
                    state = ('no_property' if digest is None else 'no_blob' if tag is None else
                             'animal' if b'Animal' in tag.split(b'\0') else 'other_tag')
                    tag_counts[state] += 1
            self.events.put((index + 1, {'event': 'scan_metrics',
                'complete': client.scan_complete, 'seconds': round(time.monotonic() - started, 4),
                'join_seconds': record.get('last_join_seconds'),
                'bytes': getattr(client, 'received_bytes', 0),
                'datagrams': getattr(client, 'received_datagrams', 0),
                'acks': getattr(client, 'ack_datagrams_sent', 0),
                'nacks': getattr(client, 'nack_datagrams_sent', 0),
                'gaps': getattr(getattr(client, 'datagram_loss', None), 'detected', 0),
                'reported_gaps': getattr(getattr(client, 'datagram_loss', None), 'reported', 0),
                'retained_nodes': len(client.world.nodes) if client.world is not None and hasattr(client.world, 'nodes') else 0,
                'retransmits': getattr(client, 'resent', 0),
                'cache_advertised': len(getattr(client, 'shared_cache_advertised', {})),
                'cache_available': len(client.shared_cache.snapshot()),
                'cache_bytes': client.shared_cache.size,
                'rtt_limit': client.scan_rtt_limit,
                'road_models': len(getattr(sync, 'models', {})),
                'road_population': len(sync.road_population()) if callable(getattr(sync, 'road_population', None)) else 0,
                'road_tags': dict(tag_counts),
                'decode_stops': dict(client.world.stops) if client.world is not None and hasattr(client.world, 'stops') else {},
                'reason': getattr(client, 'reason', None),
                'phases': dict(getattr(client, 'scan_milestones', {}))}))
            # Break the World -> Sync/Scanner -> World and World -> Client cycles
            # immediately; the next map must not overlap an old map until GC.
            world = client.world
            if world is not None:
                if world.brainrot_sync is not None:
                    world.brainrot_sync.world = None
                if world.brainrot_scanner is not None:
                    world.brainrot_scanner.world = None
                world.client = None
                client.world = None

    def _worker(self, slot):
        if self.sessions is not None:
            return self.sessions.worker(slot)
        request_id, vm, index, current_server = 0, None, None, None
        try:
            while not self._stopping():
                if index is None:
                    try:
                        index = self.tasks.get_nowait()
                    except queue.Empty:
                        return
                record = self.accounts[index]
                server = None
                retry = True
                try:
                    if self.admission is not None:
                        record.update(state='waiting_turn', phase_since=time.monotonic())
                        if not self.admission(index):
                            break
                    record.update(state='authenticating', phase_since=time.monotonic())
                    cached = self.auth.get(index)
                    if cached is None:
                        bootstrap = RobloxBootstrap(self.credentials[index], http=ScanHTTP())
                        account = bootstrap.authenticate()
                        self.auth[index] = (bootstrap, account)
                    else:
                        bootstrap, account = cached
                    with self.lock:
                        owner = self.identities.setdefault(account.user_id, index)
                    if owner != index or self.identity_claim is not None and not self.identity_claim(account.user_id, index):
                        record.update(state='skipped_duplicate', exit_code=0)
                        retry = False
                        continue
                    record['user_id'] = account.user_id
                    record.update(state='waiting_server', current_job=None, progress={}, phase_since=time.monotonic())
                    request_id += 1
                    server = self._assignment(slot, request_id)
                    if server is None:
                        break
                    if self._stopping():
                        break
                    record.update(state='joining', current_job=server, phase_since=time.monotonic())
                    record['attempts'] += 1
                    if vm is None:
                        vm = Worker().__enter__()
                    if current_server is not None:
                        vm.teleport(self.place_id, server, current_server, account.user_id)
                        record['luau_hop_requests'] += 1
                    if self._scan(slot, index, bootstrap, account, server, vm):
                        if current_server is not None:
                            record['luau_hops'] += 1
                        current_server = server
                    record['network_failures'] = 0
                except InstanceMismatch:
                    self._skip(index, server, 'unexpected_server')
                except (ScanAttemptTimeout, JoinPending):
                    self._skip(index, server, 'join_timeout')
                except RateLimited as error:
                    record.update(state='rate_limited', phase_since=time.monotonic(),
                                  retry_after_seconds=error.retry_after)
                    self._skip(index, server, 'http_rate_limited')
                    if self.on_rate_limit is not None:
                        self.on_rate_limit(error.retry_after)
                    pause = error.retry_after
                    if self.deadline is not None:
                        pause = min(pause, max(0, self.deadline - time.monotonic()))
                    self.stop.wait(pause)
                except NetworkUnavailable:
                    record['network_failures'] += 1
                    self._skip(index, server, 'https_network_error')
                    pause = min(15, 2 ** min(record['network_failures'] - 1, 4))
                    if self.deadline is not None:
                        pause = min(pause, max(0, self.deadline - time.monotonic()))
                    record.update(state='network_wait', phase_since=time.monotonic())
                    self.stop.wait(pause)
                except JoinRefused as error:
                    if error.status not in (5, 6, 10):
                        retry = False
                        record.update(state='failed', exit_code=1)
                        self.events.put((index + 1, {'event': 'error', 'message': str(error)}))
                    else:
                        self._skip(index, server, 'server_unavailable')
                except (CryptoError, OSError):
                    self._skip(index, server, 'transport_interrupted')
                    # Retry on another server, without retaining broken VM state.
                    if vm is not None:
                        vm.close()
                        vm = None
                    self.stop.wait(0.1)
                except Exception as error:
                    if vm is not None:
                        vm.close()
                        vm = None
                    retry = False
                    record.update(state='failed', exit_code=1)
                    if isinstance(error, HopBridgeError):
                        self.stop.set()
                    message = str(error) if isinstance(error, (BootstrapError, HopBridgeError)) else 'Scanner slot failed.'
                    self.events.put((index + 1, {'event': 'error', 'message': message}))
                finally:
                    if self.release_admission is not None:
                        self.release_admission(index)
                    self.coordinator.release(slot)
                    if retry:
                        record.update(state='waiting_server', exit_code=0)
                    else:
                        index, current_server = None, None
        finally:
            if vm is not None:
                vm.close()

    def _drain(self):
        messages = []
        for _ in range(256):
            try:
                index, event = self.events.get_nowait()
            except queue.Empty:
                break
            if event.get('event') == 'hop_assignment':
                self.assignments[index].put_nowait(event)
            elif event.get('event')=='joiner_ready':
                self.title.servers=1
                messages.append(f"JOINED : account[{index}] | JobID: {event['server_id']}")
            elif event.get('event')=='joiner_roster':
                if self.on_roster is not None:
                    self.on_roster(index,event)
            elif event.get('event')=='joiner_command':
                if self.on_join_command is not None:
                    self.on_join_command(index,event['result'])
            elif event.get('event') in ('egg_snapshot','brainrot_snapshot'):
                sample=event.get('sample_id',0)
                if event.get('complete') is not True or sample<=self._egg_sample_ids.get(index,0):
                    continue
                self._egg_sample_ids[index]=sample
                self._egg_servers.add(event['server_id'])
                rows=event.get('rows',[])
                if event['event']=='brainrot_snapshot':
                    from .brainrot import ordered,format_row,best_time
                    from .scan_title import normalized_name
                    seen=self._session_feature_ids.setdefault(index,{})
                    added=0
                    for row in rows:
                        identity=(event['server_id'],str(row.get('id')))
                        if normalized_name(row.get('DisplayName')) in self.title.names and identity not in seen:
                            added+=1
                            seen[identity]=None
                    while len(seen)>4096:
                        seen.pop(next(iter(seen)))
                    featured_count=self.title.featured_count
                    self.title.observe(rows)
                    self.title.featured_count=featured_count+added
                    best=next(iter(ordered(rows)),None)
                    fingerprint=(event['server_id'],best)
                    if self._session_best.get(index)!=fingerprint:
                        messages.append(f'[{best_time()}] BEST : '+(format_row(best) if best else '—')+
                            ' | JobID: '+event['server_id'])
                        self._session_best[index]=fingerprint
                else:
                    self.title.observe(rows)
                self.title.servers=len(self._egg_servers)
                self._last_best_at=time.monotonic()
                self._best_count+=1
                self._best_times.append(self._last_best_at)
                if self.on_scan_report is not None:
                    self.on_scan_report(index,event)
                if event['event']=='brainrot_snapshot':
                    continue
                schedule=event.get('schedule',{})
                phase=schedule.get('phase')
                if phase=='paused':
                    next_scan='cycle paused'
                elif phase in ('night','interval'):
                    next_scan=f"{schedule['wait_seconds']:.1f}s"
                else:
                    next_scan=f"server reset -> night + {schedule.get('reset_grace',2):g}s grace"
                messages.append(f"EGGS : account[{index}] | {len(event.get('rows',[]))} matched eggs | JobID: {event['server_id']} | next scan: {next_scan}")
            elif event.get('event') in ('egg_connection','session_connection'):
                reason=event.get('reason') or 'unknown'
                code=event.get('disconnect_code')
                details=f" | reason: {reason}"+(f' | disconnect code: {code}' if code is not None else '')
                messages.append(f"SESSION : account[{index}] | JobID: {event['job_id']} | {event['message']}"+details)
            elif event.get('event')=='session_server_changed':
                messages.append(f"SESSION : account[{index}] | {event.get('reconnect_limit',5)} failed reconnects; new JobID: {event['job_id']}")
                if self.on_server_switch is not None:
                    self.on_server_switch(index,event)
            elif event.get('event') == 'scan_metrics':
                if self.on_scan_metrics is not None:
                    self.on_scan_metrics(index, event)
            elif event.get('event') == 'scan_notice':
                if self.scan_status:
                    mode = ' | adaptive budget: 20s, RTT filter off' if event.get('relaxed') else ''
                    messages.append(f"SCAN : account[{index}] | JobID: {event['job_id']} | skip: {event['reason']} | next server{mode}")
            elif event.get('event') == 'hop_warning':
                messages.extend(self.output.event(index + 1, {'event': 'error', 'message': event['message']}))
            else:
                lines = self.output.event(index, event)
                if event.get('event') == 'brainrot_scan' and lines:
                    self.title.observe(event.get('rows', []))
                    if self.on_scan_report is not None:
                        self.on_scan_report(index, event)
                    self._last_best_at = time.monotonic()
                    self._best_count += 1
                    self._best_times.append(self._last_best_at)
                    self._idle_notice_at = self._last_best_at + 15
                messages.extend(lines)
        if self.emit_batch is not None:
            self.emit_batch(messages)
        else:
            for message in messages:
                self.emit(message)
        self.refresh_title()

    def refresh_title(self, *, force=False):
        if self.set_title is None:
            return
        now = time.monotonic()
        if force or now >= self._title_at:
            self._title_at = now + 1
            self.set_title(self.title.render(now))

    def _skip(self, index, server, reason):
        record = self.accounts[index]
        record['scans_skipped'] += 1
        record['last_skip_reason'] = reason
        timed_out = reason in ('server_latency_limit', 'scan_timeout', 'join_timeout', 'initial_scan_stalled')
        record['consecutive_timeouts'] = record['consecutive_timeouts'] + 1 if timed_out else 0
        relaxed = (self.adaptive_timeouts and record['consecutive_timeouts'] >= 3
                   and not record['adaptive_budget_seconds'])
        if relaxed:
            # A strict low RTT/deadline loop can otherwise skip every server on
            # a slower host/route forever. Keep the same account and finish as
            # soon as data arrives; this is a ceiling, not a mandatory sleep.
            record['adaptive_budget_seconds'] = 20
        if not self._stopping():
            self.events.put((index + 1, {'event': 'scan_notice', 'job_id': server,
                                       'reason': reason, 'relaxed': relaxed}))

    def report_idle(self):
        if self.sessions is not None:
            return
        now = time.monotonic()
        if self.scan_status or now < self._idle_notice_at or now - self._last_best_at < 15:
            return
        self._idle_notice_at = now + 30
        active = [a for a in self.accounts if a['state'] in
                  ('authenticating', 'waiting_server', 'joining', 'scanning', 'waiting_turn', 'rate_limited', 'network_wait')]
        if not active:
            return
        failed = sum(a['state'] == 'failed' for a in self.accounts)
        reasons = Counter(a.get('last_skip_reason') for a in active if a.get('last_skip_reason'))
        details = ', '.join(f'{reason}: {count}' for reason, count in sorted(reasons.items()))
        relaxed = sum(bool(a['adaptive_budget_seconds'] or a.get('last_budget_seconds', 0) > 4) for a in active)
        phase = ', '.join(f'{state}: {count}' for state, count in sorted(Counter(a['state'] for a in active).items()))
        line = (f'WARN : no BEST for {now - self._last_best_at:.0f}s | active: {len(active)} | failed: {failed}'
                f' | {phase} | relaxed budget: {relaxed}'
                + (f' | last skips: {details}' if details else '')
                + ' | type status or add --scan-status')
        self.emit(line)

    def show_status(self):
        now = time.monotonic()
        lines = []
        for record in self.accounts:
            if record['state'] not in ('authenticating', 'waiting_server', 'joining', 'scanning', 'waiting_turn', 'rate_limited', 'network_wait','active','reconnecting'):
                continue
            progress = record['progress']
            details = ''
            if progress:
                details = (f" | catalogs {progress['catalogs']}/3 | plots {progress['received']}/{progress['announced']}"
                           f" | road {progress['road']}/{progress['road_required']}")
            lines.append(f"SCAN : account[{record['account']}] | JobID: {record['current_job'] or '-'}"
                      f" | {record['state']}{details} | {max(0, now - record['phase_since']):.1f}s"
                      f" | attempts {record['attempts']} | BEST {record['scans_completed']} | skipped {record['scans_skipped']}"
                      + (f" | reconnects {record.get('consecutive_reconnects',0)}/5 | server switches {record.get('server_switches',0)}" if self.sessions is not None else '')
                      + (f" | budget {record['last_budget_seconds']}s" if 'last_budget_seconds' in record else ''))
        if self._run_started_at is not None:
            window = min(10, max(0.001, now - self._run_started_at))
            rate = sum(t >= now - 10 for t in self._best_times) / window
            metric='snapshots' if self.sessions is not None else 'BEST'
            lines.append(f'SCAN : aggregate {rate:.2f} {metric}/s over {window:.0f}s | total {metric} {self._best_count}')
        if self.emit_batch is not None:
            self.emit_batch(lines)
        else:
            for line in lines:
                self.emit(line)

    def run(self, commands):
        self.deadline = None if self.duration is None else time.monotonic() + self.duration
        self._last_best_at = time.monotonic()
        self._run_started_at = self._last_best_at
        self.title.started = self._run_started_at
        self.refresh_title(force=True)
        self._idle_notice_at = self._last_best_at + 15
        self.coordinator.start()
        try:
            for slot in range(self.workers):
                thread = threading.Thread(target=self._worker, args=(slot,), name=f'rakbot-scan-{slot + 1}')
                thread.start()
                self.threads.append(thread)
            while not self._stopping() and any(t.is_alive() for t in self.threads):
                self._drain()
                self.report_idle()
                if self.scan_status and time.monotonic() >= self._status_at:
                    self.show_status()
                    self._status_at = time.monotonic() + 5
                try:
                    command = commands.get(timeout=0.1).strip().casefold()
                    if command in ('quit', 'exit'):
                        break
                    if command == 'status':
                        self.show_status()
                except queue.Empty:
                    pass
        finally:
            self.stop.set()
            for commands_for_slot in self.commands:
                commands_for_slot.put_nowait('quit')
            # HTTP and UDP have bounded timeouts. Join every slot so no session
            # or VM survives this run; drain output while workers shut down.
            while any(t.is_alive() for t in self.threads):
                self._drain()
                for thread in self.threads:
                    thread.join(timeout=0.05)
            self.coordinator.close()
            if self.sessions is not None:
                self.sessions.close()
            self._drain()
            self.refresh_title(force=True)
            self.auth.clear()
            from .shared_cache import save_all
            save_all()
            for record in self.accounts:
                if record['state'] == 'waiting_server':
                    record.update(state='finished', exit_code=0)
                elif record['state'] == 'queued':
                    record['state'] = 'unused'
        return self.summary()

    def summary(self):
        from .schema import Reader
        return {'state': 'mass_finished', 'requested_accounts': len(self.credentials),
                'started_workers': len(self.threads), 'python_subprocesses': 0,
                'native_reader': Reader.__module__ == 'rakbot._reader',
                'unique_user_ids': len(self.identities),
                'skipped_duplicates': sum(a['state'] == 'skipped_duplicate' for a in self.accounts),
                'accounts': [dict(a) for a in self.accounts]}
