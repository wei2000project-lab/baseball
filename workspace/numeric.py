"""Authoritative JSON / Q32.32 / RNG. No host floating point in game state."""
import hashlib
import json
import unicodedata
from fractions import Fraction

ONE = 1 << 32
MASK = (1 << 64) - 1


def clone_json(value):
    """Copy a JSON tree; its scalar values and string keys are immutable."""
    kind=type(value)
    if kind is dict:return {k:clone_json(v) for k,v in value.items()}
    if kind is list:return [clone_json(v) for v in value]
    return value


def q(value):
    value = Fraction(str(value)) * ONE
    return str(round(value))  # Fraction: exact nearest, ties to even


def _normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        normalized = {unicodedata.normalize("NFC", k): _normalize(v) for k, v in value.items()}
        if len(normalized) != len(value):
            raise ValueError("canonical_key_collision")
        return dict(sorted(normalized.items(), key=lambda item: item[0].encode("utf-8")))
    if value is None or type(value) in (bool, int):
        return value
    raise ValueError("non_authoritative_value")


def canonical(value):
    # JSON's short control escapes are expanded to bb-canon-v1's four hex digits.
    data = json.dumps(_normalize(value), ensure_ascii=False, separators=(",", ":"))
    import re
    data = re.sub(r'(\\+)([bfnrt])', lambda m: m[0] if len(m[1]) % 2 == 0 else
                  m[1][:-1] + {"b": r"\u0008", "f": r"\u000c", "n": r"\u000a",
                               "r": r"\u000d", "t": r"\u0009"}[m[2]], data)
    return data.encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_loads(text):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate_json_key")
            result[k] = v
        return result
    value=json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non_finite")),object_pairs_hook=pairs)
    def unicode_check(v):
        if isinstance(v,str):v.encode("utf-8",errors="strict")
        elif isinstance(v,list):
            for x in v:unicode_check(x)
        elif isinstance(v,dict):
            for k,x in v.items():unicode_check(k);unicode_check(x)
    unicode_check(value)
    return value


def stream_seed(seed, name):
    return int.from_bytes(hashlib.sha256(f"baseball-rng-v1:{seed}:{name}".encode()).digest()[:8], "little")


class RNG:
    def __init__(self, seed):
        self.state = []
        for _ in range(4):
            seed = (seed + 0x9e3779b97f4a7c15) & MASK
            z = seed
            z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & MASK
            z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & MASK
            self.state.append(z ^ (z >> 31))

    @staticmethod
    def rotl(x, k):
        return ((x << k) | (x >> (64 - k))) & MASK

    def next(self):
        s = self.state
        result = (self.rotl((s[1] * 5) & MASK, 7) * 9) & MASK
        t = (s[1] << 17) & MASK
        s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]
        s[2] ^= t; s[3] = self.rotl(s[3], 45)
        return result
