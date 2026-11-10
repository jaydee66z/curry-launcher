"""One game session per subprocess; credentials arrive only over stdin."""
import argparse
import json
import sys
import queue
import time

from .bootstrap import Credential, RobloxBootstrap, JoinRefused, InstanceMismatch, job_id
from .console import Console
from .game_client import GameClient
from .native_crypto import CryptoError


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}, ensure_ascii=True), flush=True)


def wait_assignment(console, request_id, deadline):
    while deadline is None or time.monotonic() < deadline:
        try:
            line = console.commands.get(timeout=0.2)
        except queue.Empty:
            continue
        if line.casefold() in ('quit', 'exit'):
            return None
        if line.startswith('__hop__ '):
            try:
                message = json.loads(line[8:])
                if type(message.get('request_id')) is int and message['request_id'] == request_id:
                    return job_id(message.get('job_id'))
            except (ValueError, AttributeError, TypeError):
                continue
    return None


def wait_retry(console, deadline):
    until = time.monotonic() + 2
    if deadline is not None:
        until = min(until, deadline)
    while time.monotonic() < until:
        try:
            if console.commands.get(timeout=0.2).casefold() in ('quit', 'exit'):
                return False
        except queue.Empty:
            pass
    return deadline is None or time.monotonic() < deadline


def scan_servers(args, bootstrap, account):
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    request_id, completed = 0, 0
    with Console(sys.stdin) as console:
        while deadline is None or time.monotonic() < deadline:
            request_id += 1
            emit('hop_request', request_id=request_id)
            server = wait_assignment(console, request_id, deadline)
            if server is None:
                break
            try:
                info = bootstrap.prepare_instance(args.place_id, server, attempts=args.attempts)
            except InstanceMismatch:
                emit('hop_skipped', request_id=request_id, reason='unexpected_server')
                continue
            except JoinRefused as error:
                if error.status not in (5, 6, 10):
                    raise
                emit('hop_skipped', request_id=request_id, reason='server_unavailable')
                continue
            if info.account.user_id != account.user_id:
                raise ValueError('Account identity changed during startup.')
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining < 1:
                break
            snapshot = {}
            def observe(value):
                snapshot.clear()
                snapshot.update(value)
            client = GameClient(info, commands=console.commands, on_brainrots=observe, scan_once=True)
            emit('server_joining', request_id=request_id, server_id=server)
            try:
                result = client.run(duration=min(75, remaining) if remaining is not None else 75)
            except (CryptoError, OSError):
                emit('hop_skipped', request_id=request_id, reason='transport_interrupted')
                if not wait_retry(console, deadline):
                    break
                continue
            if client.scan_complete and snapshot.get('complete') is True:
                completed += 1
                snapshot['server_id'] = server  # Canonical ID, already verified by GameJoin.
                emit('brainrot_scan', request_id=request_id, **snapshot)
            elif result.get('stop_reason') == 'client_quit':
                break
            else:
                emit('hop_skipped', request_id=request_id, reason='initial_scan_incomplete')
    emit('finished', result={'state': 'scanner_stopped', 'scans_completed': completed,
                             'stop_reason': 'scanner_stopped'})
    return 0


def run(args):
    initial = sys.stdin.readline(24000)
    if len(initial) >= 24000 or not initial.endswith('\n'):
        raise ValueError('Invalid worker initialization.')
    payload = json.loads(initial)
    credential = Credential(payload['cookie'])
    vip_link = payload.get('vip_link')
    del payload, initial
    bootstrap = RobloxBootstrap(credential)
    account = bootstrap.authenticate()
    emit('authenticated', user_id=account.user_id)
    # Parent checks duplicate account IDs before allowing GameJoin.
    if sys.stdin.readline(128).strip() != '__start__':
        return 0
    if getattr(args, 'only_best', False):
        return scan_servers(args, bootstrap, account)
    info = (bootstrap.prepare_vip(vip_link, attempts=args.attempts) if vip_link is not None
            else bootstrap.prepare(args.place_id, attempts=args.attempts))
    if info.account.user_id != account.user_id:
        raise ValueError('Account identity changed during startup.')
    emit('connection_info_ready', user_id=account.user_id,
         **({'place_id': info.place_id, 'server_kind': 'private', 'private_server': info.private_server}
            if vip_link is not None else {}))
    with Console(sys.stdin) as console:
        options = {}
        if getattr(args, 'brainrot', False):
            options['on_brainrots'] = lambda snapshot: emit('brainrots', **snapshot)
        client = GameClient(info, commands=console.commands,
            on_player=lambda player: emit('player', player=player),
            on_character=lambda character: emit('character', **character),
            on_command=lambda result: emit('command', result=result), **options)
        result = client.run(duration=args.duration)
    emit('finished', result={k: result[k] for k in
        ('state', 'character_spawned', 'movement_ready', 'stop_reason', 'elapsed_seconds',
         'physics_packets_sent', 'loop_teleport', 'last_teleport', 'ack_timeout',
         'character_evidence', 'replication_diagnostics', 'last_chat', 'chat_messages_sent',
         'chat_messages_confirmed', 'chat_messages_waiting', 'chat_access') if k in result})
    return 2 if result['state'].endswith('_rejected') else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--place-id', type=int)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--brainrot', action='store_true')
    parser.add_argument('--only-best', action='store_true')
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError) as error:
        # Library errors are sanitized; never echo initialization text.
        from .bootstrap import BootstrapError
        from .native_crypto import CryptoError
        message = str(error) if isinstance(error, (BootstrapError, CryptoError, OSError)) else 'Worker initialization failed.'
        emit('error', message=message)
        return 1
    except Exception:
        emit('error', message='Unexpected session worker failure.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
