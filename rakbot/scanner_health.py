"""Small, credential-free account status summaries for the UI."""
from collections import Counter


STATES = {
    'active': 'Активны', 'queued': 'В очереди', 'waiting_turn': 'Ждут загрузки',
    'authenticating': 'Авторизация', 'waiting_server': 'Ждут сервер', 'joining': 'Подключение',
    'scanning': 'Первый скан', 'reconnecting': 'Переподключение',
    'rate_limited': 'Ожидают после 429', 'network_wait': 'Ожидают сеть',
    'failed': 'С ошибкой', 'skipped_duplicate': 'Повторный аккаунт',
    'finished': 'Завершены', 'unused': 'Не запускались',
}
FAILURES = {
    'challenge': 'Roblox требует дополнительную проверку входа',
    'unauthorized': 'Сессия недействительна (401)',
    'forbidden': 'Запрос отклонён Roblox (403)',
    'rate_limit': 'Ограничение запросов (429)',
    'join_timeout': 'Истекло время HTTPS-подключения',
    'server_refused': 'Сервер отказал в подключении',
    'network': 'Сетевая ошибка', 'memory': 'Не удалось выделить память',
    'threads': 'Не удалось создать поток', 'process_exit': 'Завершился процесс группы',
    'internal': 'Внутренняя ошибка клиента',
}


def failure_code(error):
    # Read only to classify. Never forward arbitrary exception text to the UI.
    name = type(error).__name__
    value = str(error).casefold()
    if 'additional challenge' in value:
        return 'challenge'
    for status, code in (('401','unauthorized'),('403','forbidden'),('429','rate_limit')):
        if f'http {status}' in value:
            return code
    if name == 'ScanAttemptTimeout':
        return 'join_timeout'
    if name == 'JoinRefused':
        return 'server_refused'
    if isinstance(error, MemoryError):
        return 'memory'
    if isinstance(error, RuntimeError) and 'start new thread' in value:
        return 'threads'
    if isinstance(error, OSError) or name == 'NetworkUnavailable':
        return 'network'
    return 'internal'


def account_health(accounts):
    states = Counter(a['state'] for a in accounts)
    failures = Counter(a.get('failure_code','internal') for a in accounts if a['state']=='failed')
    stages = Counter(a.get('failure_stage','unknown') for a in accounts if a['state']=='failed')
    return dict(total=len(accounts), states=dict(states), failure_reasons=dict(failures),
        failure_stages=dict(stages),
        active=states['active'], failed=states['failed'],
        pending=sum(n for state,n in states.items() if state not in
            ('active','failed','skipped_duplicate','finished','unused')),
        reconnecting=states['reconnecting'], duplicates=states['skipped_duplicate'])


def health_text(health):
    if not health:
        return 'Аккаунты ещё не запущены.'
    lines = [f"Всего выбранных аккаунтов: {health['total']}", '', 'Состояния:']
    lines.extend(f"  {STATES.get(state,state)}: {count}" for state,count in health['states'].items())
    reasons=health.get('failure_reasons',{})
    if reasons:
        lines.extend(('', 'Причины окончательных ошибок:'))
        lines.extend(f"  {FAILURES.get(code,code)}: {count}" for code,count in sorted(reasons.items()))
        stages=health.get('failure_stages',{})
        if stages:
            lines.extend(('', 'Этапы отказов:'))
            lines.extend(f"  {STATES.get(stage,stage)}: {count}" for stage,count in sorted(stages.items()))
    lines.extend(('', 'Workers — число одновременных сессий, загрузки — число одновременных входов.',
        'RAM и скорость канала не снимают ограничения Roblox на авторизацию и запросы.',
        'Полные сообщения ошибок сохраняются в папке логов.'))
    return '\n'.join(lines)
