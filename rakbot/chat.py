"""TextChatService requests using this session's identities and event schema."""
import struct
import re
import unicodedata
import uuid

from .application import string, varuint
from .commands import CommandError
from .heli_wars import wire_guid


SEND_EVENTS = (
    ('ClientToServerMessageReplicateSignalV4', [2, 2, 2, 28, 28, 9, 9, 2, 2]),
    ('ClientToServerMessageReplicateSignalV3', [2, 2, 2, 28, 28, 9, 9]),
    ('ClientToServerMessageReplicateSignalV2', [2, 2, 2, 28, 28]),
)
UNIVERSE_SEND_EVENTS = (
    # Native SendUniverseChatMessageAsync uses the free-text V1 signature.
    # V2 adds preset fields and is not preferred for ordinary text.
    ('ClientToServerUniverseChatMessageSignalV1', [2, 2, 2, 44, 9]),
    ('ClientToServerUniverseChatMessageSignalV2', [2, 2, 2, 44, 9, 2, 2]),
)
# Native 0x103e257fa returns TextChatTelemetryPropertyWrite for this bit.
# The official PCDesktopClient settings enable it. It is not age verification.
NATIVE_MESSAGE_TELEMETRY = True
MESSAGE_STATUS = {1: 'Unknown', 2: 'Success', 3: 'Sending', 4: 'TextFilterFailed',
                  5: 'Floodchecked', 6: 'InvalidPrivacySettings',
                  7: 'InvalidTextChannelPermissions', 8: 'MessageTooLong', 9: 'ModerationTimeout'}


class ChatUnavailable(CommandError):
    """Replicated chat identities may still arrive; no packet was sent."""


def new_message_id(user_id, *, nonce=None):
    if type(user_id) is not int or not 0 < user_id < 2**63:
        raise CommandError('No hay un UserId válido para enviar chat.')
    if nonce is None:
        nonce = uuid.uuid4()
    if not isinstance(nonce, uuid.UUID) or not nonce.int:
        raise CommandError('No se pudo crear el identificador del mensaje de chat.')
    # Native inbound 0x103e40444 drops the UserId prefix plus one separator;
    # 0x10302b7f8 requires the remaining GUID to be 38 bytes including braces.
    # Native SendUniverseChatMessageAsync 0x103e4a59d..0x103e4a71e.
    return f'{user_id}-{{{str(nonce).upper()}}}'


def validate_message_id(message_id, user_id):
    if (type(user_id) is not int or not 0 < user_id < 2**63 or not isinstance(message_id, str) or
            not re.fullmatch(re.escape(str(user_id)) + r'[-_]\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}',
                             message_id)):
        raise CommandError('El MessageId del chat debe contener el UserId de esta cuenta y un GUID entre llaves.')


def validate_text(text):
    if not isinstance(text, str) or not text.strip():
        raise CommandError('Uso: chat texto del mensaje')
    if len(text) > 200:
        raise CommandError('Un mensaje de chat: máximo 200 caracteres.')
    if any(unicodedata.category(c) in ('Cc', 'Cs') for c in text):
        raise CommandError('El mensaje no debe contener caracteres de control ni saltos de línea.')
    return text


def loaded_request(world):
    if world is None:
        return None
    services = list(world.nodes.class_items('TextChatService'))
    if len(services) != 1:
        return None
    service, _ = services[0]
    events = [e for e in world.schema.events if
              e['name'] == 'ClientToServerChatIsLoadedSignal' and not e['arguments'] and
              world.schema.classes[e['class_id']]['name'] == 'TextChatService']
    if len(events) != 1:
        return None
    return service, b'\x83\x07' + wire_guid(service) + struct.pack('<H', events[0]['id']) + b'\0'


