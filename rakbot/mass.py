"""Multiple isolated game sessions controlled from one bounded console."""
from collections import deque
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from .bootstrap import BootstrapError, Credential, parse_vip_link
from .console import Console


MAX_ACCOUNTS = 999999


def read_mass_credentials(path, count):
    if type(count) is not int or not 1 <= count <= MAX_ACCOUNTS:
        raise BootstrapError(f'Mass account count must be 1..{MAX_ACCOUNTS}.')
    selected, seen = [], set()
    try:
        with Path(path).open('r',encoding='utf-8-sig',newline=None) as stream:
            number=0
            while line:=stream.readline(65539):
                number+=1
                if len(line.rstrip('\r\n'))>65536:
                    raise BootstrapError(f'Mass session line {number} exceeds the size limit.')
                value=line.strip()
                if not value or value.startswith('#'):
                    continue
                # Export fields before the warning marker are not credentials.
                marker=value.find('_|WARNING')
                if marker>=0:
                    value=value[marker:]
                try:
                    credential=Credential(value)
                except BootstrapError:
                    raise BootstrapError(f'Invalid cookie on mass session line {number}.') from None
                if credential.value in seen:
                    continue
                seen.add(credential.value)
                selected.append(credential)
                if len(selected)==count:
                    return selected
    except (OSError, UnicodeError):
        raise BootstrapError('Cannot read the selected UTF-8 mass session file.') from None
    raise BootstrapError(f'Mass file has only {len(selected)} unique cookies; requested {count}.')


@dataclass(repr=False)
class Session:
    index: int
    process: object = field(repr=False)
    outbound: object = field(default_factory=lambda: queue.Queue(maxsize=64), repr=False)
    deferred: object = field(default_factory=deque, repr=False)
    state: str = 'starting'
    user_id: int | None = None
    username: str | None = None
    result: dict | None = None
    reader: object = field(default=None, repr=False)
    writer: object = field(default=None, repr=False)
    hop_request_id: int = 0
    server_id: str | None = None
    scans_completed: int = 0
    scanned_request_id: int = 0

    def summary(self):
        return {'account': self.index, 'user_id': self.user_id, 'username': self.username,
                'state': self.state, 'exit_code': self.process.poll(), 'result': self.result,
                'server_id': self.server_id, 'scans_completed': self.scans_completed}


