"""Lightweight Tk scanner UI; the Tk thread never joins games or reads cookies."""
from datetime import datetime
import json
import math
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import load_config
from .gui_support import FeaturedHistory, save_json, scanner_request, SORT_OPTIONS
from .egg_history import EggHistory
from .mass import MAX_ACCOUNTS
from .relay import Relay, load_settings as load_relay_settings


class App:
    def __init__(self, root, *, base_dir=None, config_path=None, cookies_path=None,
                 backend_command=None, stop_timeout=20, relay=False):
        self.root = root
        self.base = Path(base_dir or Path(__file__).resolve().parents[1]).resolve()
        self.data = self.base / '.rakbot-ui'
        self.data.mkdir(parents=True, exist_ok=True)
        self.history = FeaturedHistory(self.data / 'featured.sqlite3')
        self.egg_history = EggHistory(self.data / 'eggs.sqlite3')
        self.active_profile = 'brainrot'
        self.profile_forms = {}
        self.profile_stats = {}
        self.health = {}
        self.health_window = None
        self.health_body = None
        self.join_players=[]
        self.join_job=None
        self.join_observer=None
        self.egg_cycle_end = None
        self.egg_batches={}
        self.egg_cycle_night = 0
        self.egg_cycle_running = False
        self._cycle_second = None
        self.process = None
        self.events = queue.Queue(maxsize=512)
        self.reader_done = threading.Event()
        self.reader_done.set()
        self.relay = self._start_relay() if relay else None
        self.backend_command = backend_command
        self.stop_timeout = stop_timeout
        self.stop_at = None
        self.closing = False
        self.run_id = None
        self.log_file = None
        self.page_number = 0
        self.table_dirty = True
        self.inputs = []
        self.status = tk.StringVar(value='Detenido')
        self.accounts = tk.StringVar(value='30')
        self.workers = tk.StringVar(value='30')
        self.groups = tk.StringVar(value='Auto')
        self.inflight = tk.StringVar(value='Auto')
        self.cookies = tk.StringVar(value=str(cookies_path or self.base / 'cookies.txt'))
        self.config = tk.StringVar(value=str(config_path or self.base / 'config.txt'))
        self.servers = tk.StringVar(value='0')
        self.elapsed = tk.StringVar(value='00:00')
        self.featured = tk.StringVar(value='0')
        self.best = tk.StringVar(value='—')
        self.account_status = tk.StringVar(value='Las cuentas aún no se han iniciado')
        self.page_label = tk.StringVar()
        self.sort_choice = tk.StringVar(value='Recently added')
        self.join_place=tk.StringVar()
        self.join_server=tk.StringVar()
        self.join_vip=tk.StringVar()
        self.join_scope=tk.StringVar(value='Todas las cuentas')
        self.join_line=tk.StringVar()
        self.result_label = tk.StringVar(value='Featured')
        self.table_heading = tk.StringVar(value='Featured')
        self.table_subheading = tk.StringVar(value='Scan completo cada 30 s · base al entrar un jugador')
        self.cycle_label = tk.StringVar(value='')
        self._build()
        self.root.bind('<Destroy>',lambda event:self.egg_history.close() if event.widget==self.root else None,add='+')
        self._load_preferences(config_path, cookies_path)
        self.load_settings(quiet=True)
        self._refresh_history()
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(200, self._poll)

    def _build(self):
        from .gui_onyx import build
        build(self)

    def _load_preferences(self, config_path, cookies_path):
        try:
            raw = (self.data / 'settings.json').read_bytes()
            if len(raw) > 16384:
                return
            preferences = json.loads(raw)
            target=preferences.get('joiner_target',{})
            if isinstance(target,dict):
                for key,variable in (('place_id',self.join_place),('server_id',self.join_server),('vip_link',self.join_vip)):
                    value=target.get(key)
                    if isinstance(value,str) and len(value)<2048:
                        variable.set(value)
            if type(preferences.get('accounts')) is int and 1 <= preferences['accounts'] <= MAX_ACCOUNTS:
                self.accounts.set(str(preferences['accounts']))
            for argument, key, variable in ((config_path, 'config_path', self.config), (cookies_path, 'cookies_path', self.cookies)):
                value = preferences.get(key)
                if argument is None and isinstance(value, str) and len(value) < 4096 and Path(value).is_file():
                    variable.set(value)
        except (OSError, ValueError, AttributeError):
            pass

    def load_settings(self, quiet=False):
        try:
            config = load_config(self.config.get())
            settings = config['scanner']
            self.workers.set(str(settings.get('workers') or 4))
            self.groups.set(str(settings.get('processes') or 'Auto'))
            self.inflight.set(str(settings.get('inflight') or 'Auto'))
            self._append_log([f"Config cargado. Nombres de Featured: {len(config['featured_pets'])}."])
        except ValueError as error:
            if not quiet:
                messagebox.showerror('Configuración', str(error), parent=self.root)

    def _request(self):
        request = scanner_request(config_path=self.config.get(), cookies_path=self.cookies.get(),
            accounts=self.accounts.get(), workers=self.workers.get(), processes=self.groups.get(),
            inflight=self.inflight.get())
        load_config(request['config_path'])
        if self.active_profile=='eggs':
            request['profile']='eggs'
        elif self.active_profile=='joiner':
            from .joiner import target_settings
            request['profile']='joiner'
            request['target']=dict(place_id=self.join_place.get(),server_id=self.join_server.get(),vip_link=self.join_vip.get())
            target_settings(**request['target'])
        return request

    def select_profile(self,profile):
        if self.process is not None or profile==self.active_profile:
            return
        if profile not in ('brainrot','eggs','joiner'):
            raise ValueError('Tab desconocido.')
        forms=(self.accounts,self.workers,self.groups,self.inflight)
        stats=(self.servers,self.elapsed,self.featured,self.best,self.account_status)
        self.profile_forms[self.active_profile]=tuple(v.get() for v in forms)
        self.profile_stats[self.active_profile]=tuple(v.get() for v in stats)
        for variable,value in zip(forms,self.profile_forms.get(profile,('1','1','Auto','Auto'))):
            variable.set(value)
        for variable,value in zip(stats,self.profile_stats.get(profile,('0','00:00','0','—','Las cuentas aún no se han iniciado'))):
            variable.set(value)
        self.active_profile=profile
        self.health={}
        self._refresh_health()
        self.page_number=0
        egg=profile=='eggs'
        joiner=profile=='joiner'
        self.result_label.set('Jugadores' if joiner else 'Eggs' if egg else 'Featured')
        self.table_heading.set('Jugadores del servidor' if joiner else 'Steal An Egg' if egg else 'Featured')
        self.table_subheading.set('Un cliente observer · tus propios bots ocultos · haz click en un jugador' if joiner else 'Eggs en la pista · sesiones persistentes · rescan por ciclo del juego' if egg else 'Scan completo cada 30 s · base al entrar un jugador')
        self.profile_brainrot.configure(selected=profile=='brainrot')
        self.profile_eggs.configure(selected=egg)
        self.profile_joiner.configure(selected=joiner)
        if joiner:
            self.stats_panel.grid_remove()
            self.best_panel.grid_remove()
            self.joiner_target_panel.grid(row=2,column=0,sticky='ew',pady=(0,16))
            self.result_controls.pack_forget()
            self.joiner_actions.pack(side='right',anchor='n')
            self.pagination.pack_forget()
            self.joiner_command_bar.pack(side='bottom',fill='x',pady=(8,0),before=self.result_footer)
        else:
            self.stats_panel.grid()
            self.joiner_target_panel.grid_remove()
            self.best_panel.grid()
            self.joiner_actions.pack_forget()
            self.result_controls.pack(side='right',anchor='n')
            self.joiner_command_bar.pack_forget()
            self.pagination.pack(side='right')
        columns=(('username','Username',240),('display_name','Display name',260),('user_id','UserId',160)) if joiner else (('time','Tiempo',115),('pet','Egg',190),('generation','Income',120),
            ('weight','Peso, kg',110),('mutations','Mutaciones',150),('rarity','Rarity',110),
            ('area','Zona',125),('job','JobID',180),('copy','',34)) if egg else (
            ('time','Tiempo',120),('pet','Pet / mutación',290),('generation','Income',150),('job','JobID',250),('copy','',34))
        self.tree.configure(columns=tuple(c[0] for c in columns))
        for name,title,width in columns:
            self.tree.heading(name,text=title,anchor='w')
            self.tree.column(name,width=width,minwidth=34 if name=='copy' else min(width,90),
                             stretch=name in ('pet','job','username','display_name'),anchor='w')
        self.empty_history.configure(text='Esperando la lista de jugadores…' if joiner else 'Aquí aparecerán los eggs de Steal An Egg' if egg else 'Aquí aparecerán los Featured encontrados')
        if not egg:
            self.cycle_label.set('')
        else:
            self._cycle_second=None
            if self.egg_cycle_end is None:
                self.cycle_label.set('Ciclo: —')
        self._refresh_history()

    def save_settings(self):
        try:
            request = self._request()
            config = load_config(request['config_path'])
            config['scanner'].update(workers=request['workers'], processes=request['processes'], inflight=request['inflight'])
            save_json(Path(request['config_path']), config)
            self._save_preferences(request)
            self._append_log(['Ajustes guardados. La lista Featured se conservó íntegra.'])
        except (ValueError, OSError) as error:
            messagebox.showerror('Ajustes', str(error), parent=self.root)

    def _save_preferences(self, request):
        values={k:request[k] for k in ('config_path','cookies_path','accounts')}
        values['joiner_target']=dict(place_id=self.join_place.get(),server_id=self.join_server.get(),vip_link=self.join_vip.get())
        save_json(self.data/'settings.json',values)

    def start(self):
        if self.process is not None:
            return
        try:
            request = self._request()
            self._save_preferences(request)
            self.run_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
            if self.active_profile=='joiner':
                self.join_players=[]
                self.join_job=None
                self.join_observer=None
                self.table_dirty=True
            if self.active_profile=='eggs':
                self.egg_history.current_run=self.run_id
                self.egg_batches.clear()
                self.table_dirty=True
            logs = self.data / 'logs'
            logs.mkdir(exist_ok=True)
            self.log_file = (logs / f'{self.run_id}.log').open('a', encoding='utf-8')
            executable = Path(sys.executable)
            if executable.name.casefold() == 'pythonw.exe' and executable.with_name('python.exe').is_file():
                executable = executable.with_name('python.exe')
            command = self.backend_command or [str(executable), '-m', 'rakbot.gui_worker']
            self.reader_done.clear()
            self.process = subprocess.Popen(command, cwd=self.base, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', text=True, bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process.stdin.write(json.dumps(request, ensure_ascii=True) + '\n')
            self.process.stdin.flush()
            self.stop_at = None
            self.status.set('Iniciando…')
            self.servers.set('0')
            self.featured.set('0')
            self.elapsed.set('00:00')
            self.best.set('—')
            if self.active_profile=='eggs':
                self.egg_cycle_end=None
                self._cycle_second=None
                self.cycle_label.set('Ciclo: —')
            self._set_running(True)
            mode='Joiner' if self.active_profile=='joiner' else 'Steal An Egg' if self.active_profile=='eggs' else 'Brainrot'
            self._append_log([f"{mode}: inicio, {request['accounts']} cuentas, workers {request['workers']}."])
            threading.Thread(target=self._read, args=(self.process,), daemon=True, name='rakbot-ui-reader').start()
        except (ValueError, OSError) as error:
            self.reader_done.set()
            if self.process is not None:
                self.process.terminate()
            else:
                self._finish()
            messagebox.showerror('Arranque', str(error), parent=self.root)

    def _set_running(self, running):
        for widget in self.inputs:
            widget.configure(state='disabled' if running else 'normal')
        self.start_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')

    def _read(self, process):
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line) if len(line) <= 1048576 else None
                    if not isinstance(event, dict):
                        raise ValueError
                except ValueError:
                    event = {'type': 'log', 'lines': ['Respuesta incorrecta del proceso de servicio.']}
                self.events.put(event)
        except (OSError, ValueError):
            pass
        finally:
            self.reader_done.set()

    def _handle(self, event):
        kind = event.get('type')
        if kind == 'log':
            self._append_log(event.get('lines', []))
        elif kind == 'started':
            if self.stop_at is None:
                self.status.set('Funcionando')
            self.account_status.set(f"Seleccionadas: {event['accounts']} · workers: {event['workers']} · grupos: {event['groups']}")
        elif kind == 'stats':
            self.servers.set(str(event['servers']))
            self.featured.set(str(event['featured']))
            seconds = int(event['elapsed'])
            self.elapsed.set(f'{seconds // 60:02}:{seconds % 60:02}')
            self.best.set(event['best'])
            if self.active_profile=='joiner':
                target=event.get('target')
                if target:
                    self.join_job=target['job_id']
                if 'active_accounts' in event:
                    self.join_scope_box.configure(values=('Todas las cuentas',)+tuple(f"#{i}" for i in event['active_accounts']))
            self.health = {key:event[key] for key in ('total','states','failure_reasons','failure_stages') if key in event}
            total=f"/{event['total']}" if 'total' in event else ''
            pending=f" · esperando: {event['pending']}" if 'pending' in event else ''
            self.account_status.set(f"Activas: {event['active']}{total}{pending} · errores: {event['failed']}")
            if self.active_profile=='joiner' and 'spawned' in event:
                self.account_status.set(self.account_status.get()+f" · personajes: {event['spawned']}")
            self._refresh_health()
        elif kind == 'featured':
            if self.history.add(self.run_id, event.get('rows', [])):
                self.table_dirty = True
            if self.relay is not None:
                self.relay.publish(event.get('rows', []))
        elif kind=='joiner_roster':
            players=event.get('players',[])
            if players!=self.join_players:
                self.join_players=players
                self.table_dirty=True
            self.join_job=event.get('job_id') or self.join_job
            self.join_observer=event.get('observer')
            observer=f"cuenta #{self.join_observer}" if self.join_observer else 'esperando cliente'
            self.table_subheading.set(f'{observer} · tus propios bots ocultos · haz click en un jugador')
        elif kind == 'egg_scan':
            rows=event['rows']
            if event.get('replace'):
                key=(event['account'],event['job_id'])
                if event.get('offset')==0:
                    self.egg_batches[key]={'sample_id':event.get('sample_id'),'rows':[]}
                batch=self.egg_batches.get(key)
                if batch is None or batch['sample_id']!=event.get('sample_id') or event.get('offset')!=len(batch['rows']):
                    self.egg_batches.pop(key,None)
                    return
                batch['rows'].extend(rows)
                if len(batch['rows'])>10000:
                    self.egg_batches.pop(key,None)
                    return
                if not event.get('final'):
                    return
                rows=self.egg_batches.pop(key)['rows']
                self.egg_history.replace_snapshot(self.run_id,rows=rows,job_id=event['job_id'],
                    account=event['account'],detected_at=event['detected_at'])
                self.table_dirty=True
            elif self.egg_history.add(self.run_id,rows=rows,job_id=event['job_id'],
                account=event['account'],detected_at=event['detected_at']):
                self.table_dirty=True
            timing=event.get('cycle')
            if isinstance(timing,dict):
                self.egg_cycle_end=time.monotonic()+timing['seconds_until_reset']
                self.egg_cycle_night=timing['night_seconds']
                self.egg_cycle_running=timing['running']
                self._cycle_second=None
        elif kind=='server_changed' and self.active_profile=='eggs':
            self.egg_history.remove_server(self.run_id,event['previous_job'])
            self.egg_batches.pop((event['account'],event['previous_job']),None)
            self.table_dirty=True
        elif kind == 'error':
            self._append_log(['Error: ' + event.get('message', 'El scanner terminó con error.')])
            self.status.set('Error')
        elif kind == 'finished':
            label='jugadores' if self.active_profile=='joiner' else 'eggs' if self.active_profile=='eggs' else 'Featured'
            self._append_log([f"Scanner detenido. Servidores: {event['servers']}, {label}: {event['featured']}."])

    def _poll(self):
        if self.active_profile=='eggs' and self.egg_cycle_end is not None:
            remaining=max(0,math.ceil(self.egg_cycle_end-time.monotonic()))
            if remaining!=self._cycle_second:
                self._cycle_second=remaining
                minutes,seconds=divmod(remaining,60)
                phase='Noche' if remaining<=self.egg_cycle_night else 'Reset'
                self.cycle_label.set(f'{phase}: {minutes:02}:{seconds:02}' if self.egg_cycle_running else 'Ciclo pausado')
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle(event)
            except (KeyError, TypeError, ValueError, OSError, sqlite3.Error):
                self._append_log(['Error procesando el resultado. El scanner se detiene.'])
                self.stop()
        if self.table_dirty:
            try:
                self._refresh_history()
            except sqlite3.Error:
                self.table_dirty = False
                self._append_log(['No se pudo abrir el historial Featured. El scanner se detiene.'])
                self.stop()
        if self.process is not None:
            if self.stop_at is not None and time.monotonic() >= self.stop_at and self.process.poll() is None:
                self.process.terminate()  # The scanner's kill-on-close job owns every game child.
                self.stop_at = None
            if self.process.poll() is not None and self.reader_done.is_set() and self.events.empty():
                self._finish()
        if self.closing and self.process is None:
            if self.relay is not None:
                self.relay.stop()
            self.history.close()
            self.egg_history.close()
            self.root.destroy()
            return
        self.root.after(100 if self.process is not None else 400, self._poll)

    def _finish(self):
        if self.process is not None:
            if self.process.returncode not in (None, 0) and self.status.get() != 'Error':
                self._append_log([f'El proceso del scanner terminó con código {self.process.returncode}.'])
                self.status.set('Error')
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
            self.process = None
        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None
        self.stop_at = None
        if self.status.get() != 'Error':
            self.status.set('Detenido')
        self._set_running(False)

    def stop(self):
        if self.process is None or self.stop_at is not None:
            return
        self.status.set('Deteniéndose…')
        self.stop_button.configure(state='disabled')
        self.stop_at = time.monotonic() + self.stop_timeout
        try:
            self.process.stdin.write('quit\n')
            self.process.stdin.flush()
        except (OSError, ValueError):
            self.process.terminate()

    def close(self):
        self.closing = True
        self.start_button.configure(state='disabled')
        self.stop()

    def _append_log(self, lines):
        if not lines:
            return
        lines = [str(line) for line in lines]
        value = '\n'.join(lines) + '\n'
        if self.log_file is not None:
            try:
                self.log_file.write(value)
                self.log_file.flush()
            except OSError:
                try:
                    self.log_file.close()
                except OSError:
                    pass
                self.log_file = None
                value = 'No se pudo guardar el archivo de log. La salida continúa en la ventana.\n' + value
        at_bottom = self.log.yview()[1] >= 0.98
        self.log.configure(state='normal')
        self.log.insert('end', value)
        count = int(self.log.index('end-1c').split('.')[0])
        if count > 5000:
            self.log.delete('1.0', f'{count - 5000}.0')
        if at_bottom:
            self.log.see('end')
        self.log.configure(state='disabled')

    def clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def set_sort(self):
        self.page_number = 0
        self._refresh_history()

    def clear_featured(self):
        history = self.egg_history if self.active_profile=='eggs' else self.history
        history.clear()
        self.page_number = 0
        self._refresh_history()
        self._append_log(['Lista de resultados vaciada. Los nuevos resultados se añadirán en las siguientes verificaciones.'])

    def open_logs(self):
        import os
        folder=self.data/'logs'
        folder.mkdir(exist_ok=True)
        try:
            os.startfile(str(folder.resolve()))
        except OSError:
            messagebox.showerror('Logs',f'No se pudo abrir la carpeta: {folder.resolve()}',parent=self.root)

    def show_health(self):
        from .gui_onyx import BG,PANEL,TEXT,Button,label
        if self.health_window is not None and self.health_window.winfo_exists():
            self.health_window.lift()
            return
        window=self.health_window=tk.Toplevel(self.root)
        window.title('Estados de las cuentas')
        window.configure(bg=BG)
        window.geometry('740x520')
        window.minsize(600,400)
        label(window,'Estados de las cuentas',size=18,bold=True).pack(anchor='w',padx=20,pady=16)
        self.health_body=tk.Text(window,bg=PANEL,fg=TEXT,relief='flat',wrap='word',
            font=('Segoe UI',11),padx=14,pady=12,state='disabled')
        self.health_body.pack(fill='both',expand=True,padx=20)
        Button(window,text='Abrir carpeta de logs',width=230,command=self.open_logs).pack(anchor='e',padx=20,pady=16)
        self._refresh_health()

    def _refresh_health(self):
        from .scanner_health import health_text
        if self.health_body is not None and self.health_body.winfo_exists():
            self.health_body.configure(state='normal')
            self.health_body.delete('1.0','end')
            self.health_body.insert('end',health_text(self.health) if 'states' in self.health else 'Los estados detallados aparecerán tras iniciar el scanner actualizado.')
            self.health_body.configure(state='disabled')

    def _refresh_history(self):
        self.table_dirty = False
        if self.active_profile=='joiner':
            self._refresh_players()
            return
        history=self.egg_history if self.active_profile=='eggs' else self.history
        total = history.count()
        pages = max(1, math.ceil(total / history.page_size))
        self.page_number = min(self.page_number, pages - 1)
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.row_jobs = {}
        rows = history.page(self.page_number, sort=SORT_OPTIONS[self.sort_choice.get()])
        today = datetime.now().date()
        for number, entry in enumerate(rows):
            if self.active_profile=='eggs':
                detected,pet,generation,weight,mutation,rarity,area,job=entry
            else:
                detected,pet,mutation,generation,job,account=entry
            detected = datetime.fromisoformat(detected)
            stamp = detected.strftime('%H:%M:%S' if detected.date() == today else '%d.%m %H:%M')
            displayed_job = job[:16] + '…' if len(job) > 19 else job
            values=(stamp,pet,generation,f'{weight:,.2f}'.replace(',',' '),mutation or '—',rarity,area,displayed_job,'⧉') if self.active_profile=='eggs' else (
                stamp,' '.join(filter(None,(mutation,pet))),generation,displayed_job,'⧉')
            item = self.tree.insert('', 'end', values=values, tags=('even' if number % 2 == 0 else 'odd',))
            self.row_jobs[item] = job
        if rows:
            self.empty_history.place_forget()
        else:
            self.empty_history.place(relx=.5, rely=.55, anchor='center')
        self.page_label.set(f'Total {total}')
        self.previous.configure(state='normal' if self.page_number else 'disabled')
        self.next.configure(state='normal' if self.page_number + 1 < pages else 'disabled')
        first = max(0, min(self.page_number - 2, pages - len(self.page_buttons)))
        for offset, button in enumerate(self.page_buttons):
            page = first + offset
            if page < pages:
                button.configure(text=str(page + 1), selected=page == self.page_number,
                    command=lambda p=page: self.change_page(p-self.page_number))
                button.pack(side='left', padx=3, before=self.next)
            else:
                button.pack_forget()

    def change_page(self, delta):
        self.page_number = max(0, self.page_number + delta)
        self._refresh_history()

    def copy_job(self):
        selected = self.tree.selection()
        if selected:
            job = self.row_jobs.get(selected[0])
            if not job:
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(job)

    def _refresh_players(self):
        selected=self.tree.selection()
        children=self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.row_jobs={}
        for number,player in enumerate(self.join_players):
            identity=str(player['user_id'])
            self.tree.insert('','end',iid=identity,values=(player['username'],player['display_name'],identity),
                tags=('even' if number%2==0 else 'odd',))
            self.row_jobs[identity]=self.join_job
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.page_label.set(f'Jugadores: {len(self.join_players)} · tus propias cuentas excluidas')
        if self.join_players:
            self.empty_history.place_forget()
        else:
            self.empty_history.place(relx=.5,rely=.55,anchor='center')

    def send_join_command(self,action=None,username=None):
        if self.active_profile!='joiner' or self.process is None or self.stop_at is not None:
            return
        from .joiner import validate_command
        try:
            line=validate_command((action+(' '+username if username else '')) if action else self.join_line.get())
            scope=self.join_scope.get()
            account=int(scope[1:]) if scope.startswith('#') else None
            self.process.stdin.write(json.dumps(dict(line=line,account=account),ensure_ascii=True)+'\n')
            self.process.stdin.flush()
            if action is None:
                self.join_line.set('')
        except (ValueError,OSError) as error:
            self._append_log(['Joiner: '+str(error)])

    def player_menu(self,event):
        if self.active_profile!='joiner':
            return
        row=self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        username=self.tree.item(row,'values')[0]
        self.player_actions.delete(0,'end')
        for title,action in (('Teleport','teleport'),('LoopTp','looptp'),('Where','where')):
            self.player_actions.add_command(label=title,command=lambda a=action:self.send_join_command(a,username))
        self.player_actions.add_separator()
        self.player_actions.add_command(label='Stop LoopTp',command=lambda:self.send_join_command('stoploop'))
        self.player_actions.add_command(label='Copy username',command=lambda:self.copy_username(username))
        try:
            self.player_actions.tk_popup(event.x_root,event.y_root)
        finally:
            self.player_actions.grab_release()
        return 'break'

    def _start_relay(self):
        """WebSocket relay for LEET NOTIFIER clients; settings and key live in relay.json."""
        def emit(line):
            try:
                self.events.put_nowait({'type': 'log', 'lines': [line]})
            except queue.Full:
                pass
        try:
            settings = load_relay_settings(self.base / 'relay.json')
            if not settings['enabled']:
                return None
            relay = Relay(settings['host'], settings['port'], settings['key'], emit=emit)
            relay.start()
            return relay
        except (OSError, ValueError) as error:
            emit(str(error))
            return None

    def copy_username(self,username):
        self.root.clipboard_clear()
        self.root.clipboard_append(username)


def main(*, config_path=None, cookies_path=None):
    root = tk.Tk()
    try:
        App(root, config_path=config_path, cookies_path=cookies_path, relay=True)
        root.mainloop()
    except (OSError, ValueError, sqlite3.Error) as error:
        messagebox.showerror('RAKBOT', str(error), parent=root)
        root.destroy()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
