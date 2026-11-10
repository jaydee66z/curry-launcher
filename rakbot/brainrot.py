"""Read replicated overhead labels; never execute scripts or infer missing text."""
from decimal import Decimal, InvalidOperation
from datetime import datetime
import html
import re
import unicodedata
from collections import OrderedDict


PLACE_ID = 109983668079237
FIELDS = ('DisplayName', 'Generation', 'Mutation', 'Price', 'Rarity', 'Stolen')
_SUFFIXES = {name.casefold(): Decimal(1000) ** i for i, name in enumerate(
    ('', 'K', 'M', 'B', 'T', 'Qa', 'Qi', 'Sx', 'Sp', 'Oc', 'No', 'Dc'))}


def text(value):
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    if not isinstance(value, str):
        return ''
    value = html.unescape(re.sub(r'<[^>]*>', '', value[:4096]))
    return ' '.join(''.join(c for c in value if not unicodedata.category(c).startswith('C')).split())


def generation(value):
    """Numeric income, including $1,200/s, $1.5M/s and decimal-comma values."""
    value = text(value).replace('\u00a0', '').replace(' ', '')
    match = re.fullmatch(r'\$?([0-9][0-9.,]*)([A-Za-z]*)(?:/(?:s|sec))?', value, re.I)
    if not match or match[2].casefold() not in _SUFFIXES:
        return None
    number = match[1]
    if ',' in number and '.' in number:
        number = number.replace(',', '')
    elif ',' in number:
        number = number.replace(',', '') if re.fullmatch(r'\d{1,3}(?:,\d{3})+', number) else number.replace(',', '.')
    try:
        result = Decimal(number) * _SUFFIXES[match[2].casefold()]
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def ordered(rows):
    return sorted(rows, key=lambda row: (
        income(row) is None,
        -(income(row) or Decimal(0)),
        text(row.get('DisplayName')).casefold(), str(row.get('id', ''))))


def income(row):
    exact = row.get('generation_value')
    if isinstance(exact, str) and re.fullmatch(r'[0-9]{1,40}(?:\.[0-9]{1,20})?', exact):
        return Decimal(exact)
    return generation(row.get('Generation'))


def format_row(row):
    name = ' '.join(filter(None, (text(row.get('Mutation')), text(row.get('DisplayName')))))
    return f'{name} ({text(row.get("Generation"))})'


def best_time():
    return datetime.now().strftime('%H:%M:%S')


class Scanner:
    def __init__(self, world):
        self.world = world
        self.templates = set()
        self.dirty = True

    def observe(self, key, node=None):
        if node and node['props'].get('Name') in (b'FastOverheadTemplate', 'FastOverheadTemplate'):
            self.templates.add(key)
        else:
            self.templates.discard(key)
        self.dirty = True

    def changed(self, key, name):
        if name == 'Name':
            self.observe(key, self.world.nodes.get(key))
        elif name in ('Parent', 'Text', 'Visible', 'Enabled'):
            self.dirty = True

    def _inside_debris(self, key):
        seen, debris = set(), False
        while key in self.world.nodes and len(seen) < 128 and key not in seen:
            seen.add(key)
            node = self.world.nodes[key]
            if node['props'].get('Visible', True) is not True or node['props'].get('Enabled', True) is not True:
                return False
            if node['class'] == 'Workspace':
                return debris
            if node['class'] == 'Folder' and text(node['props'].get('Name')) == 'Debris':
                debris = True
            key = node['parent']
        return False

    def rows(self):
        nodes, result = self.world.nodes, []
        for key in sorted(self.templates):
            if key not in nodes or not self._inside_debris(key):
                continue
            frames = [(ref, node) for ref, node in nodes.children(key)
                      if text(node['props'].get('Name')) == 'AnimalOverhead']
            if len(frames) != 1:
                continue
            frame_key, frame = frames[0]
            if (frame['props'].get('Visible', True) is not True or
                    frame['props'].get('Enabled', True) is not True):
                continue
            fields = {name: None for name in FIELDS}
            for _, label in nodes.children(frame_key):
                name = text(label['props'].get('Name'))
                if (name in fields and label['class'] in ('TextLabel', 'TextButton', 'TextBox')
                        and label['props'].get('Visible', True) is True):
                    fields[name] = text(label['props'].get('Text')) or None
            # Hidden/unknown names or income cannot produce an advertised row.
            if fields['DisplayName'] and fields['Generation']:
                result.append({'id': ':'.join(map(str, key)), **fields})
        self.dirty = False
        return ordered(result)


class Output:
    """One compact view across workers; the same server/instance is shown once."""
    def __init__(self, *, only_best=False):
        self.players = {}
        self.snapshots = {}
        self._last_rows = []
        self._dirty = False
        self._joined_header = False
        self.only_best = only_best
        self.reported = OrderedDict()

    def event(self, index, event):
        kind = event.get('event')
        if self.only_best and kind in ('player', 'brainrots'):
            return []
        if self.only_best and kind == 'brainrot_scan':
            server = event.get('server_id')
            if event.get('complete') is not True or not server or server in self.reported:
                return []
            self.reported[server] = None
            while len(self.reported) > 10000:
                self.reported.popitem(last=False)
            rows = ordered(event.get('rows', []))
            best = next((row for row in rows if income(row) is not None), None)
            return [f'[{best_time()}] BEST : ' + (format_row(best) if best else '—') + ' | JobID: ' + text(server)]
        if kind == 'player':
            player = event['player']
            identity = player.get('user_id')
            name = (text(player.get('username')), text(player.get('display_name')))
            if not name[0] or self.players.get(identity) == name:
                return []
            self.players[identity] = name
            lines = [] if self._joined_header else ['Joined :']
            self._joined_header = True
            return [*lines, f'{name[0]} ({name[1] or name[0]})']
        if kind == 'brainrots':
            self.snapshots.pop(index, None)
            self.snapshots[index] = (event.get('server_id') or index, event['rows'])
            self._dirty = True
        if kind in ('finished', 'error', 'worker_eof') and index in self.snapshots:
            del self.snapshots[index]
            self._dirty = True
        if kind == 'error':
            return [f'error: account[{index}]: {text(event.get("message"))}']
        return []

    def flush(self):
        if self.only_best:
            return []
        if not self._dirty:
            return []
        self._dirty = False
        unique = {}
        for server, rows in self.snapshots.values():
            for row in rows:
                unique[(server, row['id'])] = row
        rows = ordered(unique.values())
        if rows == self._last_rows:
            return []
        self._last_rows = rows
        lines = [format_row(row) for row in rows]
        best = next((row for row in rows if income(row) is not None), None)
        return [*lines, f'[{best_time()}] BEST : ' + (format_row(best) if best else '—')]
