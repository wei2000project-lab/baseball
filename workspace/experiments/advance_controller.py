"""Frozen test controller, not a production Bot. No target-rate randomization.

Every existing runner attempts one base on a grounded fair play or after legally
retouching a caught fly; a batter tries second on an outfield ground hit. Defense fields normally and contests moving
runners at their destination. All candidates use exactly this same controller.
"""
import math
from bot import Bot as BaseBot,ONE,BASES


class Bot(BaseBot):
    def __init__(self):
        super().__init__();self.config=None;self.play=None;self.origins={};self.outfield=False;self.fly_caught=False

    def decide(self,m):
        s=m["state"];team=self.team;defense="home" if s["half"]=="top" else "away"
        receiver_before=self.receiver
        base=super().decide(m);players={p["id"]:p for p in s["players"]}
        def make(pid,kind,**kw):return dict(action_id=f"fixture-{m['decision_id']}-{pid}",player_id=pid,kind=kind,**kw)
        def xy(p):return [int(v)/ONE for v in p["position_q"]]
        def move(pid,point):return make(pid,"move",target_q=[str(round(v*ONE)) for v in point],catch_enabled=True)
        if team==defense and s["phase"] in ("PLATE_APPEARANCE_SETUP","PITCH_RESET"):
            return [move(f"{team}.P{i+1:02}",[int(v)/ONE for v in point]) for i,point in enumerate(self.config["field"]["defense_q"]) if i>=2]
        if s["phase"]!="BALL_IN_PLAY":return base
        if self.play!=s["play_id"]:
            self.play=s["play_id"];self.origins={r["id"]:r["origin_base"] for r in s["runners"]};self.outfield=False;self.fly_caught=False
        b=s["ball"];pos=[int(v)/ONE for v in b["position_q"]]
        grounded=b["has_touched_ground_since_bat"] and b["fair_foul_status"]=="fair"
        if b["origin"]=="batted" and grounded and math.hypot(*pos[:2])>=45:self.outfield=True
        if b["origin"]=="batted" and b['holder_id'] is not None and not b['has_touched_ground_since_bat']:
            self.fly_caught=True
        if team!=defense:
            actions={a["player_id"]:a for a in base}
            for r in s["runners"]:
                if r["retouch_obligation"] is not None:continue
                origin=self.origins.get(r["id"],r["origin_base"])
                goal=2 if origin==0 and self.outfield else min(4,origin+1) if origin>=1 and (grounded or self.fly_caught) else None
                if goal is not None and goal>r["last_legal_base"] and r["target_base"]!=goal:
                    actions[r["id"]]=make(r["id"],"run_to_base",target_base=goal)
            return list(actions.values())
        held=b["holder_id"]
        if not held:return base
        plans={a["player_id"]:a for a in base if a.get("player_id")!=held}
        holder=players[held];point=xy(holder)
        if holder.get("pending_throw") is not None or s["sim_tick"]<holder.get("catch_recovery_until_tick",0):
            if holder.get('pending_throw') is not None and receiver_before:
                self.receiver=receiver_before
                receiver,dest=receiver_before;plans[receiver]=move(receiver,dest)
            plans[held]=make(held,"hold");return list(plans.values())
        active=[r for r in s["runners"] if r["force_obligation"] is not None or r["target_base"] is not None]
        if not active:
            plans[held]=make(held,"hold");return list(plans.values())
        runner=min(active,key=lambda r:(r["force_obligation"] is None,r["force_obligation"] or r["leg_base"],r["id"]))
        target=runner["force_obligation"] or runner["retouch_obligation"] or runner["leg_base"]
        dest=BASES[target%4]
        if math.dist(point,dest)<.24:
            plans[held]=make(held,"tag",runner_id=runner["id"]) if runner["force_obligation"] is None else make(held,"hold")
            return list(plans.values())
        receiver=f"{team}.P{{:02}}".format({1:3,2:4,3:5,4:2}[max(1,target)])
        fielders=[p for p in s["players"] if p["team_id"]==team and p["id"]!=held]
        if receiver==held:receiver=min(fielders,key=lambda p:(math.dist(xy(p),dest),p["id"]))["id"]
        distance=math.dist(point,dest)
        if distance>60:
            relay=[p for p in fielders if math.dist(xy(p),dest)<distance-10 and math.dist(xy(p),point)<60]
            if relay:
                p=min(relay,key=lambda p:(math.dist(xy(p),dest),p["id"]));receiver=p["id"];dest=xy(p);distance=math.dist(point,dest)
        plans[receiver]=move(receiver,dest)
        if distance<1:
            plans[held]=move(held,dest);return list(plans.values())
        physics=self.config["physics"];speed=int(physics["throw_max_speed_q"])/ONE;g=int(physics["gravity_q"])/ONE
        disc=max(0,speed**4-g*g*distance*distance)
        vz=math.sqrt(max(0,(speed*speed-math.sqrt(disc))/2));horizontal=math.sqrt(max(1,speed*speed-vz*vz))
        desired=[(dest[i]-point[i])/distance*horizontal for i in (0,1)]+[vz+g/240]
        if not self.config["rules"].get("throw_windup_ticks"):
            # Invert the old running-throw inertia, using the same public config.
            drift=[int(v)/ONE*int(physics["throw_running_error_q"])/ONE for v in holder["velocity_q"]]+[0]
            norm=math.sqrt(sum(v*v for v in desired));unit=[v/norm for v in desired];dot=sum(a*b for a,b in zip(unit,drift))
            k=dot+math.sqrt(max(0,speed*speed-sum(v*v for v in drift)+dot*dot));desired=[k*a-b for a,b in zip(unit,drift)]
        scale=1000000/max(abs(v) for v in desired)
        plans[held]=make(held,"throw",direction_i32=[round(v*scale) for v in desired],power_u16=65535)
        self.receiver=(receiver,dest)
        return list(plans.values())
