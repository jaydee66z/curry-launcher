"""Hidden scanner host. Only allowlisted progress/results cross the GUI pipe."""
from datetime import datetime
import json
from pathlib import Path
import queue
import sys
import threading
import time


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
    lock = threading.Lock()
    def send(kind, **data):
        with lock:
            sys.stdout.write(json.dumps({'type': kind, **data}, ensure_ascii=True) + '\n')
            sys.stdout.flush()
    commands = queue.Queue(maxsize=64)
    try:
        from .bootstrap import BootstrapError
        from .config import load_config
        from .gui_support import scanner_request, featured_rows
        from .mass import read_mass_credentials
        from .brainrot import PLACE_ID, format_row
        from .scan_processes import MultiProcessScanPool
        from .egg_filter import settings as egg_filter_settings,format_report
        from .scanner_health import account_health
        from .joiner import target_settings,validate_command,visible_players
        if sys.platform == 'win32':
            # A pipe reader owns stdin in this host. Use the windowless runtime
            # for spawn children so Windows does not initialize shared stdio
            # while that reader is blocked waiting for a GUI command.
            import multiprocessing
            windowless = Path(sys.executable).with_name('pythonw.exe')
            if windowless.is_file():
                multiprocessing.set_executable(str(windowless))
        raw = sys.stdin.readline(32769)
        if len(raw) > 32768:
            raise ValueError('Слишком длинные параметры запуска.')
        parameters=json.loads(raw)
        profile=parameters.pop('profile','brainrot')
        target=parameters.pop('target',None)
        if profile not in ('brainrot','eggs','joiner'):
            raise ValueError('Неизвестная вкладка сканера.')
        if profile=='joiner':
            target=target_settings(**(target or {}))
        request = scanner_request(**parameters)
        config = load_config(request['config_path'])
        settings = config['scanner']
        try:
            credentials = read_mass_credentials(request['cookies_path'], request['accounts'])
        except BootstrapError as error:
            raise BootstrapError(f"{error} Файл аккаунтов: {request['cookies_path']}. Проверь выбор файла cookies.") from None

        def read_commands():
            try:
                while True:
                    line = sys.stdin.readline(4096)
                    if not line or line.strip().casefold() in ('quit', 'exit'):
                        commands.put('quit')
                        return
                    if line.strip().casefold() == 'status':
                        commands.put('status')
                    elif profile=='joiner':
                        try:
                            payload=json.loads(line)
                            command=validate_command(payload.get('line'))
                            account=payload.get('account')
                            if account is not None and (type(account) is not int or not 1<=account<=len(credentials)):
                                raise ValueError('Недопустимый номер аккаунта.')
                            commands.put(dict(line=command,account=account))
                        except (ValueError,AttributeError) as error:
                            send('log',lines=['Joiner: '+str(error) if not isinstance(error,json.JSONDecodeError) else 'Joiner: неверный формат команды.'])
            except (OSError, ValueError):
                commands.put('quit')

        egg_count=0
        egg_counts={}
        join_rows=[]
        def status(_title):
            extra={}
            if profile=='joiner':
                extra=dict(target=pool.resolved_target,observer=pool._observer_account+1 if pool._observer_account is not None else None,
                    active_accounts=[a['account'] for a in pool.accounts if a['state']=='active'],
                    spawned=sum(a['state']=='active' and a.get('character_spawned',False) for a in pool.accounts))
            send('stats', servers=pool.title.servers, featured=len(join_rows) if profile=='joiner' else egg_count if profile=='eggs' else pool.title.featured_count,
                elapsed=max(0, int(time.monotonic() - pool.title.started)),
                best=format_row(pool.title.best) if pool.title.best else '—',
                **account_health(pool.accounts),**extra)

        place=(target['place_id'] or 1) if profile=='joiner' else 107778070777162 if profile=='eggs' else PLACE_ID
        pool = MultiProcessScanPool(credentials, place_id=place, workers=request['workers'],
            egg_settings=egg_filter_settings(config.get('eggs')) if profile=='eggs' else None,
            join_target=target if profile=='joiner' else None,
            processes=request['processes'], inflight=request['inflight'],
            scan_timeout=max(20,settings.get('timeout',4)) if profile=='eggs' else settings.get('timeout',4),
            hop_timeout=max(20,settings.get('hop_timeout',3)) if profile=='eggs' else settings.get('hop_timeout',3),
            adaptive_timeouts=not settings.get('strict_timeouts', False),
            scan_status=settings.get('status', False), featured_pets=config['featured_pets'],
            set_title=status, emit=lambda line: send('log', lines=[line]),
            emit_batch=lambda lines: send('log', lines=lines) if lines else None)

        def report(account, event):
            nonlocal egg_count
            if profile=='eggs':
                rows=event.get('rows',[])
                egg_counts[account]=len(rows)
                egg_count=sum(egg_counts.values())
                stamp=datetime.now().isoformat(timespec='milliseconds')
                for offset in range(0,max(1,len(rows)),100):
                    if rows[offset:offset+100]:
                        send('log',lines=[format_report(row) for row in rows[offset:offset+100]])
                    send('egg_scan',rows=rows[offset:offset+100],job_id=event['server_id'],account=account,
                         detected_at=stamp,cycle=event.get('cycle'),replace=True,
                         sample_id=event.get('sample_id'),offset=offset,final=offset+100>=len(rows))
                return
            found = []
            for row in featured_rows(event.get('rows', []), pool.title.names,
                server=event['server_id'], account=account,
                detected_at=datetime.now().isoformat(timespec='milliseconds')):
                found.append(row)
                if len(found) == 100:
                    send('featured', rows=found)
                    found = []
            if found:
                send('featured', rows=found)
        pool.on_scan_report = report
        if profile=='joiner':
            def roster(account,event):
                nonlocal join_rows
                join_rows=visible_players(event.get('players',[]),set(pool.identities))
                send('joiner_roster',players=join_rows,observer=account or None,job_id=event.get('server_id'))
            pool.on_roster=roster
            pool.on_join_command=lambda account,result:send('log',lines=[f"account[{account}]: "+json.dumps(result,ensure_ascii=False)])
        def server_switched(account,event):
            nonlocal egg_count
            if profile=='eggs':
                egg_counts.pop(account,None)
                egg_count=sum(egg_counts.values())
            send('server_changed',account=account,previous_job=event['previous_job'],job_id=event['job_id'])
        pool.on_server_switch=server_switched
        threading.Thread(target=read_commands, daemon=True, name='rakbot-ui-commands').start()
        send('started', accounts=len(credentials), workers=pool.workers, groups=pool.process_count)
        if profile=='eggs':
            opts=pool.egg_settings
            send('log',lines=[f"Egg filter: min_value={opts['min_value']:g} $/s | states={opts['states']} | earnings_mode={opts['earnings_mode']}"])
        pool.run(commands)
        send('finished', servers=pool.title.servers, featured=len(join_rows) if profile=='joiner' else egg_count if profile=='eggs' else pool.title.featured_count)
        return 0
    except (ValueError, OSError) as error:
        # BootstrapError messages are sanitized; never serialize arbitrary HTTP objects.
        safe = str(error) if isinstance(error, (BootstrapError, ValueError)) and not isinstance(error, json.JSONDecodeError) else 'Не удалось запустить сканер.'
        send('error', message=safe)
        return 1
    except Exception:
        send('error', message='Служебный процесс сканера завершился с ошибкой.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
