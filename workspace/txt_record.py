"""Small TXT replay codec: T <tick> <changed key>=<JSON value>, metres in Q32.32.

Positions use decimal integer Q units, exactly as the engine/Bot protocol does.
No unchanged coordinate, duplicate action stream, or simulation checkpoints.
"""
import copy
import json

MAGIC = "BASEBALL-TXT\t2"


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False)


def short_id(pid):
    return ("a" if pid.startswith("away.") else "h") + str(int(pid[-2:]))


def project(state):
    keys = ("phase", "inning", "half", "outs", "balls", "strikes", "batter_id",
            "regulation_expired", "finish_after_inning", "terminal_status")
    values = {k: copy.deepcopy(state[k]) for k in keys}
    values.update(scoreA=state["score"]["away"], scoreH=state["score"]["home"])
    ball = state["ball"]
    for i, axis in enumerate("xyz"):
        values["b" + axis] = int(ball["position_q"][i])
        values["bv" + axis] = int(ball["velocity_q"][i])
    for k in ("mode", "holder_id", "origin", "fair_foul_status"):
        values["ball_" + k] = ball[k]
    for player in state["players"]:
        name = short_id(player["id"])
        values[name + "x"], values[name + "y"] = map(int, player["position_q"])
        values[name + "intents"] = copy.deepcopy(player["active_intents"])
        values[name + "skill"] = [player[k] for k in ("dive_until_tick","dive_ready_tick","catch_ready_tick")]
    values["runners"] = [{k: r[k] for k in ("id", "last_legal_base", "target_base", "force_obligation", "retouch_obligation")} for r in state["runners"]]
    values["pending_runs"] = [r["runner_id"] for r in state["pending_runs"]]
    return values


def restore(values, tick, rosters):
    """Viewer state only. Deliberately not a resumable authoritative GameState."""
    s = {k: copy.deepcopy(values[k]) for k in ("phase", "inning", "half", "outs", "balls", "strikes", "batter_id",
          "regulation_expired", "finish_after_inning", "terminal_status", "runners")}
    s.update(sim_tick=tick, score=dict(away=values["scoreA"], home=values["scoreH"]), players=[])
    s["ball"] = {k: values["ball_" + k] for k in ("mode", "holder_id", "origin", "fair_foul_status")}
    s["ball"].update(position_q=[str(values["b"+a]) for a in "xyz"], velocity_q=[str(values["bv"+a]) for a in "xyz"])
    for team, players in rosters.items():
        for player in players:
            name = short_id(player["id"])
            p=dict(player, team_id=team, position_q=[str(values[name+a]) for a in "xy"], active_intents=copy.deepcopy(values[name+"intents"]))
            p.update(zip(("dive_until_tick","dive_ready_tick","catch_ready_tick"),values.get(name+"skill",[0,0,0])))
            s["players"].append(p)
    s["pending_runs"] = [dict(runner_id=pid) for pid in values["pending_runs"]]
    return s


def delta_line(tick, previous, current):
    changed = {k: v for k, v in current.items() if k not in previous or previous[k] != v}
    if not changed: return None
    return "\t".join(["T", str(tick)] + [k+"="+encode(v) for k, v in sorted(changed.items())]) + "\n"
