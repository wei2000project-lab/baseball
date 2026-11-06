"""Strict versioned config. Physical numbers are Q32.32 decimal strings."""
from pathlib import Path
from numeric import strict_loads

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0-dev.P2"


def default_config():
    return strict_loads((ROOT / "config/default.json").read_text(encoding="utf-8"))


def validate_config(config):
    template = default_config()
    def check(value, expected, path):
        if type(value) is not type(expected):
            raise ValueError(f"{path}: invalid_type")
        if isinstance(expected, dict):
            if value.keys() != expected.keys():
                raise ValueError(f"{path}: unknown_or_missing_field")
            for k in expected:
                check(value[k], expected[k], f"{path}.{k}")
        elif isinstance(expected, list):
            if len(value) != len(expected):
                raise ValueError(f"{path}: invalid_length")
            for n, (v, e) in enumerate(zip(value, expected)):
                check(v, e, f"{path}[{n}]")
        elif type(expected) is int:
            if value <= 0 or value > 10_000_000:
                raise ValueError(f"{path}: out_of_range")
        elif isinstance(expected, str):
            if expected.lstrip("-").isdigit():
                if str(int(value)) != value or abs(int(value)) > 1000 * (1 << 32):
                    raise ValueError(f"{path}: invalid_fixed_point")
            elif value != expected:
                raise ValueError(f"{path}: unsupported_version")
    check(config, template, "config")
    r, p, f = (config[k] for k in ("rules", "physics", "field"))
    if r["max_ticks"] <= r["regulation_ticks"] or r["tick_rate_hz"] != 120:
        raise ValueError("rules: max_ticks/tick_rate_hz")
    for k, value in p.items():
        if k != "version" and int(value) <= 0:
            raise ValueError(f"physics.{k}: positive_required")
    if not 0 < int(p["ground_restitution_q"]) <= 1 << 32:
        raise ValueError("physics.ground_restitution_q: invalid_coefficient")
    if not 0 < int(p["wall_restitution_q"]) <= 1 << 32:
        raise ValueError("physics.wall_restitution_q: invalid_coefficient")
    if not 0 < int(p["ground_retention_q"]) <= 1 << 32:
        raise ValueError("physics.ground_retention_q: invalid_coefficient")
    for kind in ("pitch", "throw", "bat"):
        if not 0 < int(p[f"{kind}_min_speed_q"]) <= int(p[f"{kind}_max_speed_q"]) <= 100 * (1 << 32):
            raise ValueError(f"physics.{kind}: invalid_speed_range")
    if not 0 < int(p["player_speed_q"]) <= 100 * (1 << 32):
        raise ValueError("physics.player_speed_q: invalid_speed")
    for low, high in (("xmin_q", "xmax_q"), ("ymin_q", "ymax_q"),
                      ("strike_xmin_q", "strike_xmax_q"), ("strike_zmin_q", "strike_zmax_q")):
        if int(f[low]) >= int(f[high]):
            raise ValueError(f"field.{low}: invalid_geometry")
    for name in ("bat_box_q", "body_box_q"):
        if any(int(f[name][i]) >= int(f[name][i+1]) for i in (0, 2, 4)):
            raise ValueError(f"field.{name}: invalid_geometry")
    positions = [tuple(pos) for pos in f["defense_q"]]
    if len(set(positions)) != 9:
        raise ValueError("field.defense_q: overlapping_initial_positions")
    for x, y in positions + [tuple(pos) for pos in f["bases_q"]]:
        if not int(f["xmin_q"]) <= int(x) <= int(f["xmax_q"]) or not int(f["ymin_q"]) <= int(y) <= int(f["ymax_q"]):
            raise ValueError("field: position_out_of_bounds")
    if int(f["wall_radius_q"]) < 50 * (1 << 32):
        raise ValueError("field.wall_radius_q: too_small")
    return config
