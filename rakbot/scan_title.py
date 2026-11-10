"""Constant-memory run statistics, based on every row of accepted full scans."""
import unicodedata

from .brainrot import text, income, format_row


def normalized_name(name):
    return unicodedata.normalize('NFKC', text(name)).casefold()


class ScanTitle:
    def __init__(self, featured_pets=()):
        self.names = {}
        for name in featured_pets:
            self.names.setdefault(normalized_name(name), text(name))
        self.started = None
        self.servers = self.featured_count = 0
        self.best = self.featured_best = None
        self.best_income = self.featured_income = None

    def observe(self, rows):
        self.servers += 1
        seen = set()
        for index, row in enumerate(rows):
            identity = row.get('id', index)
            if identity in seen:
                continue
            seen.add(identity)
            value = income(row)
            if value is not None and (self.best_income is None or value > self.best_income):
                self.best, self.best_income = dict(row), value
            name = self.names.get(normalized_name(row.get('DisplayName')))
            if name is None:
                continue
            self.featured_count += 1
            if value is not None and (self.featured_income is None or value > self.featured_income):
                self.featured_income = value
                self.featured_best = {'DisplayName': name, 'Generation': row.get('Generation')}

    def render(self, now):
        elapsed = max(0, int(now - self.started)) if self.started is not None else 0
        minutes, seconds = divmod(elapsed, 60)
        best = format_row(self.best) if self.best is not None else '—'
        featured = format_row(self.featured_best) if self.featured_best is not None else '—'
        return (f'Scanned {self.servers} servers. Working for {minutes} minutes {seconds} secounds. '
                f'Best by earnings - {best}. FEATURED : {self.featured_count}, {featured}')
