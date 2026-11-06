"""Stateless ctypes ABI. No Python fallback for native physics."""
import ctypes as C
import hashlib
import json
from build_native import LIB,source_digest
from numeric import ONE

I64 = C.c_int64
PTR = C.POINTER(I64)


def array(values):
    values = [int(v) for v in values]
    if any(v < -(1 << 63) or v >= (1 << 63) for v in values):
        raise ValueError("int64_overflow")
    return (I64 * len(values))(*values)


class Native:
    def __init__(self):
        if not LIB.exists():
            raise RuntimeError("native_missing: run python workspace/build_native.py")
        stamp=LIB.parent/"native-build.json"
        if not stamp.exists():raise RuntimeError("native_build_metadata_missing: rebuild native")
        metadata=json.loads(stamp.read_text())
        if metadata["source_sha256"]!=source_digest() or metadata["binary_sha256"]!=hashlib.sha256(LIB.read_bytes()).hexdigest():
            raise RuntimeError("native_stale_or_modified: rebuild native")
        self.lib = C.CDLL(str(LIB))
        self.lib.bb_numeric.argtypes = [C.c_int, C.c_int64, C.c_int64, C.POINTER(C.c_int64)]
        self.lib.bb_numeric.restype = C.c_int
        if self.lib.bb_abi() != 1:
            raise RuntimeError("native_abi_mismatch")
        signatures = {
            "bb_action": ([C.c_int, PTR, PTR, PTR], C.c_int),
            "bb_sweep_box": ([PTR, PTR, PTR, I64], I64),
            "bb_sweep_cylinder": ([PTR, PTR, PTR, PTR, I64, I64], I64),
            "bb_flight": ([PTR, PTR, PTR], C.c_int),
            "bb_move": ([PTR, PTR], C.c_int),
            "bb_field": ([I64, I64, I64], C.c_int),
            "bb_lerp": ([PTR, PTR, I64, PTR], C.c_int),
            "bb_strike": ([PTR, PTR, I64], C.c_int),
            "bb_clamp_position": ([PTR, PTR, PTR], C.c_int),
            "bb_progress": ([PTR, PTR, PTR], I64),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name); fn.argtypes = args; fn.restype = result

    def numeric(self, op, a, b=0):
        array([a, b])  # Validate before ctypes can truncate an oversized Python integer.
        result = C.c_int64()
        if self.lib.bb_numeric(op, int(a), int(b), C.byref(result)):
            raise ValueError("native_numeric_error")
        return str(result.value)

    def action(self, kind, action, physics):
        kinds = {"pitch": 0, "throw": 1, "swing": 2}
        stem = "bat" if kind == "swing" else kind
        numbers = action.get("direction_i32", [0, 0, 0]) + [action["power_u16"], action.get("azimuth_mdeg", 0), action.get("elevation_mdeg", 0)]
        if any(type(v) is not int or not -(1 << 31) <= v < (1 << 31) for v in numbers):
            raise ValueError("action_integer_range")
        out = (I64 * 9)()
        speeds = [physics[f"{stem}_min_speed_q"], physics[f"{stem}_max_speed_q"]]
        if self.lib.bb_action(kinds[kind], array(numbers), array(speeds), out):
            raise ValueError("invalid_action_vector")
        normalized = dict(action, power_u16=out[3])
        if kind == "swing":
            normalized.update(azimuth_mdeg=out[4], elevation_mdeg=out[5])
        else:
            normalized["direction_i32"] = list(out[6:9])
        return normalized, [str(v) for v in out[:3]]

    def sweep_box(self, start, end, box, radius="0"):
        result = self.lib.bb_sweep_box(array(start), array(end), array(box), int(radius))
        if result == -2:
            raise ValueError("native_geometry_error")
        return result

    def sweep_cylinder(self, start, end, player_start, player_end, radius, height):
        result = self.lib.bb_sweep_cylinder(array(start), array(end), array(player_start), array(player_end), int(radius), int(height))
        if result == -2:
            raise ValueError("native_geometry_error")
        return result

    def lerp(self, start, end, time):
        out = (I64 * 3)()
        if self.lib.bb_lerp(array(start), array(end), time, out):
            raise ValueError("native_geometry_error")
        return [str(v) for v in out]

    def fair(self, position, radius="0"):
        return bool(self.lib.bb_field(int(position[0]), int(position[1]), int(radius)))

    def advance(self, position, velocity, config, remaining=ONE, rolling=False, apply_forces=True):
        p, f = config["physics"], config["field"]
        constants = [p[k+"_q"] for k in ("gravity", "ball_radius", "ground_restitution", "ground_retention", "rolling_deceleration", "stop_speed", "rolling_threshold")]
        constants += [f["wall_radius_q"], f["wall_height_q"], p["wall_restitution_q"]]
        constants += [f[k+"_q"] for k in ("xmin", "xmax", "ymin", "ymax")]
        out = (I64 * 12)()
        if self.lib.bb_flight(array(position + velocity + [remaining, int(rolling), int(apply_forces)]), array(constants), out):
            raise ValueError("native_physics_error")
        return {"position_q": [str(v) for v in out[:3]], "velocity_q": [str(v) for v in out[3:6]],
                "consumed_q": out[6], "event": [None, "ground", "wall", "out"][out[7]], "rolling": bool(out[8]),
                "flight_velocity_q": [str(v) for v in out[9:12]]}

    def trace(self, position, velocity, config, rolling=False):
        """Standalone tick harness; engine may interleave earlier catch/bat contacts."""
        remaining, segments = ONE, []
        for i in range(32):
            result = self.advance(position, velocity, config, remaining, rolling, i == 0)
            result.pop("flight_velocity_q")
            segments.append({"start_q": position[:], **result})
            position, velocity, rolling = result["position_q"], result["velocity_q"], result["rolling"]
            remaining -= result["consumed_q"]
            if not remaining or result["event"] == "out":
                return segments
        raise ValueError("physics_contact_limit")

    def move(self, position, velocity, target, physics, radius="0", moving=True, stop_on_touch=True):
        values = position + velocity + target + [int(moving), int(stop_on_touch), physics["player_speed_q"], physics["player_acceleration_q"], radius]
        out = (I64 * 6)()
        if self.lib.bb_move(array(values), out):
            raise ValueError("native_movement_error")
        return {"position_q": [str(v) for v in out[:2]], "velocity_q": [str(v) for v in out[2:4]],
                "touch_q": out[4], "stopped": bool(out[5])}

    def find_catches(self, start, end, players, physics):
        contacts = []
        for p in players:
            if not p.get("catch_enabled", False):
                continue
            t = self.sweep_cylinder(start, end, p["start_q"]+["0"], p["end_q"]+["0"],
                                    physics["catch_radius_q"], physics["catch_height_q"])
            if t >= 0:
                contacts.append({"sub_tick_q": t, "player_id": p["id"], "kind": "catch"})
        return sorted(contacts, key=lambda c: (c["sub_tick_q"], c["player_id"]))

    def strike(self, position, config):
        f = config["field"]
        zone = [f[k+"_q"] for k in ("strike_xmin", "strike_xmax", "strike_zmin", "strike_zmax")]
        return bool(self.lib.bb_strike(array(position), array(zone), int(config["physics"]["ball_radius_q"])))

    def clamp_position(self, position, field):
        out = (I64 * 2)()
        bounds = [field[k+"_q"] for k in ("xmin", "xmax", "ymin", "ymax")]
        self.lib.bb_clamp_position(array(position),array(bounds),out)
        return [str(v) for v in out]

    def progress(self, position, start, end):
        result=self.lib.bb_progress(array(position+["0"]),array(start+["0"]),array(end+["0"]))
        if result < 0:raise ValueError("native_path_error")
        return result