def prepare(world, user_id, text, message_id, *, universe_service=None):
    validate_text(text)
    validate_message_id(message_id, user_id)
    if world is None:
        raise ChatUnavailable('El chat aún se está cargando.')
    services = list(world.nodes.class_items('TextChatService'))
    if len(services) != 1:
        raise ChatUnavailable('En el mundo recibido todavía no hay un TextChatService único.')
    service, _ = services[0]
    channels = []
    for key, node in world.nodes.class_items('TextChannel'):
        if node['props'].get('Name') != b'RBXGeneral':
            continue
        parent, seen = node['parent'], set()
        while parent in world.nodes and parent not in seen and len(seen) < 16:
            if parent == service:
                channels.append(key)
                break
            seen.add(parent)
            parent = world.nodes[parent]['parent']
    if len(channels) != 1:
        raise ChatUnavailable('El canal general RBXGeneral aún no se ha recibido o no está disponible en este juego.')
    channel = channels[0]
    sources = [(key, node) for key, node in world.nodes.children(channel)
               if node['class'] == 'TextSource' and node['props'].get('UserIdReplicated') == user_id]
    if len(sources) > 1:
        order = getattr(world, 'chat_source_order', {})
        if all(key in order for key, _ in sources):
            sources = [max(sources, key=lambda pair: order[pair[0]])]
    if sources and all(node['props'].get('CanSend', True) is False for _, node in sources):
        raise CommandError('Roblox prohibió el envío en este canal: TextSource.CanSend=false.')
    schema = world.schema
    service_events = next((c.get('events', schema.events) for c in schema.classes
                           if c['name'] == 'TextChatService'), [])
    if universe_service == service:
        for name, types in UNIVERSE_SEND_EVENTS:
            events = [e for e in service_events if
                      schema.classes[e['class_id']]['name'] == 'TextChatService' and
                      e['name'] == name and [a['type'] for a in e['arguments']] == types]
            if len(events) != 1:
                continue
            # Native event registration 0x1005f4a2d..0x1005f4b2a:
            # text, metadata, messageId, this account's userId, verified, presets.
            values = (string(text) + string('') + string(message_id) + varuint(user_id << 1) +
                      bytes([NATIVE_MESSAGE_TELEMETRY]))
            if len(types) == 7:
                values += string('') + string('')
            packet = b'\x83\x07' + wire_guid(service) + struct.pack('<H', events[0]['id']) + values + b'\0'
            return {'packet': packet, 'service': service, 'source': None, 'channel_ref': channel,
                    'channel': 'Global', 'wire_event': name, 'loaded_packet': None}
        raise CommandError('El servidor asignó UniverseChat, pero el schema de envío no está soportado.')
    if len(sources) != 1:
        raise ChatUnavailable('La cuenta aún no se ha añadido al chat general o el chat no está disponible para ella.')
    source, node = sources[0]
    if node['props'].get('CanSend', True) is not True:
        raise CommandError('Roblox prohibió el envío en este canal: TextSource.CanSend=false.')
    # The received class descriptor already indexes its events. Avoid scanning
    # the entire game schema on every broadcast account.
    for name, types in SEND_EVENTS:
        events = [event for event in service_events if
                  schema.classes[event['class_id']]['name'] == 'TextChatService' and
                  event['name'] == name and [arg['type'] for arg in event['arguments']] == types]
        if len(events) != 1:
            continue
        event = events[0]
        # Native registration 0x1005f42ef..0x1005f4463:
        # text, metadata, messageId, textSource, textChannel.
        values = string(text) + string('') + string(message_id) + wire_guid(source) + wire_guid(channel)
        if len(types) >= 7:
            # Match the native telemetry bit; text is not pre-escaped.
            # The server still performs account/channel checks and filtering.
            values += bytes([NATIVE_MESSAGE_TELEMETRY, False])
        if len(types) == 9:
            values += string('') + string('')  # No preset ID/version.
        packet = b'\x83\x07' + wire_guid(service) + struct.pack('<H', event['id']) + values + b'\0'
        loaded = [e for e in service_events if e['name'] == 'ClientToServerChatIsLoadedSignal' and
                  schema.classes[e['class_id']]['name'] == 'TextChatService' and not e['arguments']]
        loaded_packet = (b'\x83\x07' + wire_guid(service) + struct.pack('<H', loaded[0]['id']) + b'\0'
                         if len(loaded) == 1 else None)
        return {'packet': packet, 'service': service, 'source': source, 'channel_ref': channel,
                'channel': 'Here', 'wire_event': name, 'loaded_packet': loaded_packet}
    raise CommandError('El schema del servidor no contiene un envío soportado de TextChatService.')


def receipt(name, arguments):
    if name == 'TextChatService.ServerToClientMessageReplicateSignal' and len(arguments) == 8:
        return {'message_id': arguments[2], 'source': arguments[4], 'channel_ref': arguments[5],
                'status': arguments[7], 'text': arguments[0]}
    if (name in ('TextChatService.ServerToClientMessageReplicateSignalV2',
                 'TextChatService.ServerToClientUniverseChatMessageSignalV1') and len(arguments) == 1
            and isinstance(arguments[0], dict)):
        data = arguments[0]
        def get(lower, upper):
            return data.get(lower, data.get(upper))
        return {'message_id': get(b'messageId', b'MessageId'), 'status': get(b'status', b'Status'),
                'source': get(b'textSource', b'TextSource'), 'channel_ref': get(b'textChannel', b'TextChannel'),
                'text': get(b'text', b'Text'), 'sender_user_id': get(b'senderUserId', b'SenderUserId'),
                'universe': name.endswith('ServerToClientUniverseChatMessageSignalV1'),
                'for_moderation': get(b'forModeration', b'ForModeration')}
    return None
