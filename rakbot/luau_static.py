"""Bounded static Luau-14 instruction/constant reader. Never executes code."""
from pathlib import Path
import re
import struct

from .luau_bytecode import Reader


def parse(raw):
    if len(raw) > 1048576:
        raise ValueError('Bytecode exceeds inspection bound')
    reader = Reader(raw)
    if reader.take(2) != b'\x0e\x03':
        raise ValueError('Unsupported Luau version')
    count = reader.var()
    if count > 65535:
        raise ValueError('String count exceeds bound')
    strings = [reader.take(reader.var()) for _ in range(count)]
    while reader.take(1)[0]:
        reader.var()
    headers = Path(__file__).resolve().parents[1] / '.reverse-inputs/luau/Common/include/Luau'
    enum = (headers / 'Bytecode.h').read_text().split('enum LuauOpcode', 1)[1].split('};', 1)[0]
    names = re.findall(r'^\s*LOP_([A-Z][A-Z0-9_]*),', enum, re.M)
    lengths = (headers / 'BytecodeUtils.h').read_text().split('inline int getOpLength', 1)[1].split('return 2;', 1)[0]
    two = set(re.findall(r'case LOP_([A-Z][A-Z0-9_]*):', lengths))
    functions = []
    count = reader.var()
    if count > 65535:
        raise ValueError('Function count exceeds bound')
    for index in range(count):
        size = reader.var()
        start = reader.at
        if not 0 < size <= len(raw) - start:
            raise ValueError('Invalid function size')
        stack, parameters, upvalues, vararg, flags = reader.take(5)
        reader.take(reader.var())
        words = reader.var()
        if words > size // 4:
            raise ValueError('Instruction count exceeds bound')
        code = struct.unpack('<' + str(words) + 'I', reader.take(words * 4))
        constants = []
        for _ in range(reader.var()):
            kind = reader.take(1)[0]
            if kind == 0:
                value = None
            elif kind == 1:
                value = bool(reader.take(1)[0])
            elif kind == 2:
                value = struct.unpack('<d', reader.take(8))[0]
            elif kind == 3:
                at = reader.var()
                if not 1 <= at <= len(strings):
                    raise ValueError('Invalid string index')
                value = strings[at - 1]
            elif kind == 4:
                value = {'import': int.from_bytes(reader.take(4), 'little')}
            elif kind == 5:
                value = {'table': [reader.var() for _ in range(reader.var())]}
            elif kind == 6:
                value = {'closure': reader.var()}
            elif kind in (7, 11):
                reader.take(16 if kind == 7 else 32)
                value = {'vector': True}
            elif kind == 8:
                value = {'table_values': [(reader.var(), int.from_bytes(reader.take(4), 'little', signed=True))
                                          for _ in range(reader.var())]}
            else:
                raise ValueError('Unsupported constant kind')
            constants.append(value)
        children = [reader.var() for _ in range(reader.var())]
        if reader.at > start + size:
            raise ValueError('Function constants exceed frame')
        reader.at = start + size
        pc, instructions = 0, []
        while pc < words:
            word = code[pc]
            opcode = (word & 255) * 203 & 255
            if opcode >= len(names):
                raise ValueError('Unknown opcode')
            name = names[opcode]
            length = 2 if name in two else 1
            if pc + length > words:
                raise ValueError('Truncated instruction')
            item = {'pc': pc, 'op': name, 'a': word >> 8 & 255,
                    'b': word >> 16 & 255, 'c': word >> 24, 'd': word >> 16}
            if length == 2:
                item['aux'] = code[pc + 1]
            if name in ('LOADK', 'GETIMPORT', 'DUPCLOSURE') and item['d'] < len(constants):
                item['constant'] = constants[item['d']]
            if name in ('GETTABLEKS', 'NAMECALL', 'SETTABLEKS') and item.get('aux', 2**32) < len(constants):
                item['member'] = constants[item['aux']]
            if name == 'NEWCLOSURE' and item['d'] < len(children):
                item['child'] = children[item['d']]
            instructions.append(item)
            pc += length
        functions.append({'index': index, 'parameters': parameters, 'upvalues': upvalues,
                          'constants': constants, 'children': children, 'instructions': instructions})
    main = reader.var()
    if main >= len(functions):
        raise ValueError('Invalid main function')
    return {'functions': functions, 'main': main, 'strings': strings}
