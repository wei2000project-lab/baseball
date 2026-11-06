"""Deterministic scripted acceptance controller (not engine code)."""
def strikeout_actions(state, team):
    defense = "home" if state["half"] == "top" else "away"
    if state["phase"] == "PITCH_READY" and team == defense:
        return [{"action_id":f"{team}-{state['sim_tick']}","player_id":f"{team}.P01","kind":"pitch",
                 "direction_i32":[0,-1000000,47000],"power_u16":32768}]
    return []