class MassRunner:
    def __init__(self, credentials, *, place_id=None, vip_link=None, attempts=3, duration=None, emit=print,
                 process_factory=None, emit_batch=None, brainrot=False, only_best=False,
                 mm2=False, mm2_dry_run=False):
        if only_best and (not brainrot or vip_link is not None):
            raise ValueError('Only-best hopping requires --brainrot and public servers.')
        if vip_link is not None:
            parse_vip_link(vip_link)
            if place_id is not None:
                raise ValueError('Select either Place ID or VIP link.')
        elif type(place_id) is not int or not 0 < place_id < 2**63:
            raise ValueError('Invalid Place ID.')
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError('Invalid Place ID or attempts.')
        if duration is not None and (not math.isfinite(duration) or not 1 <= duration <= 300):
            raise ValueError('Duration must be finite and in 1..300 seconds.')
        self.credentials = credentials
        self.place_id, self.attempts, self.duration = place_id, attempts, duration
        self._vip_link = vip_link
        self.emit, self.process_factory = emit, process_factory or subprocess.Popen
        self.emit_batch = emit_batch
        self._output_batch = None
        self.sessions, self.user_ids = {}, set()
        self.events = queue.Queue(maxsize=4096)
        self._next_launch = 0
        self._closing = False
        self._broadcast_loop = None
        self._startup_chats = []
        from .brainrot import Output
        self.brainrot_output = Output(only_best=only_best) if brainrot else None
        self.only_best = only_best
        self.mm2 = mm2
        self.mm2_dry_run = mm2_dry_run
        self.coordinator = None

    def _show(self, index, event):
        messages = (self.brainrot_output.event(index, event) if self.brainrot_output is not None else
                    [f'account[{index}]: ' + json.dumps(event, ensure_ascii=False)])
        if self._output_batch is not None:
            self._output_batch.extend(messages)
        else:
            for message in messages:
                self.emit(message)

    def _writer(self, session):
        try:
            while True:
                line = session.outbound.get()
                if line is None:
                    return
                session.process.stdin.write(line + '\n')
                session.process.stdin.flush()
        except (OSError, ValueError):
            return

    def _reader(self, session):
        try:
            while True:
                line = session.process.stdout.readline(1024 * 1024 + 1)
                if not line:
                    break
                if len(line) > 1024 * 1024:
                    self.events.put((session.index, {'event': 'error', 'message': 'Worker event exceeds limit.'}))
                    break
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError
                except ValueError:
                    event = {'event': 'error', 'message': 'Invalid worker event.'}
                self.events.put((session.index, event))
        except (OSError, ValueError):
            pass
        self.events.put((session.index, {'event': 'worker_eof'}))

    def launch(self, credential):
        index = len(self.sessions) + 1
        argv = [sys.executable, '-u', '-m', 'rakbot.mass_worker', '--attempts', str(self.attempts)]
        if self.place_id is not None:
            argv += ['--place-id', str(self.place_id)]
        if self.duration is not None:
            argv += ['--duration', str(self.duration)]
        if self.brainrot_output is not None:
            argv += ['--brainrot']
        if self.only_best:
            argv += ['--only-best']
        if getattr(self, 'mm2', False):
            argv += ['--mm2']
        if getattr(self, 'mm2_dry_run', False):
            argv += ['--mm2-dry-run']
        process = self.process_factory(argv, cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        session = self.sessions[index] = Session(index, process)
        if self._broadcast_loop:
            session.deferred.append(self._broadcast_loop)
        session.deferred.extend(self._startup_chats)
        if len(self.sessions) == len(self.credentials):
            self._startup_chats.clear()
        initial = {'cookie': credential.value}
        if self._vip_link is not None:
            initial['vip_link'] = self._vip_link
        session.outbound.put_nowait(json.dumps(initial))
        session.writer = threading.Thread(target=self._writer, args=(session,), daemon=True)
        session.writer.start()
        session.reader = threading.Thread(target=self._reader, args=(session,), daemon=True)
        session.reader.start()
        self._show(index, {'event': 'starting'})

    def _enqueue(self, session, line):
        try:
            session.outbound.put_nowait(line)
            return True
        except queue.Full:
            self._show(session.index, {'event': 'error', 'message': 'Account command queue is full.'})
            return False

    def dispatch(self, line):
        text = line.strip()
        if text.casefold() in ('quit', 'exit'):
            return False
        if self.only_best:
            return True
        if text.casefold() == 'accounts':
            self.emit('accounts: ' + json.dumps([s.summary() for s in self.sessions.values()]))
            return True
        if text.casefold() == 'help':
            self.emit('mass: commands apply to all accounts; @3 command selects account 3; '
                      'accounts, looptp username, stoploop, players, status, where [username], teleport username, chat text, quit')
            return True
        targets = list(self.sessions.values())
        if not text.startswith('@'):
            parts = text.split()
            if parts and parts[0].casefold() == 'chat' and len(self.sessions) < len(self.credentials):
                from .chat import validate_text
                from .commands import CommandError
                try:
                    validate_text(text.split(None, 1)[1] if len(parts) > 1 else '')
                except CommandError as error:
                    self.emit('mass: ' + str(error))
                    return True
                if len(self._startup_chats) >= 32:
                    self.emit('mass: La cola de chat para las cuentas en arranque está llena.')
                    return True
                self._startup_chats.append(text)
            if parts and parts[0].casefold() == 'looptp' and len(parts) == 2:
                self._broadcast_loop = None if parts[1].casefold() in ('off', 'stop') else text
            elif parts and parts[0].casefold() in ('stoploop', 'stoplooptp', 'teleport', 'tp'):
                self._broadcast_loop = None
        if text.startswith('@'):
            prefix, _, text = text.partition(' ')
            try:
                targets = [self.sessions[int(prefix[1:])]]
            except (ValueError, KeyError):
                self.emit('mass: Unknown account. Use accounts.')
                return True
        if not text:
            return True
        for session in targets:
            if session.process.poll() is not None or session.state in ('failed', 'finished', 'stopping'):
                continue
            if session.state == 'starting' and text.casefold() not in ('quit', 'exit'):
                if len(session.deferred) < 64:
                    session.deferred.append(text)
                else:
                    self._show(session.index, {'event': 'error', 'message': 'Account startup queue is full.'})
            else:
                if text.casefold() in ('quit', 'exit'):
                    session.state = 'stopping'
                    session.deferred.clear()
                self._enqueue(session, text)
        return True

    def drain_events(self):
        self._output_batch = []
        try:
            self._drain_events()
            if self.brainrot_output is not None:
                self._output_batch.extend(self.brainrot_output.flush())
        finally:
            messages, self._output_batch = self._output_batch, None
            if self.emit_batch is not None:
                self.emit_batch(messages)
            else:
                for message in messages:
                    self.emit(message)

    def _drain_events(self):
        for _ in range(256):
            try:
                index, event = self.events.get_nowait()
            except queue.Empty:
                return
            session = self.sessions[index]
            kind = event.get('event')
            if kind == 'hop_request' and self.only_best:
                request_id = event.get('request_id')
                if (type(request_id) is int and request_id == session.hop_request_id + 1 and
                        session.state not in ('failed', 'finished', 'stopping', 'skipped_duplicate') and not self._closing):
                    session.hop_request_id = request_id
                    session.server_id = None
                    self.coordinator.request(index, request_id)
                continue
            if kind == 'hop_assignment' and self.only_best:
                if (event.get('request_id') == session.hop_request_id and not self._closing and
                        session.state not in ('failed', 'finished', 'stopping', 'skipped_duplicate')):
                    session.server_id = event['job_id']
                    self._enqueue(session, '__hop__ ' + json.dumps({
                        'request_id': session.hop_request_id, 'job_id': session.server_id}))
                continue
            if kind == 'brainrot_scan' and self.only_best:
                if (event.get('request_id') != session.hop_request_id or event.get('complete') is not True or
                        event.get('server_id') != session.server_id or
                        session.scanned_request_id >= session.hop_request_id):
                    continue
                session.scans_completed += 1
                session.scanned_request_id = session.hop_request_id
            if kind == 'hop_warning' and self.only_best:
                self._show(index, {'event': 'error', 'message': event.get('message')})
                continue
            if kind == 'authenticated':
                user_id = event.get('user_id')
                if type(user_id) is not int or user_id in self.user_ids or self._closing or session.state == 'stopping':
                    session.state = 'skipped_duplicate' if user_id in self.user_ids else 'stopping'
                    self._enqueue(session, 'quit')
                    self._show(index, {'event': 'duplicate_or_stopped', 'user_id': user_id})
                    continue
                self.user_ids.add(user_id)
                session.user_id, session.state = user_id, 'joining'
                self._enqueue(session, '__start__')
                while session.deferred:
                    self._enqueue(session, session.deferred.popleft())
            elif kind == 'player' and event.get('player', {}).get('is_self'):
                session.username = event['player']['username']
            elif kind == 'character' and event.get('character_spawned'):
                session.state = 'spawned'
            elif kind == 'finished':
                session.result, session.state = event.get('result'), 'finished'
                if self.coordinator is not None:
                    self.coordinator.release(index)
            elif kind == 'error':
                session.state = 'failed'
                if self.coordinator is not None:
                    self.coordinator.release(index)
            elif kind == 'worker_eof':
                if session.state not in ('failed', 'finished', 'stopping', 'skipped_duplicate'):
                    session.state = 'failed'
                    if self.coordinator is not None:
                        self.coordinator.release(index)
                    self._show(index, {'event': 'error', 'message': 'Account worker exited unexpectedly.'})
                continue
            self._show(index, event)

    def close(self):
        self._closing = True
        if self.coordinator is not None:
            self.coordinator.close()
        for session in self.sessions.values():
            if session.process.poll() is None:
                self._enqueue(session, 'quit')
        deadline = time.monotonic() + 5
        while any(s.process.poll() is None for s in self.sessions.values()) and time.monotonic() < deadline:
            self.drain_events()
            time.sleep(0.05)
        for session in self.sessions.values():
            if session.process.poll() is None:
                session.process.terminate()
        for session in self.sessions.values():
            try:
                session.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                session.process.kill()
                session.process.wait(timeout=2)
            try:
                session.outbound.put_nowait(None)
            except queue.Full:
                pass
            if session.reader is not None:
                session.reader.join(timeout=0.5)
            if session.writer is not None:
                session.writer.join(timeout=0.5)
            session.process.stdin.close()
            session.process.stdout.close()
        while not self.events.empty():
            self.drain_events()

    def run(self, commands):
        if self.only_best:
            from .server_pool import Coordinator
            self.coordinator = Coordinator(self.place_id, self.events)
            self.coordinator.start()
        try:
            while True:
                self.drain_events()
                stopping = False
                for _ in range(32):
                    try:
                        line = commands.get_nowait()
                    except queue.Empty:
                        break
                    if not self.dispatch(line):
                        stopping = True
                        break
                if stopping:
                    break
                count = len(self.sessions)
                if count < len(self.credentials) and time.monotonic() >= self._next_launch:
                    self.launch(self.credentials[count])
                    self._next_launch = time.monotonic() + 0.5
                if count == len(self.credentials) and all(s.process.poll() is not None for s in self.sessions.values()):
                    break
                time.sleep(0.02)
        finally:
            self.close()
        return self.summary()

    def summary(self):
        return {'state': 'mass_finished', 'requested_accounts': len(self.credentials),
                'started_workers': len(self.sessions), 'unique_user_ids': len(self.user_ids),
                'skipped_duplicates': sum(s.state == 'skipped_duplicate' for s in self.sessions.values()),
                'accounts': [s.summary() for s in self.sessions.values()]}


def run_mass(args):
    from .config import load_config
    config = load_config(getattr(args, 'config', None)) if getattr(args, 'only_best', False) else {}
    credentials = read_mass_credentials(args.mass_cookies_path, args.mass_cookie_file)
    brainrot = getattr(args, 'brainrot', False)
    with Console(sys.stdin, prompt='' if brainrot else 'rakbot> ') as console:
        if getattr(args, 'only_best', False):
            from .scan_pool import ScanPool
            from .scan_processes import MultiProcessScanPool, process_count
            settings = config['scanner']
            def setting(argument, key, default=None):
                value = getattr(args, argument, None)
                return settings.get(key, default) if value is None else value
            workers = setting('scan_workers', 'workers')
            timeout = setting('scan_timeout', 'timeout')
            hop_timeout = setting('scan_hop_timeout', 'hop_timeout')
            processes = setting('scan_processes', 'processes')
            inflight = setting('scan_inflight', 'inflight')
            active = min(len(credentials), 4 if workers is None else workers)
            parallel = active > 2 or process_count(active, processes) > 1 or inflight is not None
            factory = MultiProcessScanPool if parallel else ScanPool
            process_options = {'processes': processes, 'inflight': inflight} if parallel else {}
            runner = factory(credentials, place_id=args.place_id, attempts=args.attempts,
                              duration=args.duration, workers=4 if workers is None else workers,
                              emit=console.emit, emit_batch=console.emit_many,
                              scan_timeout=4 if timeout is None else timeout,
                              hop_timeout=3 if hop_timeout is None else hop_timeout,
                              scan_status=setting('scan_status', 'status', False),
                              adaptive_timeouts=not setting('scan_strict_timeouts', 'strict_timeouts', False),
                              featured_pets=config['featured_pets'], set_title=console.set_title, **process_options)
        else:
            runner = MassRunner(credentials, place_id=args.place_id, attempts=args.attempts,
                            vip_link=args.vip_link, duration=args.duration, emit=console.emit,
                            emit_batch=console.emit_many, brainrot=brainrot, only_best=getattr(args, 'only_best', False))
        if not brainrot:
            console.emit(f'mass: selected {len(credentials)} accounts; help, accounts; @3 command; quit stops all')
        runner.run(console.commands)
        result = runner.summary()
    failed = any(a['state'] == 'failed' or a['exit_code'] not in (0, None) for a in result['accounts'])
    return result, 2 if failed else 0
