"""The sole authoritative rules coordinator; never selects Bot strategy."""
import copy
from configuration import validate_config, VERSION
from native import Native
from numeric import digest, RNG, stream_seed, q
from contracts import validate_named

ROLES = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]


class BaseballEngine:
    def __init__(self, config=None, seed="42"):
        self.native = Native()
        self.config = None
        self.state = None
        self.events = []
        if config is not None:
            self.initialize(config, self.initial_state(config, seed))

    @staticmethod
    def initial_state(config, seed="42"):
        validate_config(config)
        if not seed.isdecimal() or not 0 <= int(seed) < (1 << 64):
            raise ValueError("invalid_seed")
        players = []
        for team in ("away", "home"):
            for i, (role, position) in enumerate(zip(ROLES, config["field"]["defense_q"])):
                players.append({"id": f"{team}.P{i+1:02}", "team_id": team, "role": role,
                                "position_q": position[:], "velocity_q": ["0", "0"], "active_intents": {}})
        return {"schema_version": VERSION, "ruleset_version": config["version"],
                "physics_version": config["physics"]["version"], "map_version": config["field"]["version"],
                "config_hash": digest(config), "sim_tick": 0, "phase": "INIT", "phase_start_tick": 0,
                "phase_deadline_tick": 0, "inning": 1, "half": "top", "transition_from_half": None,
                "pending_transition": None, "regulation_expired": False, "finish_after_inning": None,
                "score": {"away": 0, "home": 0}, "outs": 0, "balls": 0, "strikes": 0,
                "batting_order_index_by_team": {"away": 0, "home": 0}, "completed_halves": {"away": 0, "home": 0},
                "play_id": 0, "plate_appearance_id": 0, "pitch_id": 0, "pitches_total": 0,
                "ball": {"mode": "dead", "position_q": ["0", "0", "0"], "velocity_q": ["0"]*3,
                         "holder_id": None, "origin": None, "has_touched_ground_since_bat": False,
                         "fair_foul_status": "undecided"},
                "players": players, "runners": [], "pitch_start_bases": [], "force_state": [],
                "pending_runs": [], "pending_appeals": [], "swing_windows": None,
                "settle_counter": 0, "recovery_counter": 0, "scheduled_actions": [],
                "pending_boundary_events": [], "rng_stream_states": {
                    name: [str(v) for v in RNG(stream_seed(seed, name)).state]
                    for name in ("setup", "engine")}, "action_cursor": 0, "last_event_seq": 0,
                "terminal_status": None, "termination_reason": None}

    def initialize(self, config, initial_state):
        self.config = copy.deepcopy(validate_config(config))
        self.restore(initial_state)

    def snapshot(self):
        return copy.deepcopy(self.state)

    def restore(self, snapshot):
        validate_named(snapshot, "state")
        if snapshot["schema_version"] != VERSION:
            raise ValueError("unsupported_version")
        if self.config is not None and snapshot["config_hash"] != digest(self.config):
            raise ValueError("configuration_mismatch")
        self.state = copy.deepcopy(snapshot)
        self.check_invariants()
        self.events = []

    def check_invariants(self):
        s = self.state
        assert 0 <= s["outs"] <= 3 and s["sim_tick"] >= 0
        assert all(type(v) is int and v >= 0 for v in s["score"].values())
        assert len({p["id"] for p in s["players"]}) == 18
        for p in s["players"]:
            assert all(type(v) is str and abs(int(v)) <= 1000*(1 << 32) for v in p["position_q"])
        assert s["ball"]["holder_id"] is None or s["ball"]["holder_id"] in {p["id"] for p in s["players"]}

    def canonical_state_hash(self):
        return digest(self.state)

    def observe(self, team_id):
        if team_id not in ("away", "home"):
            raise ValueError("unknown_team")
        return self.snapshot()

    def terminal_result(self):
        s = self.state
        if not s["terminal_status"]:
            return None
        return {"status": s["terminal_status"], "score": copy.deepcopy(s["score"]),
                "sim_tick": s["sim_tick"], "reason": s["termination_reason"],
                "final_state_hash": self.canonical_state_hash()}
