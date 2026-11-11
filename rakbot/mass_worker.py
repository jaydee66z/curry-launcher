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


def run_mm2_farm(args, bootstrap, account):
    """MM2 pure-Python farm: join MM2, run mm2_client.Session loop.

    - ``--mm2-dry-run`` logs payloads without sending (zero AC risk).
    - Default duration = 3600s per round of bootstrap.prepare() to reduce
      join frequency.
    """
    from .mm2_client import Session
    from .mm2_inventory import EmbersickleWatcher
    place_id = args.place_id or 142823291  # MM2
    info = bootstrap.prepare(place_id, attempts=args.attempts)
    if info.account.user_id != account.user_id:
        raise ValueError('Account identity changed during startup.')
    emit('connection_info_ready', user_id=account.user_id, place_id=info.place_id,
         server_kind='public', farm_mode='mm2')
    with Console(sys.stdin) as console:
        client = GameClient(info, commands=console.commands,
            on_player=lambda player: emit('player', player=player),
            on_character=lambda character: emit('character', **character))
        # Give the client time to join + replicate enough world to pick
        # out Coin_Server nodes and ProfileData. The farm loop only
        # begins after inspector.own is set.
        inspector = getattr(client, 'inspector', None)
        if inspector is None:
            emit('error', message='GameClient has no inspector (schema missing).')
            return 1
        transport = getattr(client, 'transport', None)
        if transport is None:
            emit('error', message='GameClient has no transport.')
            return 1
        session = Session(inspector=inspector, transport=transport,
                          emit=lambda e: emit('mm2', **e))
        # Hook CoinCollected via inspector's event sink. inspector.event_value
        # is called for every RemoteEvent OnClientEvent; we filter inside.
        _orig_ev = inspector.event_value
        def _wrapped_event(name, key, arguments):
            try:
                if name == 'RemoteEvent.OnClientEvent':
                    # CoinCollected arg[0] = coin type bytes
                    if arguments and isinstance(arguments[0], (bytes, str)):
                        kind = arguments[0] if isinstance(arguments[0], bytes) else arguments[0].encode('utf-8', 'ignore')
                        if kind in (b'Candy', b'Coin', b'Candy2026'):
                            session.on_coin_collected(kind)
                    elif not arguments:
                        # Maybe CoinsStarted
                        session.on_coins_started()
            finally:
                _orig_ev(name, key, arguments)
        inspector.event_value = _wrapped_event
        # Fire up the Embersickle watcher (daemon thread)
        watcher = EmbersickleWatcher(inspector, username=account.username or '',
                                     user_id=account.user_id,
                                     emit=lambda e: emit('mm2_inv', **e))
        watcher.start()
        try:
            # Run GameClient in a background thread so Session.run can also tick
            import threading
            def _client_runner():
                try:
                    client.run(duration=args.duration)
                except Exception as e:
                    emit('client_err', msg=repr(e)[:160])
            t = threading.Thread(target=_client_runner, daemon=True)
            t.start()
            # Wait for inspector.own to be populated (character joined)
            for _ in range(600):  # up to 60s
                if inspector.own is not None:
                    break
                time.sleep(0.1)
            if inspector.own is None:
                emit('error', message='Timed out waiting for inspector.own (join failed).')
                return 1
            session.run(duration=args.duration, dry_run=bool(getattr(args, 'mm2_dry_run', False)))
        finally:
            watcher.stop()
    emit('finished', result={'state': 'mm2_stopped',
                             'lifetime_candies': session.lifetime_candies,
                             'boxes_opened': session.boxes_opened})
    return 0


def run(args):
    initial = sys.stdin.readline(24000)
    if len(initial) >= 24000 or not initial.endswith('\n'):
        raise ValueError('Invalid worker initialization.')
    payload = json.loads(initial)
    credential = Credential(payload['cookie'])
    vip_link = payload.get('vip_link')
    del payload, initial
    # v0.45: optional per-account proxy from rakbot.proxy_pool.
    # ProxyPool.enabled() returns False silently if no proxies.txt.
    proxy_pool = None
    try:
        from .proxy_pool import ProxyPool
        pp = ProxyPool()
        if pp.enabled():
            proxy_pool = pp
    except Exception:
        proxy_pool = None  # non-fatal; direct connection still works
    bootstrap = RobloxBootstrap(credential, proxy_pool=proxy_pool)
    account = bootstrap.authenticate()
    emit('authenticated', user_id=account.user_id,
         proxy_pool=bool(proxy_pool))
    # Parent checks duplicate account IDs before allowing GameJoin.
    if sys.stdin.readline(128).strip() != '__start__':
        return 0
    if getattr(args, 'only_best', False):
        return scan_servers(args, bootstrap, account)
    if getattr(args, 'mm2', False):
        return run_mm2_farm(args, bootstrap, account)
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
    parser.add_argument('--mm2', action='store_true',
                        help='Run the MM2 Python farm (GetCoin + box opener).')
    parser.add_argument('--mm2-dry-run', action='store_true',
                        help='Log payloads instead of sending (zero AC risk).')
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
