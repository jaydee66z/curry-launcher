"""Observed Heli Wars normal team-selection RPC, not a generic script executor."""
from collections import Counter
import struct

from .application import string, varuint
from .native_crypto import CryptoError


def wire_guid(value):
    if (not isinstance(value, tuple) or len(value) != 2 or
            any(type(x) is not int for x in value) or
            not 1 <= value[0] <= 0xffffffff or not 0 <= value[1] <= 0xffffffff):
        raise CryptoError('Invalid instance reference.')
    return varuint(value[0]) + struct.pack('<I', value[1])


def team_request(inspector, *, invocation_id=1):
    """Return one RequestData:InvokeServer('JoinTeam', team.Name) payload.

    Target path, team names and event index come from this session. The call
    was identified statically in the game's TeamChange button handler.
    """
    own = inspector.nodes.get(inspector.own)
    if not own or own['class'] != 'Player' or own['props'].get('UserId') != inspector.user_id:
        return None

    def path(key):
        parts, seen = [], set()
        while key in inspector.nodes and key not in seen and len(parts) < 12:
            seen.add(key)
            node = inspector.nodes[key]
            parts.append(node['props'].get('Name', node['class'].encode('utf-8')))
            key = node['parent']
        return tuple(reversed(parts))

    remotes = [(key, node) for key, node in inspector.nodes.items()
               if node['class'] == 'RemoteFunction' and
               path(key) == (b'ReplicatedStorage', b'Remotes', b'RequestData')]
    teams = [node for key, node in inspector.nodes.items()
             if node['class'] == 'Team' and path(key)[:1] == (b'Teams',) and
             isinstance(node['props'].get('Name'), bytes) and
             type(node['props'].get('TeamColor')) is int]
    if len(remotes) != 1 or not teams:
        return None
    counts = Counter(node['props'].get('TeamColor') for node in inspector.nodes.values()
                     if node['class'] == 'Player' and not node['props'].get('Neutral', False))
    team = min(teams, key=lambda node: (counts[node['props']['TeamColor']], node['props']['Name']))
    try:
        team_name = team['props']['Name'].decode('utf-8')
    except UnicodeError:
        raise CryptoError('Unsupported team name encoding.') from None
    candidates = [index for index, event in enumerate(inspector.schema.events)
                  if inspector.schema.classes[event['class_id']]['name'] == 'RemoteFunction' and
                  event['name'] == 'RemoteOnInvokeServer' and
                  [arg['type'] for arg in event['arguments']] == [10, 28, 29]]
    if len(candidates) != 1 or not 1 <= invocation_id < 2**31:
        raise CryptoError('Unsupported RemoteFunction invocation schema.')
    remote = remotes[0][0]
    payload = (b'\x83\x07' + wire_guid(remote) + struct.pack('<H', candidates[0]) +
               varuint(invocation_id * 2) + wire_guid(inspector.own) +
               varuint(2) + b'\x02' + string('JoinTeam') + b'\x02' + string(team_name) + b'\0')
    return {'payload': payload, 'remote': remote, 'team_name': team_name,
            'invocation_id': invocation_id}
