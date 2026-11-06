"""The sole authoritative rules coordinator; never selects Bot strategy."""
import copy
from configuration import validate_config, VERSION
from native import Native
from numeric import digest, RNG, stream_seed, q
from contracts import validate_named, validate, SCHEMAS
from numeric import strict_loads, ONE

ROLES = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]


class BaseballEngine:
    def __init__(self, config=None, seed="42"):
        self.native = Native()
        self.config = None
        self.state = None
        self.events = []
        self._action_schema = strict_loads((SCHEMAS / "action.schema.json").read_text())["properties"]["actions"]["items"]
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
                "terminal_status": None, "termination_reason": None, "half_runs":0, "half_pa":0,
                "batter_id":None, "swing_used":False}

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
        score = s["score"]
        winner = None if s["terminal_status"] != "completed" or score["away"] == score["home"] else max(score, key=score.get)
        return {"status": s["terminal_status"], "score": copy.deepcopy(score), "winner": winner,
                "completed_halves": copy.deepcopy(s["completed_halves"]), "finish_after_inning": s["finish_after_inning"],
                "sim_tick": s["sim_tick"], "reason": s["termination_reason"],
                "final_state_hash": self.canonical_state_hash()}

    @property
    def offense(self): return "away" if self.state["half"] == "top" else "home"

    @property
    def defense(self): return "home" if self.offense == "away" else "away"

    def player(self, player_id):
        return next(p for p in self.state["players"] if p["id"] == player_id)

    def _emit(self, kind, **payload):
        s = self.state
        s["last_event_seq"] += 1
        sub = getattr(self, "_sub", 0)
        tick = s["sim_tick"]
        if sub == ONE: tick += 1; sub = 0
        self.events.append({"schema_version": VERSION, "seq": s["last_event_seq"], "sim_tick": tick,
                            "sub_tick_q": sub, "play_id": s["play_id"], "type": kind, "payload": payload})

    def _phase(self, phase, duration=0):
        s = self.state
        s["phase"] = phase; s["phase_start_tick"] = s["sim_tick"]
        s["phase_deadline_tick"] = s["sim_tick"] + duration

    def _reset_ball(self):
        s = self.state; p = self.player(f"{self.defense}.P01")
        s["ball"].update(mode="pitcher_held", holder_id=p["id"], origin=None,
                         position_q=p["position_q"] + [self.config["physics"]["pitch_height_q"]],
                         velocity_q=["0"]*3, has_touched_ground_since_bat=False, fair_foul_status="undecided")
        s["swing_windows"] = None; s["swing_used"] = False
        for player in s["players"]: player["active_intents"] = {}

    def _start_half(self):
        s = self.state
        s.update(outs=0, balls=0, strikes=0, runners=[], half_runs=0, half_pa=0,
                 pending_transition=None, transition_from_half=None)
        for i, pos in enumerate(self.config["field"]["defense_q"]):
            p = self.player(f"{self.defense}.P{i+1:02}")
            p.update(position_q=pos[:], velocity_q=["0","0"], active_intents={})
        self._emit("HalfInningStarted", inning=s["inning"], half=s["half"])
        self._start_pa()

    def _start_pa(self):
        s = self.state
        s["plate_appearance_id"] += 1; s["play_id"] += 1; s["half_pa"] += 1
        s.update(balls=0, strikes=0, pending_runs=[], pitch_start_bases=[], force_state=[])
        s["batter_id"] = f"{self.offense}.P{s['batting_order_index_by_team'][self.offense]+1:02}"
        for i in (0,1):
            p = self.player(f"{self.defense}.P{i+1:02}")
            p.update(position_q=self.config["field"]["defense_q"][i][:], velocity_q=["0","0"])
        for r in s["runners"]:
            self.player(r["id"]).update(position_q=self.config["field"]["bases_q"][r["last_legal_base"] % 4][:], velocity_q=["0","0"])
        self.player(s["batter_id"]).update(position_q=[q("-.70"), "0"], velocity_q=["0","0"])
        self._reset_ball()
        self._phase("PLATE_APPEARANCE_SETUP", self.config["rules"]["plate_appearance_setup_ticks"])
        self._emit("PlateAppearanceStarted", batter_id=s["batter_id"], index=s["plate_appearance_id"])

    def _pitch_ready(self):
        s = self.state
        s["pitch_start_bases"] = copy.deepcopy(s["runners"])
        self._phase("PITCH_READY", self.config["rules"]["pitch_release_deadline_ticks"])

    def _finish_half(self):
        s = self.state
        if s["half_runs"] >= self.config["rules"]["half_run_cap"] or s["half_pa"] >= self.config["rules"]["half_pa_cap"]:
            self._emit("HalfInningCapped", runs=s["half_runs"], plate_appearances=s["half_pa"])
        s["completed_halves"][self.offense] += 1
        self._emit("HalfInningEnded", inning=s["inning"], half=s["half"], score=copy.deepcopy(s["score"]))
        s["transition_from_half"] = s["half"]
        s["pending_transition"] = "bottom" if s["half"] == "top" else "next_inning"
        s["runners"] = []; s["ball"]["mode"] = "dead"; s["ball"]["holder_id"] = None
        for p in s["players"]: p["active_intents"] = {}
        self._phase("HALF_TRANSITION", self.config["rules"]["half_inning_change_ticks"])

    def _finish_pa(self):
        s = self.state
        s["batting_order_index_by_team"][self.offense] = (s["batting_order_index_by_team"][self.offense]+1) % 9
        self._emit("PlayEnded", outs=s["outs"])
        if s["outs"] >= 3 or s["half_runs"] >= self.config["rules"]["half_run_cap"] or s["half_pa"] >= self.config["rules"]["half_pa_cap"]:
            self._finish_half()
        else: self._start_pa()

    def _run_scored(self, runner_id):
        s = self.state
        s["score"][self.offense] += 1; s["half_runs"] += 1
        self._emit("RunScored", runner_id=runner_id)

    def _walk(self, hbp=False):
        s = self.state
        self._emit("HitByPitch" if hbp else "Walk", batter_id=s["batter_id"])
        occupied = {r["last_legal_base"]:r for r in s["runners"]}
        push = []
        for base in (1,2,3):
            if base not in occupied: break
            push.append(occupied[base])
        for r in reversed(push):
            r["last_legal_base"] += 1
            self._emit("BaseAwarded", runner_id=r["id"], base=r["last_legal_base"], reason="walk")
            if r["last_legal_base"] == 4:
                self._run_scored(r["id"]); s["runners"].remove(r)
        s["runners"].append(self._new_runner(s["batter_id"], 1))
        self._emit("BaseAwarded", runner_id=s["batter_id"], base=1, reason="hit_by_pitch" if hbp else "walk")
        self._finish_pa()

    def _new_runner(self, player_id, base):
        return {"id":player_id, "origin_base":base, "last_legal_base":base, "target_base":None,
                "force_obligation":None, "retouch_obligation":None, "alive":True, "touched_bases":[base]}

    def _pitch_call(self, strike=False, foul=False, hbp=False):
        s = self.state
        self._reset_ball()
        if hbp:
            self._walk(True); return
        if strike:
            if not foul or s["strikes"] < 2: s["strikes"] += 1
            self._emit("StrikeCalled", strikes=s["strikes"], foul=foul)
            if s["strikes"] >= 3:
                s["outs"] += 1
                self._emit("Strikeout", batter_id=s["batter_id"])
                self._emit("RunnerOut", runner_id=s["batter_id"], reason="strikeout", is_force=False,
                           batter_before_first=True, base=0)
                self._finish_pa(); return
        else:
            s["balls"] += 1; self._emit("BallCalled", balls=s["balls"])
            if s["balls"] >= 4:
                self._walk(); return
        self._phase("PITCH_RESET", self.config["rules"]["pitch_reset_ticks"])

    def _boundary(self):
        s, r = self.state, self.config["rules"]
        if s["terminal_status"]: return
        if s["sim_tick"] >= r["regulation_ticks"] and not s["regulation_expired"]:
            s["regulation_expired"] = True; s["finish_after_inning"] = s["inning"]
            self._emit("RegulationExpired", finish_after_inning=s["inning"])
        if s["phase"] == "HALF_TRANSITION" and s["half"] == "bottom" and s["regulation_expired"]:
            s.update(terminal_status="completed", termination_reason="fair_inning_completed")
            self._phase("GAME_OVER"); self._emit("GameEnded", score=copy.deepcopy(s["score"])); return
        if s["sim_tick"] >= r["max_ticks"] or s["pitches_total"] >= r["max_pitches"]:
            self.abort("max_ticks" if s["sim_tick"] >= r["max_ticks"] else "max_pitches"); return
        if s["phase"] == "INIT":
            self._emit("GameStarted"); self._start_half()
        elif s["sim_tick"] >= s["phase_deadline_tick"]:
            if s["phase"] in ("PLATE_APPEARANCE_SETUP", "PITCH_RESET"): self._pitch_ready()
            elif s["phase"] == "PITCH_READY":
                s["pitches_total"] += 1; s["pitch_id"] += 1
                self._emit("PitchClockViolation"); self._pitch_call()
            elif s["phase"] == "HALF_TRANSITION":
                if s["half"] == "top": s["half"] = "bottom"
                else: s["inning"] += 1; s["half"] = "top"
                self._start_half()

    def abort(self, reason):
        if self.state["terminal_status"]: return
        self.state.update(terminal_status="aborted", termination_reason=reason)
        self._phase("ABORTED"); self._emit("GameAborted", reason=reason)

    def _legal(self, team, action):
        s = self.state; kind = action["kind"]
        if kind == "noop": return
        p = self.player(action["player_id"])
        if p["team_id"] != team: raise ValueError("unauthorized_player")
        if kind in ("pitch", "swing", "take"):
            if kind == "pitch":
                if team != self.defense or p["role"] != "P" or s["phase"] != "PITCH_READY" or s["ball"]["holder_id"] != p["id"]:
                    raise ValueError("illegal_pitch_phase_or_holder")
                center = self.config["field"]["defense_q"][0] + ["0"]
                if self.native.sweep_cylinder(p["position_q"]+["0"],p["position_q"]+["0"],center,center,self.config["field"]["base_radius_q"],q(1)) < 0:
                    raise ValueError("pitcher_outside_release_area")
            elif team != self.offense or p["id"] != s["batter_id"] or s["phase"] not in ("PITCH_READY", "PITCH_IN_FLIGHT"):
                raise ValueError("illegal_batter_phase")
            elif kind == "swing" and s["swing_used"]: raise ValueError("swing_already_used")
        elif kind in ("move", "catch", "hold"):
            if team != self.defense or s["phase"] not in ("PLATE_APPEARANCE_SETUP", "PITCH_READY", "PITCH_RESET", "PITCH_IN_FLIGHT", "BALL_IN_PLAY"):
                raise ValueError("illegal_fielding_phase")
        else: raise ValueError("unsupported_action_in_phase")

    def validate_intents(self, team_id, requested):
        if team_id not in ("away", "home"): raise ValueError("unknown_team")
        accepted, results, ids, players = [], [], set(), set()
        schema = self._action_schema
        if type(requested) is not list or len(requested) > 9:
            return {"team_id":team_id,"requested_actions":requested,"accepted_intents":[],"validation_results":[{"status":"rejected","reason":"invalid_batch"}]}
        for action in requested:
            try:
                validate(action, schema)
                pid = action.get("player_id")
                if action["action_id"] in ids or pid in players and pid is not None: raise ValueError("duplicate_action_or_player")
                ids.add(action["action_id"]); players.add(pid)
                self._legal(team_id, action)
                normalized = copy.deepcopy(action)
                if action["kind"] in ("pitch", "throw", "swing"):
                    normalized, _ = self.native.action(action["kind"], action, self.config["physics"])
                if action["kind"] == "move":
                    normalized["target_q"] = self.native.clamp_position(action["target_q"], self.config["field"])
                accepted.append(normalized)
                results.append({"status":"accepted" if normalized == action else "clamped", "action_id":action["action_id"]})
            except (ValueError, KeyError, StopIteration, TypeError, OverflowError) as error:
                results.append({"status":"rejected", "action_id":action.get("action_id") if isinstance(action,dict) else None, "reason":str(error)})
        return {"team_id":team_id,"requested_actions":copy.deepcopy(requested),"accepted_intents":accepted,"validation_results":results}

    def _apply(self, action):
        s = self.state; kind = action["kind"]
        if kind == "noop" or kind == "take": return
        p = self.player(action["player_id"])
        if kind == "pitch":
            _, velocity = self.native.action(kind, action, self.config["physics"])
            s["pitches_total"] += 1; s["pitch_id"] += 1
            s["ball"].update(mode="pitched",holder_id=None,origin="pitch",velocity_q=velocity)
            self._phase("PITCH_IN_FLIGHT"); self._emit("PitchReleased", pitcher_id=p["id"], velocity_q=velocity)
        elif kind == "swing":
            start = s["sim_tick"] + self.config["rules"]["swing_delay_ticks"]
            s["swing_windows"] = {"start_tick":start,"end_tick":start+self.config["rules"]["swing_duration_ticks"],"action":copy.deepcopy(action)}
            s["swing_used"] = True; self._emit("SwingStarted", batter_id=p["id"],start_tick=start)
        elif kind == "move":
            p["active_intents"]["move"] = action["target_q"][:]
            if "catch_enabled" in action: p["active_intents"]["catch"] = action["catch_enabled"]
        elif kind == "catch": p["active_intents"]["catch"] = action["enabled"]
        elif kind == "hold": p["active_intents"].pop("move",None)

    def _move_fielders(self):
        s = self.state
        if s["phase"] in ("HALF_TRANSITION","GAME_OVER","ABORTED"): return
        for p in s["players"]:
            if p["team_id"] != self.defense: continue
            target = p["active_intents"].get("move")
            if target is None and p["velocity_q"] == ["0","0"]: continue
            result = self.native.move(p["position_q"],p["velocity_q"],target or p["position_q"],self.config["physics"],
                                      radius=q(".001"),moving=target is not None)
            p.update(position_q=result["position_q"],velocity_q=result["velocity_q"])
            if result["stopped"]: p["active_intents"].pop("move",None)
        if s["ball"]["holder_id"]:
            s["ball"]["position_q"] = self.player(s["ball"]["holder_id"])["position_q"]+[self.config["physics"]["pitch_height_q"]]

    def adjudicate_fair(self, position, trigger):
        s = self.state; ball = s["ball"]
        if ball["fair_foul_status"] != "undecided": return ball["fair_foul_status"]
        beyond = int(position[1]) >= int(self.config["field"]["bases_q"][1][1])
        final = trigger in ("touch","stop","base","boundary") or beyond
        if not final: return "undecided"
        fair = trigger == "base" or self.native.fair(position,self.config["physics"]["ball_radius_q"])
        ball["fair_foul_status"] = "fair" if fair else "foul"
        self._emit("FairBallDeclared" if fair else "FoulBallDeclared", position_q=position[:])
        return ball["fair_foul_status"]

    def _bat_contact(self):
        s = self.state; ball = s["ball"]
        _, velocity = self.native.action("swing",s["swing_windows"]["action"],self.config["physics"])
        ball.update(mode="batted_airborne",origin="batted",velocity_q=velocity,has_touched_ground_since_bat=False)
        self._phase("BALL_IN_PLAY"); self._emit("BatContact",batter_id=s["batter_id"],velocity_q=velocity)

    def _flight(self):
        s = self.state; ball = s["ball"]; remaining=ONE; elapsed=0; forces=True
        for _ in range(32):
            if ball["mode"] not in ("pitched","batted_airborne","rolling","thrown"): return
            start = ball["position_q"][:]
            result = self.native.advance(start,ball["velocity_q"],self.config,remaining,ball["mode"]=="rolling",forces)
            candidates = []
            window = s["swing_windows"]
            active = window is not None and window["start_tick"] <= s["sim_tick"] < window["end_tick"]
            if ball["origin"] == "pitch":
                if active:
                    hit = self.native.sweep_box(start,result["position_q"],self.config["field"]["bat_box_q"])
                    if hit >= 0: candidates.append((hit,0,"bat"))
                body = self.native.sweep_box(start,result["position_q"],self.config["field"]["body_box_q"],self.config["physics"]["ball_radius_q"])
                if body >= 0: candidates.append((body,1,"body"))
                plane = [q(-1000),q(1000),"0","0",q(-1000),q(1000)]
                if int(start[1]) >= 0 and int(result["position_q"][1]) <= 0:
                    crossing = self.native.sweep_box(start,result["position_q"],plane)
                    if crossing >= 0: candidates.append((crossing,2,"plane"))
            if candidates:
                contact, _, kind = min(candidates)
                consumed = int(self.native.numeric(0,str(result["consumed_q"]),str(contact)))
                ball["position_q"] = self.native.lerp(start,result["position_q"],contact)
                ball["velocity_q"] = result["flight_velocity_q"]
                self._sub = elapsed+consumed
                if kind == "bat":
                    self._bat_contact(); remaining-=consumed; elapsed+=consumed; forces=False
                    if not remaining: return
                    continue
                self._pitch_call(strike=active or (kind=="plane" and self.native.strike(ball["position_q"],self.config)),hbp=kind=="body" and not active)
                return
            ball["position_q"] = result["position_q"]; ball["velocity_q"] = result["velocity_q"]
            self._sub = elapsed+result["consumed_q"]
            if ball["origin"] == "batted" and ball["has_touched_ground_since_bat"] and ball["fair_foul_status"] == "undecided":
                # Decide at the crossing itself; a later sideways roll cannot undo fair.
                base_y = self.config["field"]["bases_q"][1][1]
                if int(start[1]) < int(base_y) <= int(result["position_q"][1]):
                    plane = [q(-1000),q(1000),base_y,base_y,q(-1000),q(1000)]
                    crossing = self.native.sweep_box(start,result["position_q"],plane)
                    if crossing >= 0:
                        self.adjudicate_fair(self.native.lerp(start,result["position_q"],crossing),"boundary")
                for base in (1,3):
                    center = self.config["field"]["bases_q"][base]+["0"]
                    radius = str(int(self.config["field"]["base_radius_q"])+int(self.config["physics"]["ball_radius_q"]))
                    if self.native.sweep_cylinder(start,result["position_q"],center,center,radius,q(".1")) >= 0:
                        self.adjudicate_fair(ball["position_q"],"base")
            if result["event"] == "ground":
                ball["has_touched_ground_since_bat"] = True
                self._emit("GroundContact",position_q=ball["position_q"][:])
                if ball["origin"] == "batted": self.adjudicate_fair(ball["position_q"],"ground")
            elif result["event"] == "wall": self._emit("WallContact",position_q=ball["position_q"][:])
            elif result["event"] == "out":
                if ball["origin"] == "pitch": self._pitch_call()
                else: ball["mode"] = "dead"  # P3 supplies explicit batted-ball awards.
                return
            if result["rolling"]:
                ball["mode"] = "rolling"
                if not any(int(v) for v in ball["velocity_q"]):
                    if ball["origin"] == "pitch": self._pitch_call(); return
                    self.adjudicate_fair(ball["position_q"],"stop")
            if ball["fair_foul_status"] == "foul":
                s["runners"] = copy.deepcopy(s["pitch_start_bases"])
                self._pitch_call(strike=True,foul=True); return
            remaining -= result["consumed_q"]; elapsed += result["consumed_q"]; forces=False
            if not remaining: return
        raise ValueError("physics_contact_limit")

    def step(self, accepted_intents=()):
        self.events = []; self._sub = 0
        if self.state["terminal_status"]:
            return {"sim_tick":self.state["sim_tick"],"events":[],"terminal":True,"checkpoint":False,"phase":self.state["phase"]}
        self._boundary()
        if self.state["terminal_status"]:
            return {"sim_tick":self.state["sim_tick"],"events":self.events,"terminal":True,"checkpoint":True,"phase":self.state["phase"]}
        for batch in sorted(accepted_intents,key=lambda b:b["team_id"]):
            checked = self.validate_intents(batch["team_id"],batch["requested_actions"])
            if checked != batch: raise ValueError("accepted_intent_mismatch")
            for result in batch["validation_results"]:
                self._emit({"accepted":"ActionAccepted","rejected":"ActionRejected","clamped":"ActionClamped"}[result["status"]],team_id=batch["team_id"],**result)
        actions = [(b["team_id"], a) for b in accepted_intents for a in b["accepted_intents"]]
        for _, action in sorted(actions,key=lambda pair:(pair[0],pair[1].get("player_id",""),pair[1]["kind"])): self._apply(action)
        self.state["action_cursor"] += len(accepted_intents)
        self._move_fielders(); self._flight()
        self._sub = 0; self.state["sim_tick"] += 1; self._boundary()
        self.check_invariants()
        checkpoint = self.state["sim_tick"] % 600 == 0 or any(e["type"] == "PlayEnded" for e in self.events) or bool(self.state["terminal_status"])
        return {"sim_tick":self.state["sim_tick"],"events":self.events,"terminal":bool(self.state["terminal_status"]),"checkpoint":checkpoint,"phase":self.state["phase"]}
