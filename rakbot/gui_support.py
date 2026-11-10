"""Small GUI data layer; full Featured history lives on disk, not in widgets."""
import json
from pathlib import Path
import sqlite3

from .brainrot import text, income
from .scan_title import normalized_name
from .mass import MAX_ACCOUNTS

SORT_OPTIONS = {
    'Recently added': 'recent',
    'Oldest first': 'oldest',
    'Lowest to highest': 'income_asc',
    'Highest to lowest': 'income_desc',
    'Name A–Z': 'name_asc',
    'Name Z–A': 'name_desc',
}


def history_order(sort, *, name='pet', earnings='income_sort'):
    # Only fixed SQL fragments, never interpolate the menu label into SQL.
    orders = {'recent': 'detected_at DESC,id DESC', 'oldest': 'detected_at ASC,id ASC',
        'income_asc': f'{earnings} ASC,detected_at DESC,id DESC',
        'income_desc': f'{earnings} DESC,detected_at DESC,id DESC',
        'name_asc': f'{name} COLLATE NOCASE ASC,detected_at DESC,id DESC',
        'name_desc': f'{name} COLLATE NOCASE DESC,detected_at DESC,id DESC'}
    if sort not in orders:
        raise ValueError('Unknown history sort order.')
    return orders[sort]


def featured_rows(rows, names, *, server, account, detected_at):
    seen = set()
    # Reports are income-sorted; equal discovery times use identity, not income.
    for index, row in enumerate(sorted(rows, key=lambda r: (str(r.get('id', '')), text(r.get('DisplayName'))))):
        identity = str(row.get('id', index))
        if identity in seen:
            continue
        seen.add(identity)
        if normalized_name(row.get('DisplayName')) not in names:
            continue
        yield dict(pet_id=identity, detected_at=detected_at, account=account,
            pet=text(row.get('DisplayName')), mutation=text(row.get('Mutation')),
            generation=text(row.get('Generation')), job_id=text(server))


class FeaturedHistory:
    page_size = 100

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS featured (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, detected_at TEXT NOT NULL,
            account INTEGER NOT NULL, pet_id TEXT NOT NULL, pet TEXT NOT NULL,
            mutation TEXT NOT NULL, generation TEXT NOT NULL, job_id TEXT NOT NULL,
            UNIQUE(run_id, job_id, pet_id))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS featured_time ON featured(detected_at DESC, id DESC)')
        if 'income_sort' not in {r[1] for r in self.db.execute('PRAGMA table_info(featured)')}:
            self.db.execute('ALTER TABLE featured ADD COLUMN income_sort REAL NOT NULL DEFAULT 0')
            self.db.create_function('parse_income', 1, lambda value: float(income({'Generation': value}) or 0))
            self.db.execute('UPDATE featured SET income_sort=parse_income(generation)')
        self.db.execute('CREATE INDEX IF NOT EXISTS featured_income ON featured(income_sort,detected_at DESC,id DESC)')
        self.db.execute('CREATE INDEX IF NOT EXISTS featured_name ON featured(pet COLLATE NOCASE,detected_at DESC,id DESC)')
        self.db.commit()

    def add(self, run_id, rows):
        before = self.db.total_changes
        self.db.executemany('''INSERT INTO featured
            (run_id,detected_at,account,pet_id,pet,mutation,generation,job_id,income_sort) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id,job_id,pet_id) DO UPDATE SET pet=excluded.pet,mutation=excluded.mutation,
            generation=excluded.generation,account=excluded.account,income_sort=excluded.income_sort
            WHERE featured.pet<>excluded.pet OR featured.mutation<>excluded.mutation OR
            featured.generation<>excluded.generation OR featured.account<>excluded.account''',
            ((run_id, r['detected_at'], r['account'], r['pet_id'], r['pet'],
              r['mutation'], r['generation'], r['job_id'], float(income({'Generation':r['generation']}) or 0)) for r in rows))
        self.db.commit()
        return self.db.total_changes - before

    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM featured').fetchone()[0]

    def page(self, number=0, sort='recent'):
        return self.db.execute('''SELECT detected_at,pet,mutation,generation,job_id,account
            FROM featured ORDER BY '''+history_order(sort)+' LIMIT ? OFFSET ?',
            (self.page_size, max(0, number) * self.page_size)).fetchall()

    def clear(self):
        with self.db:
            self.db.execute('DELETE FROM featured')

    def close(self):
        self.db.close()


def scanner_request(*, config_path, cookies_path, accounts, workers, processes, inflight):
    config_path, cookies_path = Path(config_path).resolve(), Path(cookies_path).resolve()
    if not config_path.is_file():
        raise ValueError('Выбери существующий config.txt.')
    if not cookies_path.is_file():
        raise ValueError('Выбери существующий cookies.txt.')
    def integer(value, label, *, automatic=False, maximum=None):
        if automatic and (value is None or str(value).strip().casefold() in ('', 'auto', 'авто')):
            return None
        try:
            result = int(str(value).strip())
        except ValueError:
            raise ValueError(f'{label}: укажи целое положительное число.') from None
        if result < 1 or maximum is not None and result > maximum:
            raise ValueError(f'{label}: недопустимое количество.')
        return result
    return dict(config_path=str(config_path), cookies_path=str(cookies_path),
        accounts=integer(accounts, 'Аккаунты', maximum=MAX_ACCOUNTS),
        workers=integer(workers, 'Workers'), processes=integer(processes, 'Группы', automatic=True),
        inflight=integer(inflight, 'Загрузки', automatic=True))


def save_json(path, value):
    """Atomic settings write, without truncating an existing config on failure."""
    import os
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix='.rakbot-settings-', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
