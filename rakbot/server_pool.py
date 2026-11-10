"""One anonymous server browser and exclusive assignments for this mass run."""
from collections import OrderedDict, deque
import math
import queue
import threading
import time

from .bootstrap import BootstrapError, RobloxHTTP, _object, job_id, public_servers_url


class PublicServers:
    def __init__(self, place_id, *, http=None, prefer_fast=False, sort_order='Desc', min_players=0):
        public_servers_url(place_id, sort_order=sort_order)
        if type(min_players) is not int or not 0 <= min_players <= 1000:
            raise ValueError('Minimum server population must be 0..1000.')
        self.place_id = place_id
        self.http = http or RobloxHTTP()
        self.prefer_fast = prefer_fast
        self.sort_order = sort_order
        self.min_players = min_players

    def page(self, cursor=None):
        response = _object(self.http.request(public_servers_url(self.place_id, cursor, sort_order=self.sort_order)))
        rows = response.get('data')
        if not isinstance(rows, list) or len(rows) > 100:
            raise BootstrapError('Unsupported public-server list.')
        result, ranked = [], []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                server = job_id(row.get('id'))
            except BootstrapError:
                continue
            playing, maximum = row.get('playing'), row.get('maxPlayers')
            if type(playing) is int and type(maximum) is int and self.min_players <= playing < maximum <= 1000:
                result.append(server)
                ping, fps = row.get('ping'), row.get('fps')
                ping = ping if type(ping) in (int, float) and math.isfinite(ping) and 0 <= ping <= 60000 else 60000
                slow = type(fps) in (int, float) and math.isfinite(fps) and fps < 45
                ranked.append((playing == 0, slow, ping, playing / maximum, server))
        cursor = response.get('nextPageCursor')
        if cursor is not None:
            public_servers_url(self.place_id, cursor, sort_order=self.sort_order)  # Validate before storing it.
        if self.prefer_fast:
            # Keep the populated-server page; prioritize its advertised health.
            result = [item[-1] for item in sorted(ranked)]
        return result, cursor


class ServerPool:
    def __init__(self):
        self.available = deque()
        self.reserved = {}
        self.seen = OrderedDict()

    def add(self, jobs):
        known = set(self.available)
        for value in jobs:
            value = job_id(value)
            if value not in known and value not in self.seen and value not in self.reserved.values():
                self.available.append(value)
                known.add(value)

    def release(self, account):
        self.reserved.pop(account, None)

    def assign(self, account):
        if account in self.reserved:
            return self.reserved[account]
        while self.available:
            value = self.available.popleft()
            if value in self.seen or value in self.reserved.values():
                continue
            self.reserved[account] = value
            self.seen[value] = None
            while len(self.seen) > 10000:
                self.seen.popitem(last=False)
            return value
        return None


class Coordinator:
    def __init__(self, place_id, events, *, browser=None, assignment_interval=0.5, assignment_sink=None, preload=False,
                 prefetch=0):
        if not math.isfinite(assignment_interval) or assignment_interval < 0:
            raise ValueError('Assignment interval must be finite and nonnegative.')
        self.browser = browser or PublicServers(place_id)
        self.assignment_interval = assignment_interval
        self.events = events
        self.assignment_sink = assignment_sink
        self.wake = threading.Event()
        self.preload = preload
        self.prefetch = prefetch
        self._fetch_thread = None
        self._fetch_results = queue.Queue(maxsize=1)
        self.pool = ServerPool()
        self.requests = queue.Queue(maxsize=512)
        self.waiting = OrderedDict()
        self.stop = threading.Event()
        self.thread = None
        self.cursor = None
        self.next_fetch = self.next_assignment = 0
        self.failures = 0
        self._warned = False

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='rakbot-server-pool')
        self.thread.start()

    def request(self, account, request_id):
        self.requests.put_nowait(('request', account, request_id))
        self.wake.set()

    def release(self, account):
        self.requests.put_nowait(('release', account, None))
        self.wake.set()

    def _fetched(self, response, now):
        jobs, cursor, error = response
        if error is not None:
            self.failures += 1
            self.next_fetch = now + min(60, 5 * 2 ** min(self.failures, 4))
            if not self._warned and self.waiting:
                account = next(iter(self.waiting))
                self.events.put((account, {'event': 'hop_warning', 'message': str(error)}))
                self._warned = True
            return
        self.pool.add(jobs)
        exhausted = cursor is None or cursor == self.cursor
        self.cursor = None if exhausted else cursor
        self.next_fetch = now + (15 if exhausted else 1)
        self.failures, self._warned, self.preload = 0, False, False

    def _fetch(self):
        try:
            jobs, cursor = self.browser.page(self.cursor)
            response = (jobs, cursor, None)
        except BootstrapError as error:
            response = (None, None, error)
        except Exception:
            response = (None, None, BootstrapError('Public-server lookup failed.'))
        self._fetch_results.put(response)
        self.wake.set()

    def step(self, now=None):
        now = time.monotonic() if now is None else now
        for _ in range(256):
            try:
                kind, account, request_id = self.requests.get_nowait()
            except queue.Empty:
                break
            self.pool.release(account)
            if kind == 'request':
                self.waiting[account] = request_id
            else:
                self.waiting.pop(account, None)
        if self.prefetch:
            try:
                self._fetched(self._fetch_results.get_nowait(), now)
            except queue.Empty:
                pass
        if (not self.waiting and not self.preload and not self.prefetch) or self.stop.is_set():
            return
        if len(self.pool.available) <= self.prefetch and now >= self.next_fetch:
            if self.prefetch:
                if self._fetch_thread is None or not self._fetch_thread.is_alive():
                    self._fetch_thread = threading.Thread(target=self._fetch, daemon=True,
                                                          name='rakbot-server-prefetch')
                    self._fetch_thread.start()
            else:
                try:
                    jobs, cursor = self.browser.page(self.cursor)
                    self._fetched((jobs, cursor, None), now)
                except BootstrapError as error:
                    self._fetched((None, None, error), now)
        while self.waiting and now >= self.next_assignment and not self.stop.is_set():
            account = next(iter(self.waiting))
            value = self.pool.assign(account)
            if value is None:
                break
            request_id = self.waiting.pop(account)
            assignment = {'event': 'hop_assignment', 'request_id': request_id, 'job_id': value}
            if self.assignment_sink is None:
                self.events.put((account, assignment))
            else:
                self.assignment_sink(account, assignment)
            self.next_assignment = now + self.assignment_interval

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            self.step()
            self.wake.wait(0.05)

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=0.2)
