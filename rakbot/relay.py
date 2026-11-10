"""WebSocket relay: Featured finds go out to Roblox clients (LEET NOTIFIER menu).

The scanner GUI owns one Relay. Clients connect to ws://host:port/ and send
{"type":"auth","key":"<key>"} first (or put ?key=<key> in the URL);
every find is broadcast to every authorised client, and each client filters by its
own Targets list. Clients never send commands, so the relay cannot be used to drive
the scanner or read anything but finds.
"""
import asyncio
import hmac
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import broadcast, serve
from websockets.exceptions import ConnectionClosed

from .brainrot import PLACE_ID, income

DEFAULTS = {'enabled': True, 'host': '0.0.0.0', 'port': 8765, 'key': ''}
DEDUP_SECONDS = 120  # the same pet on the same server is reported again on every rescan
CLOSE_BAD_KEY = 4401
AUTH_TIMEOUT = 10  # seconds to send {"type":"auth"} when the key is not in the URL


def load_settings(path):
    """relay.json next to config.txt; a random key is generated and saved on first run."""
    path = Path(path)
    try:
        data = json.loads(path.read_text('utf-8-sig'))
    except FileNotFoundError:
        data = {}
    except (OSError, UnicodeError, ValueError):
        raise ValueError('relay.json: ожидается UTF-8 JSON с enabled, host, port, key.') from None
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('relay.json: допустимы только поля enabled, host, port, key.')

    settings = {**DEFAULTS, **data}
    if (type(settings['enabled']) is not bool or not isinstance(settings['host'], str)
            or type(settings['port']) is not int or not 1 <= settings['port'] <= 65535
            or not isinstance(settings['key'], str)):
        raise ValueError('relay.json: неверный тип enabled/host/port/key.')
    if len(settings['key']) < 16:
        settings['key'] = secrets.token_urlsafe(24)
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n', 'utf-8')
    return settings


def find_message(row):
    generation = row.get('generation', '')
    return {
        'type': 'find',
        'name': row.get('pet', ''),
        'mutation': row.get('mutation') or None,
        'generation': generation,
        'income': float(income({'Generation': generation}) or 0),
        'jobId': row.get('job_id', ''),
        'placeId': PLACE_ID,
        'detectedAt': row.get('detected_at', ''),
    }


class Relay:
    def __init__(self, host, port, key, *, emit=print):
        self.host, self.port, self.key = host, port, key
        self.emit = emit
        self.loop = None
        self.clients = set()  # touched only on the relay thread
        self.recent = {}  # touched only on the caller's (Tk) thread
        self.ready = threading.Event()
        self.error = None
        self._stop = None
        self._thread = None

    def start(self, timeout=5):
        self._thread = threading.Thread(target=self._run, name='relay', daemon=True)
        self._thread.start()
        self.ready.wait(timeout)
        if self.error:
            raise OSError(self.error)

    def _run(self):
        try:
            asyncio.run(self._main())
        except OSError as error:  # port busy, bad host
            self.error = f'Relay не запустился на {self.host}:{self.port}: {error}'
            self.ready.set()

    async def _main(self):
        self.loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with serve(self._handler, self.host, self.port, ping_interval=20, max_size=4096):
            self.emit(f'Relay слушает ws://{self.host}:{self.port}')
            self.ready.set()
            await self._stop.wait()

    async def _handler(self, connection):
        query = parse_qs(urlsplit(connection.request.path).query)
        key = query.get('key', [''])[0]
        if not key:
            key = await self._auth_message(connection)
        if not hmac.compare_digest(key.encode(), self.key.encode()):
            await connection.close(CLOSE_BAD_KEY, 'bad key')
            return
        address = connection.remote_address[0] if connection.remote_address else '?'
        self.clients.add(connection)
        self.emit(f'Relay: клиент подключён ({address}), всего {len(self.clients)}')
        try:
            await connection.send(json.dumps({'type': 'hello', 'placeId': PLACE_ID}))
            async for _ in connection:
                pass  # clients only listen; anything they send is ignored
        finally:
            self.clients.discard(connection)
            self.emit(f'Relay: клиент отключён ({address}), всего {len(self.clients)}')

    @staticmethod
    async def _auth_message(connection):
        """Key as the first message {"type":"auth","key":...}: some executors mangle URLs with a query."""
        try:
            data = json.loads(await asyncio.wait_for(connection.recv(), AUTH_TIMEOUT))
        except (asyncio.TimeoutError, ValueError, TypeError, ConnectionClosed):
            return ''
        if isinstance(data, dict) and data.get('type') == 'auth' and isinstance(data.get('key'), str):
            return data['key']
        return ''

    def publish(self, rows):
        """Called from the GUI thread with rows from a 'featured' event."""
        if self.loop is None:
            return
        now = time.monotonic()
        messages = []
        for row in rows:
            identity = (row.get('job_id'), row.get('pet_id'))
            if now - self.recent.get(identity, -DEDUP_SECONDS) < DEDUP_SECONDS:
                continue
            self.recent[identity] = now
            messages.append(json.dumps(find_message(row), ensure_ascii=False))
        if len(self.recent) > 20000:
            self.recent = {k: t for k, t in self.recent.items() if now - t < DEDUP_SECONDS}
        if messages:
            self.loop.call_soon_threadsafe(self._broadcast, messages)

    def _broadcast(self, messages):
        for message in messages:
            broadcast(self.clients, message)

    def stop(self):
        if self.loop is not None and self._stop is not None:
            self.loop.call_soon_threadsafe(self._stop.set)
