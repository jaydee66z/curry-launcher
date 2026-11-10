"""Local UTF-8 JSON scanner configuration; command line values take precedence."""
import json
import math
from pathlib import Path

from .bootstrap import BootstrapError


def load_config(path=None):
    target = Path(path) if path is not None else Path(__file__).resolve().parents[1] / 'config.txt'
    try:
        with target.open('rb') as stream:
            raw = stream.read(262145)
    except FileNotFoundError:
        if path is None:
            return {'featured_pets': [], 'scanner': {}}
        raise BootstrapError('Scanner config file was not found.') from None
    except OSError:
        raise BootstrapError('Cannot read scanner config file.') from None
    try:
        if len(raw) > 262144:
            raise ValueError
        result = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(result, dict) or set(result) - {'featured_pets', 'scanner','eggs'}:
            raise ValueError
        pets, scanner = result.get('featured_pets', []), result.get('scanner', {})
        if (not isinstance(pets, list) or len(pets) > 2000 or
                any(not isinstance(p, str) or not p.strip() or len(p) > 128 or
                    any(ord(c) < 32 for c in p) for p in pets)):
            raise ValueError
        if not isinstance(scanner, dict) or set(scanner) - {
                'workers', 'processes', 'inflight', 'timeout', 'hop_timeout', 'status', 'strict_timeouts'}:
            raise ValueError
        for key, value in scanner.items():
            if key in ('status', 'strict_timeouts'):
                if type(value) is not bool:
                    raise ValueError
            elif key in ('workers', 'processes', 'inflight'):
                if value is not None and (type(value) is not int or value < 1):
                    raise ValueError
            elif type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 75:
                raise ValueError
        validated={'featured_pets': pets, 'scanner': scanner}
        if 'eggs' in result:
            from .egg_filter import settings
            validated['eggs']=settings(result['eggs'])
        return validated
    except (ValueError, UnicodeError, RecursionError):
        raise BootstrapError('Invalid scanner config: expected UTF-8 JSON with featured_pets, scanner and optional eggs settings.') from None
