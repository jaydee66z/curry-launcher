"""Read literal catalog fields from verified Luau bytecode, without executing it."""
from dataclasses import dataclass
from functools import lru_cache
from decimal import Decimal, ROUND_DOWN
import math

from .luau_bytecode import unpack_rsb
from .luau_static import parse


@dataclass(frozen=True)
class Reference:
    path: tuple


UNKNOWN = object()


def _text(value):
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else value


def literal_tables(module):
    """Bounded straight-line dataflow of table literals, not a Luau interpreter.

    Calls are opaque except table.freeze's identity result. References represent
    property names only (e.g. Rarities.Legendary); no function or require is run.
    This deliberately returns partial facts rather than fabricating live state.
    """
    function = module['functions'][module['main']]
    constants, registers, tables, keys = function['constants'], {}, [], {}
    def constant(index):
        value = constants[index]
        return _text(value) if type(value) in (bytes, str, int, float, bool) or value is None else UNKNOWN
    def make(values=None):
        table = dict(values or {})
        tables.append(table)
        keys[id(table)] = set()
        return table
    for ins in function['instructions']:
        op, a, b, c = ins['op'], ins['a'], ins['b'], ins['c']
        if op == 'DUPTABLE':
            spec = constants[ins['d']]
            registers[a] = make({constant(k):constant(v) if v >= 0 else UNKNOWN
                                 for k,v in spec.get('table_values', ())})
        elif op == 'NEWTABLE':
            registers[a] = make()
        elif op == 'LOADK':
            registers[a] = constant(ins['d'])
        elif op == 'LOADN':
            registers[a] = ins['d'] if ins['d'] < 32768 else ins['d']-65536
        elif op == 'LOADB':
            registers[a] = bool(b)
        elif op == 'LOADNIL':
            registers[a] = None
        elif op == 'MOVE':
            registers[a] = registers.get(b, UNKNOWN)
        elif op == 'GETIMPORT':
            value = ins.get('aux', 0)
            count = value >> 30
            indices = ((value >> 20) & 1023, (value >> 10) & 1023, value & 1023)
            registers[a] = Reference(tuple(constant(i) for i in indices[:count]))
        elif op == 'GETTABLEKS':
            source, member = registers.get(b), _text(ins['member'])
            registers[a] = source.get(member, UNKNOWN) if isinstance(source, dict) else Reference(
                (source.path if isinstance(source, Reference) else ()) + (member,))
        elif op == 'SETTABLEKS':
            parent, member, value = registers.get(b), _text(ins['member']), registers.get(a, UNKNOWN)
            if isinstance(parent, dict):
                parent[member] = value
                if isinstance(value, dict):
                    keys[id(value)].add(member)
        elif op in ('CALL', 'CALLFB'):
            callee, argument = registers.get(a), registers.get(a+1, UNKNOWN)
            frozen = isinstance(callee, Reference) and callee.path == ('table', 'freeze')
            result = argument if frozen else UNKNOWN
            for register in range(a, a+max(1,c-1) if c else 256):
                registers[register] = UNKNOWN
            registers[a] = result
        elif op in ('GETUPVAL','GETTABLE','GETTABLEN','NAMECALL','DUPCLOSURE','NEWCLOSURE'):
            registers[a] = UNKNOWN
        elif op == 'SETLIST':
            parent = registers.get(a)
            if isinstance(parent, dict) and c:
                for offset in range(c-1):
                    parent[ins.get('aux',1)+offset] = registers.get(b+offset, UNKNOWN)
    result = []
    for table in tables:
        row = {k:v for k,v in table.items() if isinstance(k,str) and
               (type(v) in (str,int,float,bool) or v is None)}
        rarity = table.get('Rarity')
        if isinstance(rarity, Reference) and rarity.path:
            row['Rarity'] = rarity.path[-1]
        row['_keys'] = tuple(keys[id(table)])
        result.append(row)
    return result


@lru_cache(maxsize=768)
def facts(blob):
    module = parse(unpack_rsb(blob))
    rows = literal_tables(module)
    main = module['functions'][module['main']]['instructions']
    for index, ins in enumerate(main):
        if ins.get('member') == b'FromTemplate':
            for after in main[index+1:index+5]:
                value = _text(after.get('constant'))
                if after['op'] == 'LOADK' and isinstance(value,str):
                    for row in rows:
                        if 'EarningRate' in row and 'ModelWeight' not in row:
                            row['_template'] = value
                    break
    return rows


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def game_money(value):
    # FormatAbbreviated calls RoundFigures(value, 3, nil, math.floor).
    # Keep the exact income separately; only the label loses precision.
    amount=Decimal(str(value))
    units=('', 'K', 'M', 'B', 'T', 'Qa', 'Qi', 'Sx', 'Sp', 'Oc', 'No', 'Dc')
    unit=0
    while abs(amount)>=1000 and unit<len(units)-1:
        amount/=1000
        unit+=1
    quantum=Decimal(1).scaleb(amount.adjusted()-2) if amount else Decimal(1)
    amount=amount.quantize(quantum,rounding=ROUND_DOWN)
    rendered=format(amount,'f')
    if '.' in rendered:
        rendered=rendered.rstrip('0').rstrip('.')
    return '$'+rendered+units[unit]


