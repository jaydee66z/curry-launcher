"""Validated Egg reporting settings and a credential-free compact log."""
import math

UNFILTERED_GAME=dict(min_value=0,states=['Slot'],earnings_mode='game',mutation_multipliers={})


def settings(value=None):
    if value is None:
        value={}
    if not isinstance(value,dict) or set(value)-{'min_value','states','earnings_mode','mutation_multipliers',
            'cycle_fallback','night_fallback','reset_grace'}:
        raise ValueError('Invalid Egg filter settings.')
    result=dict(min_value=10000000000,states=['Slot',''],earnings_mode='game',mutation_multipliers={},
        cycle_fallback=300,night_fallback=10,reset_grace=2)
    result.update(value)
    threshold=result['min_value']
    if type(threshold) not in (int,float) or not 0<=threshold<=1e40 or not math.isfinite(threshold):
        raise ValueError('Egg min_value must be a finite nonnegative number.')
    if not isinstance(result['states'],list) or not result['states'] or any(s not in ('Slot','') for s in result['states']):
        raise ValueError('Egg states must contain Slot and/or an empty string.')
    if result['earnings_mode'] not in ('game','product'):
        raise ValueError('Egg earnings_mode must be game or product.')
    for key,low,high in (('cycle_fallback',1,310),('night_fallback',0,310),('reset_grace',0,60)):
        value=result[key]
        if type(value) not in (int,float) or not low<=value<=high or not math.isfinite(value):
            raise ValueError('Invalid Egg cycle timing settings.')
    multipliers=result['mutation_multipliers']
    if not isinstance(multipliers,dict) or len(multipliers)>64 or any(
        not isinstance(k,str) or not 0<len(k)<=128 or any(ord(c)<32 for c in k) or
        type(v) not in (int,float) or not 0<v<=1e6 or not math.isfinite(v) for k,v in multipliers.items()):
        raise ValueError('Invalid Egg mutation multipliers.')
    result['states']=list(result['states'])
    result['mutation_multipliers']=dict(multipliers)
    return result


def format_report(row):
    def clean(value):
        return ''.join(c for c in str(value) if ord(c)>=32 and ord(c)!=127)
    mutations='+'.join(clean(m) for m in row.get('mutations',[]))
    return (f"[filter] {clean(row['DisplayName'])}  scale={row['scale']:.2f}  "
            f"mutations={mutations}  value={row['income']/1e9:.2f}B/s")
