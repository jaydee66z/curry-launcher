"""Separate chronological Egg history, persisted locally with no coordinator."""
import json
from pathlib import Path
import sqlite3
from .gui_support import history_order


class EggHistory:
    page_size=100

    def __init__(self,path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.current_run=None
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS eggs (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL,
            egg_id TEXT NOT NULL, detected_at TEXT NOT NULL, account INTEGER NOT NULL,
            name TEXT NOT NULL, income TEXT NOT NULL, generation TEXT NOT NULL,
            weight REAL NOT NULL, mutation TEXT NOT NULL, mutations TEXT NOT NULL,
            rarity TEXT NOT NULL, area TEXT NOT NULL, category TEXT NOT NULL,
            source TEXT NOT NULL, scale REAL NOT NULL,
            UNIQUE(run_id,job_id,egg_id))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS egg_time ON eggs(detected_at DESC,id DESC)')
        self.db.commit()

    def add(self,run_id,*,rows,job_id,account,detected_at):
        before=self.db.total_changes
        self._insert(run_id,rows=rows,job_id=job_id,account=account,detected_at=detected_at)
        self.db.commit()
        return self.db.total_changes-before

    def replace_snapshot(self,run_id,*,rows,job_id,account,detected_at):
        # Commit the entire sample at once, including an empty conveyor.
        with self.db:
            self.db.execute('DELETE FROM eggs WHERE run_id=? AND job_id=?',(run_id,job_id))
            self._insert(run_id,rows=rows,job_id=job_id,account=account,detected_at=detected_at)

    def remove_server(self,run_id,job_id):
        with self.db:
            self.db.execute('DELETE FROM eggs WHERE run_id=? AND job_id=?',(run_id,job_id))

    def _insert(self,run_id,*,rows,job_id,account,detected_at):
        self.db.executemany('''INSERT OR IGNORE INTO eggs
            (run_id,job_id,egg_id,detected_at,account,name,income,generation,weight,mutation,
             mutations,rarity,area,category,source,scale) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ((run_id,job_id,r['id'],detected_at,account,r['DisplayName'],str(r['income']),r['Generation'],
              r['weight'],r['Mutation'],json.dumps(r['mutations'],ensure_ascii=False),r['rarity'],
              r['area'],r['category'],r['source'],r['scale']) for r in sorted(rows,key=lambda r:r['id'])))

    def count(self):
        return self.db.execute('SELECT COUNT(*) FROM eggs'+(' WHERE run_id=?' if self.current_run else ''),
            (self.current_run,) if self.current_run else ()).fetchone()[0]

    def page(self,number=0,sort='recent'):
        return self.db.execute('''SELECT detected_at,name,generation,weight,mutation,rarity,area,job_id
            FROM eggs'''+(' WHERE run_id=?' if self.current_run else '')+
            ' ORDER BY '+history_order(sort,name='name',earnings='CAST(income AS REAL)')+' LIMIT ? OFFSET ?',
            ((self.current_run,) if self.current_run else ())+(self.page_size,max(0,number)*self.page_size)).fetchall()

    def clear(self):
        with self.db:
            self.db.execute('DELETE FROM eggs'+(' WHERE run_id=?' if self.current_run else ''),
                (self.current_run,) if self.current_run else ())

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db=None
