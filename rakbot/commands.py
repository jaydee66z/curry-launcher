"""Commands operate on decoded identities and receive-side world state."""
import math
import shlex
import time

from .players import _name


class CommandError(ValueError):
    pass


class PlayerUnavailable(CommandError):
    pass


def resolve_player(client, nickname=None):
    if client.world is None:
        raise PlayerUnavailable('El mundo aún se está cargando. Espera la lista de jugadores y a que aparezca el personaje.')
    players = []
    for key, node in client.world.nodes.class_items('Player'):
        if node['class'] != 'Player' or type(node['props'].get('UserId')) is not int:
            continue
        username = _name(node['props'].get('Name'))
        if username is not None:
            players.append((key, node, username))
    if nickname is None:
        matches = [p for p in players if p[0] == client.world.own and
                   p[1]['props']['UserId'] == client.info.account.user_id]
    else:
        query = nickname.casefold()
        matches = [p for p in players if p[2].casefold() == query]
        if not matches:
            matches = [p for p in players if p[2].casefold().startswith(query)]
    if len(matches) > 1:
        names = ', '.join(sorted(p[2] for p in matches)[:8])
        raise CommandError('El nickname coincide con varios jugadores: ' + names + '. Especifica el prefijo o el username completo.')
    if not matches:
        raise PlayerUnavailable('Jugador no encontrado todavía. Verifica el username completo en players o espera a que cargue la lista.')
    key, node, username = matches[0]
    return key, node, username


def root_for(client, player):
    character = player['props'].get('Character')
    model = client.world.nodes.get(character)
    if character is None or not model or model['class'] != 'Model':
        raise CommandError('El modelo del personaje del jugador aún no se ha recibido.')
    roots = [(key, node) for key, node in client.world.nodes.children(character)
             if node['parent'] == character and node['class'] in ('Part', 'MeshPart') and
             node['props'].get('Name') == b'HumanoidRootPart']
    if len(roots) != 1:
        raise CommandError('La root part del personaje aún no se ha recibido. La posición del jugador no está disponible.')
    return roots[0]


def position_for(client, nickname=None):
    _, player, username = resolve_player(client, nickname)
    root, node = root_for(client, player)
    source = getattr(client.world, 'position_sources', {}).get(root, 'CFrame')
    frame = node['props'].get(source)
    position = frame.get('position') if isinstance(frame, dict) else None
    if (not isinstance(position, (tuple, list)) or len(position) != 3 or
            any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 2**30 for v in position)):
        raise CommandError('Las coordenadas del personaje aún no se han recibido.')
    observed = client.world.position_observed.get(root)
    return {'username': username, 'user_id': player['props']['UserId'], 'root': root,
            'position': tuple(position),
            'age_seconds': round(time.monotonic() - observed, 2) if observed is not None else None,
            'source': 'replicated_' + source}


def execute(client, line):
    # Chat owns the rest of the line: apostrophes, quotes and repeated spaces
    # are message content rather than shell-style arguments.
    head = line.lstrip().split(None, 1)
    if head and head[0].casefold() == 'chat':
        return {'command': 'chat', **client.chat(head[1] if len(head) == 2 else '')}
    try:
        args = shlex.split(line)
    except ValueError:
        raise CommandError('Comilla sin cerrar en el comando.') from None
    if not args:
        return None
    command, *arguments = args
    command = command.casefold()
    if command in ('quit', 'exit') and not arguments:
        return {'command': 'quit', 'state': 'closing'}
    if command == 'help' and not arguments:
        return {'command': 'help', 'commands': ['players', 'status', 'where [username]',
                                               'teleport username', 'looptp username', 'looptp off',
                                               'stoploop', 'chat text', 'quit'],
                'teleport': 'Experimental physics request; server acceptance requires confirmation.'}
    if command == 'players' and not arguments:
        return {'command': command, **(client.player_roster.summary() if client.player_roster else {'players': []})}
    if command == 'status' and not arguments:
        s = client.summary()
        return {'command': command, **{k: s[k] for k in ('state', 'character_spawned', 'movement_ready',
                                                       'elapsed_seconds', 'last_teleport', 'character_evidence',
                                                       'loop_teleport', 'replication_diagnostics', 'last_chat',
                                                       'chat_messages_sent', 'chat_messages_confirmed',
                                                       'chat_messages_waiting', 'chat_access')}}
    if command == 'where' and len(arguments) <= 1:
        return {'command': command, **position_for(client, arguments[0] if arguments else None)}
    if command in ('tp', 'teleport') and len(arguments) == 1:
        if client._loop_tp is not None:
            client.stop_loop()
        return {'command': 'teleport', **client.teleport(arguments[0])}
    if command == 'looptp' and len(arguments) <= 1:
        if not arguments:
            return {'command': command, **client.loop_status()}
        result = client.stop_loop() if arguments[0].casefold() in ('off', 'stop') else client.start_loop(arguments[0])
        return {'command': command, **result}
    if command in ('stoploop', 'stoplooptp') and not arguments:
        return {'command': 'looptp', **client.stop_loop()}
    raise CommandError(f'Comando o argumentos desconocidos: {command[:64]}. Escribe help. Esc limpia la línea de entrada.')
