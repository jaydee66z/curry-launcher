"""Small, credential-free account status summaries for the UI."""
from collections import Counter


STATES = {
    'active': 'Activos', 'queued': 'En cola', 'waiting_turn': 'Esperando carga',
    'authenticating': 'Autorizando', 'waiting_server': 'Esperando servidor', 'joining': 'Conectando',
    'scanning': 'Primer scan', 'reconnecting': 'Reconectando',
    'rate_limited': 'Esperando tras 429', 'network_wait': 'Esperando red',
    'failed': 'Con error', 'skipped_duplicate': 'Cuenta duplicada',
    'finished': 'Terminadas', 'unused': 'Sin iniciar',
}
FAILURES = {
    'challenge': 'Roblox requiere verificación adicional de login',
    'unauthorized': 'Sesión inválida (401)',
    'forbidden': 'Solicitud rechazada por Roblox (403)',
    'rate_limit': 'Rate limit de solicitudes (429)',
    'join_timeout': 'Timeout de conexión HTTPS',
    'server_refused': 'El servidor rechazó la conexión',
    'network': 'Error de red', 'memory': 'No se pudo asignar memoria',
    'threads': 'No se pudo crear un thread', 'process_exit': 'El proceso de grupo terminó',
    'internal': 'Error interno del cliente',
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
        return 'Las cuentas aún no se han iniciado.'
    lines = [f"Total de cuentas seleccionadas: {health['total']}", '', 'Estados:']
    lines.extend(f"  {STATES.get(state,state)}: {count}" for state,count in health['states'].items())
    reasons=health.get('failure_reasons',{})
    if reasons:
        lines.extend(('', 'Causas de los errores finales:'))
        lines.extend(f"  {FAILURES.get(code,code)}: {count}" for code,count in sorted(reasons.items()))
        stages=health.get('failure_stages',{})
        if stages:
            lines.extend(('', 'Etapas de los fallos:'))
            lines.extend(f"  {STATES.get(stage,stage)}: {count}" for stage,count in sorted(stages.items()))
    lines.extend(('', 'Workers — número de sesiones simultáneas, cargas — número de logins simultáneos.',
        'La RAM y el ancho de banda no eliminan los límites de Roblox sobre autorización y solicitudes.',
        'Los mensajes de error completos se guardan en la carpeta de logs.'))
    return '\n'.join(lines)
