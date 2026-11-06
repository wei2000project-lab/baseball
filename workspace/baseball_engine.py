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
                "batter_id":None, "swing_used":False, "third_out":None,"throw_start_bases":[],"original_runner_order":[]}

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
        def require(condition,reason):
            if not condition:raise ValueError("invariant:"+reason)
        require(0<=s["outs"]<=3 and s["sim_tick"]>=0,"clock_or_outs")
        require(all(type(v) is int and v>=0 for v in s["score"].values()),"score")
        ids={p["id"] for p in s["players"]}
        require(ids=={f"{t}.P{i:02}" for t in ("away","home") for i in range(1,10)},"roster")
        for p in s["players"]:
            require(all(type(v) is str and abs(int(v))<=1000*ONE for v in p["position_q"]),"player_position")
            require(sum(int(v)**2 for v in p["velocity_q"])<=(int(self.config["physics"]["player_speed_q"])+8)**2,"player_speed")
        b=s["ball"];held=b["mode"] in ("pitcher_held","fielder_held")
        require((b["holder_id"] in ids and b["velocity_q"]==["0"]*3) if held else b["holder_id"] is None,"ball_holder")
        require(all(type(v) is str and abs(int(v))<=1000*ONE for v in b["position_q"]),"ball_position")
        require(sum(int(v)**2 for v in b["velocity_q"])<=(100*ONE)**2,"ball_speed")
        require(len({r["id"] for r in s["runners"]})==len(s["runners"]),"duplicate_runner")
        for r in s["runners"]:
            require(r["id"] in ids and r["alive"] and 0<=r["last_legal_base"]<=4,"runner")
        if s["terminal_status"]=="completed":require(s["completed_halves"]["away"]==s["completed_halves"]["home"],"unfair_terminal")

    def canonical_state_hash(self):
        return digest(self.state)

    def observe(self, team_id):
        if team_id not in ("away", "home"):
            raise ValueError("unknown_team")
        observation=self.snapshot()
        observation.pop("rng_stream_states")
        return observation

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

    def _time(self,sub):
        return [self.state["sim_tick"]+int(sub==ONE),0 if sub==ONE else sub]

    def _phase(self, phase, duration=0):
        s = self.state
        start=s["sim_tick"]+int(getattr(self,"_sub",0)>0)
        s["phase"] = phase; s["phase_start_tick"] = start
        s["phase_deadline_tick"] = start + duration

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
        s.update(third_out=None,throw_start_bases=[],original_runner_order=[],settle_counter=0,recovery_counter=0)
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
        s["balls"]=s["strikes"]=0;s["ball"]["velocity_q"]=["0"]*3
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
                "force_obligation":None, "retouch_obligation":None, "alive":True, "touched_bases":[base],
                "leg_base":min(4,base+1),"running_direction":1,"initial_order":0,"has_first":base>=1}

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
        elif kind == "hold" and team==self.offense and s["phase"]=="BALL_IN_PLAY" and any(r["id"]==p["id"] for r in s["runners"]):
            return
        elif kind in ("move", "catch", "hold"):
            if team != self.defense or s["phase"] not in ("PLATE_APPEARANCE_SETUP", "PITCH_READY", "PITCH_RESET", "PITCH_IN_FLIGHT", "BALL_IN_PLAY"):
                raise ValueError("illegal_fielding_phase")
        elif kind in ("run_to_base","return_to_base"):
            runner=next((r for r in s["runners"] if r["id"]==p["id"]),None)
            if team!=self.offense or s["phase"]!="BALL_IN_PLAY" or runner is None:raise ValueError("illegal_runner")
            if kind=="run_to_base" and action["target_base"]<=runner["last_legal_base"]:raise ValueError("non_forward_target")
            if kind=="return_to_base" and (runner["retouch_obligation"] is None or action["target_base"]!=runner["retouch_obligation"]):raise ValueError("invalid_return_obligation")
        elif kind in ("throw","tag","appeal_return"):
            if team!=self.defense or s["phase"]!="BALL_IN_PLAY" or s["ball"]["holder_id"]!=p["id"]:raise ValueError("illegal_holder_action")
            if kind in ("tag","appeal_return") and not any(r["id"]==action["runner_id"] for r in s["runners"]):raise ValueError("unknown_runner")
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
        if kind in ("run_to_base","return_to_base","hold") and p["team_id"]==self.offense:
            r=next(r for r in s["runners"] if r["id"]==p["id"])
            if kind=="hold":r["target_base"]=None
            else:
                direction=-1 if kind=="return_to_base" else 1
                center=self.config["field"]["bases_q"][r["last_legal_base"]%4]+["0"]
                at=p["position_q"]+["0"]
                on_base=self.native.sweep_cylinder(at,at,center,center,self.config["field"]["base_radius_q"],q(1))>=0
                if r["target_base"] is None and on_base:
                    r["leg_base"]=max(1,min(4,r["last_legal_base"]+direction))
                elif r["running_direction"]!=direction:
                    r["leg_base"]=max(0,r["leg_base"]-1) if direction<0 else min(4,r["leg_base"]+1)
                r["running_direction"]=direction;r["target_base"]=action["target_base"]
            s["settle_counter"]=s["recovery_counter"]=0
        elif kind=="throw":
            _,velocity=self.native.action(kind,action,self.config["physics"])
            s["throw_start_bases"]=[{"id":r["id"],"base":r["last_legal_base"]} for r in s["runners"]]
            s["ball"].update(mode="thrown",holder_id=None,origin="throw",velocity_q=velocity,
                             position_q=p["position_q"]+[self.config["physics"]["throw_height_q"]])
            p["active_intents"].pop("tag",None);p["active_intents"].pop("appeal_return",None)
            p["active_intents"]["catch"]=False
            s["settle_counter"]=s["recovery_counter"]=0
            self._emit("ThrowReleased",fielder_id=p["id"],velocity_q=velocity)
        elif kind in ("tag","appeal_return"):p["active_intents"][kind]=action["runner_id"]

    def _move_fielders(self):
        s = self.state
        self._motions={p["id"]:{"start":p["position_q"][:],"end":p["position_q"][:],"stop":None} for p in s["players"]}
        self._arrivals=[];self._competition_time=0
        self._holder_since=0 if s["ball"]["holder_id"] else None
        if s["phase"] in ("HALF_TRANSITION","GAME_OVER","ABORTED"): return
        for p in s["players"]:
            if p["team_id"] != self.defense: continue
            target = p["active_intents"].get("move")
            if target is None and p["velocity_q"] == ["0","0"]: continue
            result = self.native.move(p["position_q"],p["velocity_q"],target or p["position_q"],self.config["physics"],
                                      radius=q(".001"),moving=target is not None)
            p.update(position_q=result["position_q"],velocity_q=result["velocity_q"])
            self._motions[p["id"]].update(end=p["position_q"][:],stop=result["touch_q"] if result["stopped"] else None)
            if result["stopped"]: p["active_intents"].pop("move",None)
        if s["ball"]["holder_id"]:
            s["ball"]["position_q"] = self.player(s["ball"]["holder_id"])["position_q"]+[self.config["physics"]["pitch_height_q"]]
        if s["phase"]=="BALL_IN_PLAY":self._move_runners()

    def _at(self,player_id,time):
        motion=self._motions[player_id];stop=motion["stop"]
        if stop is not None:
            if time>=stop:return motion["end"][:]
            time=int(self.native.numeric(1,str(time),str(stop)))
        return self.native.lerp(motion["start"]+["0"],motion["end"]+["0"],time)[:2]

    def _move_runners(self):
        for r in self.state["runners"]:
            p=self.player(r["id"]);target=r["target_base"]
            if target is None and p["velocity_q"]==["0","0"]:continue
            base=r["leg_base"]
            center=self.config["field"]["bases_q"][base%4]
            stop=target==base
            move=self.native.move(p["position_q"],p["velocity_q"],center,self.config["physics"],
                                  self.config["field"]["base_radius_q"],moving=target is not None,stop_on_touch=stop)
            p.update(position_q=move["position_q"],velocity_q=move["velocity_q"])
            self._motions[p["id"]].update(end=p["position_q"][:],stop=move["touch_q"] if move["stopped"] else None)
            if target is not None and move["touch_q"]>=0:self._arrivals.append((move["touch_q"],r["id"],base))

    def _touching(self,player_id,base,time=ONE):
        center=self.config["field"]["bases_q"][base%4]+["0"]
        at=self._at(player_id,time)+["0"]
        return self.native.sweep_cylinder(at,at,center,center,self.config["field"]["base_radius_q"],q(1))>=0

    def _safe(self,r,time=ONE):
        if not r["last_legal_base"] or r["last_legal_base"]>=4 or r["force_obligation"] is not None or r["retouch_obligation"] is not None:return False
        if not self._touching(r["id"],r["last_legal_base"],time):return False
        owners=[other for other in self.state["runners"] if other["last_legal_base"]==r["last_legal_base"] and self._touching(other["id"],other["last_legal_base"],time)]
        return not any(other["initial_order"]<r["initial_order"] for other in owners)

    def _arrival(self,runner_id,base,time):
        s=self.state;r=next((r for r in s["runners"] if r["id"]==runner_id),None)
        if r is None:return
        r["last_legal_base"]=base;r["touched_bases"].append(base)
        if base==1:r["has_first"]=True
        if r["force_obligation"]==base:r["force_obligation"]=None
        if r["retouch_obligation"]==base:
            r["retouch_obligation"]=None;self._emit("ReturnCompleted",runner_id=runner_id,base=base)
        self._emit("BaseTouched",runner_id=runner_id,base=base)
        if r["target_base"]==base:r["target_base"]=None
        else:r["leg_base"]=base+r["running_direction"]
        if base==4 and r["retouch_obligation"] is None:
            s["pending_runs"].append({"runner_id":runner_id,"time":self._time(time),"order":r["initial_order"]})
            self._emit("RunPending",runner_id=runner_id);s["runners"].remove(r)

    def _runner_out(self,runner_id,reason,time,is_force=False):
        s=self.state;r=next((r for r in s["runners"] if r["id"]==runner_id),None)
        if r is None or s["outs"]>=3:return
        before_first=runner_id==s["batter_id"] and not r["has_first"]
        s["runners"].remove(r);s["outs"]+=1
        self._emit("RunnerOut",runner_id=runner_id,reason=reason,is_force=is_force,batter_before_first=before_first,base=r["last_legal_base"])
        for force in s["force_state"]:
            if runner_id in force["depends_on"]:
                other=next((x for x in s["runners"] if x["id"]==force["runner_id"]),None)
                if other:other["force_obligation"]=None
        if reason=="appeal":s["pending_appeals"].append({"runner_id":runner_id,"order":r["initial_order"]})
        if s["outs"]==3:s["third_out"]={"time":self._time(time),"is_force":is_force,"batter_before_first":before_first}

    def _holder_candidates(self,until):
        s=self.state;holder=s["ball"]["holder_id"]
        if holder is None:return []
        begin=max(self._competition_time,self._holder_since or 0)
        if begin>until:return []
        candidates=[];hp=self.player(holder)
        for r in s["runners"]:
            base=r["force_obligation"]
            appeal=hp["active_intents"].get("appeal_return")==r["id"] and r["retouch_obligation"] is not None
            if appeal:base=r["retouch_obligation"]
            if base is not None:
                center=self.config["field"]["bases_q"][base%4]+["0"]
                t=self.native.sweep_cylinder(self._at(holder,begin)+["0"],self._at(holder,until)+["0"],center,center,self.config["field"]["base_radius_q"],q(1))
                if t>=0:
                    at=begin+int(self.native.numeric(0,str(until-begin),str(t)))
                    candidates.append((at,1,"appeal" if appeal else "force",r["id"]))
            if hp["active_intents"].get("tag")==r["id"]:
                t=self.native.sweep_cylinder(self._at(holder,begin)+["0"],self._at(holder,until)+["0"],self._at(r["id"],begin)+["0"],self._at(r["id"],until)+["0"],self.config["physics"]["tag_radius_q"],q(1))
                if t>=0:
                    at=begin+int(self.native.numeric(0,str(until-begin),str(t)))
                    if self._safe(r,at) and not self._safe(r,until):
                        lo,hi=at,until
                        while lo+1<hi:
                            mid=(lo+hi)//2
                            if self._safe(r,mid):lo=mid
                            else:hi=mid
                        at=hi
                        # A glove may have left contact before the runner left safety.
                        hpos=self._at(holder,at)+["0"];rpos=self._at(r["id"],at)+["0"]
                        if self.native.sweep_cylinder(hpos,hpos,rpos,rpos,self.config["physics"]["tag_radius_q"],q(1))<0:continue
                    candidates.append((at,1,"tag",r["id"]))
        return candidates

    def _competition(self,until):
        points={until}
        points.update(m["stop"] for m in self._motions.values() if m["stop"] is not None and self._competition_time<m["stop"]<until)
        points.update(t for t,_,_ in self._arrivals if self._competition_time<t<until)
        for point in sorted(points):self._competition_segment(point)

    def _competition_segment(self,until):
        s=self.state
        if s["phase"]!="BALL_IN_PLAY" or s["outs"]>=3:return
        candidates=[(t,0,"arrival",(pid,base)) for t,pid,base in self._arrivals if self._competition_time<=t<=until]
        candidates+=self._holder_candidates(until)
        ordered=sorted(s["runners"],key=lambda r:r["initial_order"])
        def progress(r,time):
            base=r["leg_base"]-1 if r["running_direction"]>0 else r["leg_base"]
            base=max(0,min(3,base));field=self.config["field"]["bases_q"]
            return base*ONE+self.native.progress(self._at(r["id"],time),field[base],field[(base+1)%4])
        for front,back in zip(ordered,ordered[1:]):
            a=progress(front,self._competition_time)-progress(back,self._competition_time)
            b=progress(front,until)-progress(back,until)
            if b<0:
                ratio=int(self.native.numeric(1,str(a),str(a-b))) if a>=0 else 0
                t=self._competition_time if a<0 else self._competition_time+int(self.native.numeric(0,str(until-self._competition_time),str(ratio)))+1
                candidates.append((min(until,t),1,"overtaking",back["id"]))
        for time,priority,kind,data in sorted(candidates,key=lambda c:(c[0],c[1],str(c[3]))):
            if s["outs"]>=3:break
            self._sub=time
            if kind=="arrival":
                self._arrival(data[0],data[1],time)
                self._arrivals=[a for a in self._arrivals if not (a[0]==time and a[1]==data[0])]
            else:
                r=next((r for r in s["runners"] if r["id"]==data),None)
                if r is None:continue
                if kind=="force" and r["force_obligation"] is None:continue
                if kind=="appeal" and r["retouch_obligation"] is None:continue
                if kind=="tag" and self._safe(r,time):continue
                self._runner_out(data,kind,time,kind=="force")
        self._competition_time=until

    def _finish_play(self):
        s=self.state;third=s["third_out"]
        for run in sorted(s["pending_runs"],key=lambda r:(r["time"],r["order"])):
            reason=None
            if third and (third["is_force"] or third["batter_before_first"]):reason="third_out_force_or_batter"
            elif third and run["time"]>=third["time"]:reason="not_before_third_out"
            elif any(a["order"]<=run["order"] for a in s["pending_appeals"]):reason="preceding_return_appeal"
            elif s["half_runs"]>=self.config["rules"]["half_run_cap"]:reason="half_inning_cap"
            if reason:self._emit("RunCancelled",runner_id=run["runner_id"],reason=reason)
            else:self._run_scored(run["runner_id"])
        s["pending_runs"]=[];s["pending_appeals"]=[]
        self._finish_pa()

    def _caught(self,fielder_id,time):
        s=self.state;ball=s["ball"]
        fly=ball["origin"]=="batted" and not ball["has_touched_ground_since_bat"]
        self._emit("BallCaught",fielder_id=fielder_id,origin=ball["origin"],before_first_ground_contact=fly)
        ball.update(mode="fielder_held",holder_id=fielder_id,velocity_q=["0"]*3)
        self._holder_since=time
        if fly:
            self._runner_out(s["batter_id"],"flyout",time)
            s["force_state"]=[]
            for r in s["runners"]:
                r["force_obligation"]=None
                r["retouch_obligation"]=None if self._touching(r["id"],r["origin_base"],time) else r["origin_base"]
        elif ball["origin"]=="batted" and self.adjudicate_fair(ball["position_q"],"touch")=="foul":self._foul()

    def _foul(self):
        s=self.state;s["runners"]=copy.deepcopy(s["pitch_start_bases"])
        s.update(pending_runs=[],pending_appeals=[],force_state=[])
        for r in s["runners"]:self.player(r["id"]).update(position_q=self.config["field"]["bases_q"][r["last_legal_base"]%4][:],velocity_q=["0","0"])
        self._pitch_call(strike=True,foul=True)

    def _award(self,amount,reason,starting=None):
        s=self.state
        origins=starting or [{"id":r["id"],"base":r["origin_base"]} for r in s["runners"]]
        for origin in sorted(origins,key=lambda r:(-r["base"],r["id"])):
            r=next((r for r in s["runners"] if r["id"]==origin["id"]),None)
            if r is None:continue
            dest=min(4,origin["base"]+amount)
            for base in range(origin["base"]+1,dest+1):
                self._emit("BaseAwarded",runner_id=r["id"],base=base,reason=reason)
                r["last_legal_base"]=base;r["touched_bases"].append(base)
                self._emit("BaseTouched",runner_id=r["id"],base=base)
            r.update(force_obligation=None,retouch_obligation=None,target_base=None,leg_base=min(4,dest+1))
            self.player(r["id"]).update(position_q=self.config["field"]["bases_q"][dest%4][:],velocity_q=["0","0"])
            if dest==4:
                s["pending_runs"].append({"runner_id":r["id"],"time":self._time(self._sub),"order":r["initial_order"]})
                self._emit("RunPending",runner_id=r["id"]);s["runners"].remove(r)
        self._finish_play()

    def _out_of_play(self):
        s=self.state;b=s["ball"]
        if b["origin"]=="throw":self._award(2,"throw_out",s["throw_start_bases"])
        elif b["origin"]=="batted":
            if b["has_touched_ground_since_bat"] and b["fair_foul_status"]=="fair":self._award(2,"ground_rule_double")
            elif not self.native.fair(b["position_q"],self.config["physics"]["ball_radius_q"]):
                self.adjudicate_fair(b["position_q"],"stop");self._foul()
            elif not b["has_touched_ground_since_bat"]:
                self._emit("HomeRun",batter_id=s["batter_id"]);self._award(4,"home_run")
            else:self._award(2,"ground_rule_double")
        else:self._pitch_call()

    def _settle(self):
        s=self.state
        if s["phase"]!="BALL_IN_PLAY":return
        if s["outs"]>=3:self._finish_play();return
        stopped=all(r["target_base"] is None and self.player(r["id"])["velocity_q"]==["0","0"] and self._safe(r) for r in s["runners"])
        held=s["ball"]["holder_id"] is not None
        s["settle_counter"]=s["settle_counter"]+1 if stopped and held else 0
        static=not any(int(v) for v in s["ball"]["velocity_q"])
        s["recovery_counter"]=s["recovery_counter"]+1 if stopped and static and not held else 0
        if s["settle_counter"]>=self.config["rules"]["settle_ticks"]:self._finish_play()
        elif s["recovery_counter"]>=self.config["rules"]["loose_ball_recovery_ticks"]:
            self._phase("BALL_RECOVERY");self._emit("AdministrativeBallRecovery");self._finish_play()

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
        ordered=sorted(s["runners"],key=lambda r:(-r["last_legal_base"],r["id"]))
        for i,r in enumerate(ordered):
            r["origin_base"]=r["last_legal_base"];r["initial_order"]=i;r["force_obligation"]=None
            r["retouch_obligation"]=None;r["leg_base"]=min(4,r["last_legal_base"]+1);r["running_direction"]=1
        batter=self._new_runner(s["batter_id"],0);batter["initial_order"]=len(ordered)
        s["runners"].append(batter);s["original_runner_order"]=[r["id"] for r in ordered]+[batter["id"]]
        by_base={r["origin_base"]:r for r in s["runners"]}
        dependencies=[];s["force_state"]=[]
        for base in (0,1,2,3):
            if base not in by_base:break
            r=by_base[base];r["force_obligation"]=base+1
            s["force_state"].append({"runner_id":r["id"],"target_base":base+1,"depends_on":dependencies[:]})
            dependencies.append(r["id"])
        self._phase("BALL_IN_PLAY"); self._emit("BatContact",batter_id=s["batter_id"],velocity_q=velocity)

    def _flight(self):
        s = self.state; ball = s["ball"]; remaining=ONE; elapsed=0; forces=True
        contacts=0
        for _ in range(64):
            if ball["mode"] not in ("pitched","batted_airborne","rolling","thrown"): return
            start = ball["position_q"][:]
            result = self.native.advance(start,ball["velocity_q"],self.config,remaining,ball["mode"]=="rolling",forces)
            # Split at a fielder's hard stop so relative sweeps remain piecewise linear.
            stops=[m["stop"] for m in self._motions.values() if m["stop"] is not None and elapsed<m["stop"]<elapsed+result["consumed_q"]]
            if stops:
                duration=min(stops)-elapsed
                local=int(self.native.numeric(1,str(duration),str(result["consumed_q"])))
                result.update(position_q=self.native.lerp(start,result["position_q"],local),velocity_q=result["flight_velocity_q"],
                              consumed_q=duration,event=None,rolling=ball["mode"]=="rolling")
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
            if s["phase"]=="BALL_IN_PLAY":
                if ball["origin"]=="batted" and ball["has_touched_ground_since_bat"] and ball["fair_foul_status"]=="undecided":
                    by=self.config["field"]["bases_q"][1][1]
                    if int(start[1])<int(by)<=int(result["position_q"][1]):
                        plane=[q(-1000),q(1000),by,by,q(-1000),q(1000)]
                        time=self.native.sweep_box(start,result["position_q"],plane)
                        if time>=0:candidates.append((time,-1,"fair_boundary"))
                    for base in (1,3):
                        center=self.config["field"]["bases_q"][base]+["0"]
                        radius=str(int(self.config["field"]["base_radius_q"])+int(self.config["physics"]["ball_radius_q"]))
                        time=self.native.sweep_cylinder(start,result["position_q"],center,center,radius,q(".1"))
                        if time>=0:candidates.append((time,-1,"fair_base"))
                fielders=[{"id":p["id"],"start_q":self._at(p["id"],elapsed),"end_q":self._at(p["id"],elapsed+result["consumed_q"]),
                           "catch_enabled":p["active_intents"].get("catch",False)} for p in s["players"] if p["team_id"]==self.defense]
                for catch in self.native.find_catches(start,result["position_q"],fielders,self.config["physics"]):
                    if catch["sub_tick_q"]==ONE and result["event"] in ("ground","out"):continue
                    candidates.append((catch["sub_tick_q"],3,"catch",catch["player_id"]))
            if candidates:
                selected=min(candidates);contact,_,kind=selected[:3]
                consumed = int(self.native.numeric(0,str(result["consumed_q"]),str(contact)))
                ball["position_q"] = self.native.lerp(start,result["position_q"],contact)
                ball["velocity_q"] = result["flight_velocity_q"]
                self._sub = elapsed+consumed
                self._competition(self._sub);self._sub=elapsed+consumed
                if s["outs"]>=3:return
                if kind == "bat":
                    self._bat_contact(); remaining-=consumed; elapsed+=consumed; forces=False
                    if not remaining: return
                    continue
                if kind=="catch":self._caught(selected[3],self._sub);return
                if kind in ("fair_boundary","fair_base"):
                    self.adjudicate_fair(ball["position_q"],"boundary" if kind=="fair_boundary" else "base")
                    if ball["fair_foul_status"]=="foul":self._foul();return
                    remaining-=consumed;elapsed+=consumed;forces=False
                    if not remaining:return
                    continue
                self._pitch_call(strike=active or (kind=="plane" and self.native.strike(ball["position_q"],self.config)),hbp=kind=="body" and not active)
                return
            ball["position_q"] = result["position_q"]; ball["velocity_q"] = result["velocity_q"]
            self._sub = elapsed+result["consumed_q"]
            self._competition(self._sub);self._sub=elapsed+result["consumed_q"]
            if s["outs"]>=3:return
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
                self._out_of_play();return
            if result["event"]:
                contacts+=1
                if contacts>32:raise ValueError("physics_contact_limit")
            if result["rolling"]:
                ball["mode"] = "rolling"
                if not any(int(v) for v in ball["velocity_q"]):
                    if ball["origin"] == "pitch": self._pitch_call(); return
                    self.adjudicate_fair(ball["position_q"],"stop")
            if ball["fair_foul_status"] == "foul":
                self._foul();return
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
        self._move_fielders(); self._flight();self._competition(ONE)
        self._sub=ONE
        if self.state["phase"]=="BALL_IN_PLAY" and self.state["ball"]["holder_id"]:
            self.state["ball"]["position_q"]=self.player(self.state["ball"]["holder_id"])["position_q"]+[self.config["physics"]["throw_height_q"]]
        self._settle()
        self._sub = 0; self.state["sim_tick"] += 1; self._boundary()
        self.check_invariants()
        checkpoint = self.state["sim_tick"] % 600 == 0 or any(e["type"] == "PlayEnded" for e in self.events) or bool(self.state["terminal_status"])
        return {"sim_tick":self.state["sim_tick"],"events":self.events,"terminal":bool(self.state["terminal_status"]),"checkpoint":checkpoint,"phase":self.state["phase"]}