class Catalog:
    def __init__(self):
        self.pets, self.mutations = {}, {}
        self.earnings = {}
        self.area_cycle = {}
        self.sources = set()

    def module(self, name, path, blob):
        if name in ('GameplayBalance','HalloweenPets') or '.Assets.Configs.' in path or '.Mutations.Catalog' in path:
            try:
                rows = facts(blob)
            except (ValueError, IndexError, KeyError, OverflowError):
                return False
            if name == 'GameplayBalance':
                for row in rows:
                    if all(finite(row.get(k)) for k in ('TAPER_KNEE_SCALE','STEEP_SCALE_POWER','TAPERED_SCALE_POWER','MINIMUM_RATE')):
                        self.earnings = {k:row[k] for k in ('TAPER_KNEE_SCALE','STEEP_SCALE_POWER','TAPERED_SCALE_POWER','MINIMUM_RATE')}
                    if finite(row.get('PERIOD_SECONDS')) and finite(row.get('NIGHT_SECONDS_DEFAULT')):
                        self.area_cycle = {k:v for k,v in row.items() if finite(v)}
            for row in rows:
                if isinstance(row.get('DisplayName'),str) and finite(row.get('EarningRate')):
                    ids = [row.get('_id'), row.get('Id'), *row.get('_keys',())]
                    if '.Assets.Configs.' in path:
                        ids = [name]
                    for identity in ids:
                        if isinstance(identity,str) and identity not in ('Specs','Directory','All'):
                            if self.pets.get(identity,{}).get('source')!='halloween' or name=='HalloweenPets':
                                self.pets[identity] = {**row,'source':'halloween' if name=='HalloweenPets' else 'normal'}
                if finite(row.get('EarningsScalar')):
                    for identity in (row.get('Id'), *row.get('_keys',())):
                        if isinstance(identity,str):
                            self.mutations[identity] = row
            self.sources.add(name)
            return True
        return False

    def row(self, record, *, admin_multiplier=1,earnings_mode='game',mutation_multipliers=None):
        # Report the egg's card rate, not a player's boosted payout.
        # Keep admin_multiplier accepted for older callers, without applying it.
        category = _text(record.get(b'AssetCategory',record.get('AssetCategory')))
        cfg = self.pets.get(category)
        seen = set()
        while cfg and cfg.get('_template') and cfg['_template'] not in seen:
            parent = cfg['_template']
            seen.add(parent)
            inherited = self.pets.get(parent)
            if inherited is None:
                return None
            cfg = {**inherited, **{k:v for k,v in cfg.items() if k != '_template'}}
        scale = record.get(b'AssetScale',record.get('AssetScale',1))
        raw_mutations = record.get(b'Mutations',record.get('Mutations',[]))
        mutations = [_text(v) for v in raw_mutations] if isinstance(raw_mutations,list) else []
        overrides=mutation_multipliers or {}
        if cfg is None or not finite(cfg.get('ModelWeight')) or not finite(scale) or not 0 < scale <= 100000 or earnings_mode=='game' and not self.earnings:
            return None
        if any(not isinstance(m,str) or m not in self.mutations and not (earnings_mode=='product' and m in overrides) for m in mutations):
            return None
        if earnings_mode=='product':
            factor=scale**1.85
            scalars=[overrides[m] if m in overrides else self.mutations[m]['EarningsScalar'] for m in mutations]
            if any(not finite(v) or v<=0 for v in scalars):
                return None
            value=cfg['EarningRate']*factor*math.prod(scalars)
        elif earnings_mode=='game':
            setting = self.earnings
            knee = setting['TAPER_KNEE_SCALE']
            if knee <= 0:
                return None
            factor = scale ** setting['STEEP_SCALE_POWER'] if scale <= knee else (
                knee ** setting['STEEP_SCALE_POWER'] * (scale/knee) ** setting['TAPERED_SCALE_POWER'])
            multiplier = 1 + sum(max(0,self.mutations[m]['EarningsScalar']-1) for m in mutations)
            value = max(setting['MINIMUM_RATE'], math.floor(cfg['EarningRate']*factor*multiplier+.5))
        else:
            raise ValueError('Unknown Egg earnings mode.')
        weight = cfg['ModelWeight']*scale**3
        if not finite(value) or not finite(weight):
            return None
        def get(key, default=''):
            return _text(record.get(key.encode(),record.get(key,default)))
        from .brainrot_data import money
        label=game_money(value) if earnings_mode=='game' else money(value)
        return dict(id=get('Uid'), DisplayName=cfg['DisplayName'], Generation=label+'/s', generation_value=format(Decimal(str(value)),'f'),
            Mutation=' + '.join(self.mutations.get(m,{}).get('Label',m) for m in mutations),
            mutations=mutations, weight=weight, rarity=cfg.get('Rarity',''),
            category=category, source=cfg['source'], area=get('AreaId'), state=get('State'),
            icon=cfg.get('Icon') if isinstance(cfg.get('Icon'),str) else '',
            scale=scale, income=value, base_income=cfg['EarningRate']*factor,earnings_mode=earnings_mode)
