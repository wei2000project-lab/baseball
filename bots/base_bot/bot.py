"""Portable deterministic baseline strategy. No engine or native imports."""
import json
import math
import sys

ONE=1<<32
BASES=[[0,0],[19.398,19.398],[0,38.796],[-19.398,19.398]]


class Bot:
    def __init__(self):self.seed=0;self.team=None;self.receiver=None
    def decide(self,m):
        s=m["state"];team=self.team;defense="home" if s["half"]=="top" else "away";actions=[]
        def make(pid,kind,**kwargs):
            return dict(action_id=f"{team}-{m['decision_id']}-{pid}",player_id=pid,kind=kind,**kwargs)
        def xy(p):return [int(v)/ONE for v in p["position_q"][:2]]
        def move(pid,target):return make(pid,"move",target_q=[str(round(v*ONE)) for v in target],catch_enabled=True)
        players={p["id"]:p for p in s["players"]}
        if team!=defense:
            if s["phase"]=="PITCH_IN_FLIGHT" and not s["swing_used"]:
                b=s["ball"];y=int(b["position_q"][1])/ONE;vy=int(b["velocity_q"][1])/ONE
                eta=(y-.5)/(-vy)*120 if vy<0 else 999
                if 6<=eta<=12:
                    shot=(s["plate_appearance_id"]+self.seed)%6
                    az=[-25000,0,30000,0,15000,-40000][shot]
                    el=[5000,45000,18000,38000,10000,60000][shot]
                    power=[45000,52000,40000,65535,48000,50000][shot]
                    actions.append(make(s["batter_id"],"swing",power_u16=power,azimuth_mdeg=az,elevation_mdeg=el))
                    print(f"swing {s['plate_appearance_id']} shot={shot}",file=sys.stderr,flush=True)
            if s["phase"]=="BALL_IN_PLAY":
                for r in s["runners"]:
                    goal=r["retouch_obligation"] if r["retouch_obligation"] is not None else r["force_obligation"]
                    if goal is None:continue
                    kind="return_to_base" if r["retouch_obligation"] is not None else "run_to_base"
                    direction=-1 if kind=="return_to_base" else 1
                    if r["target_base"]!=goal or r["running_direction"]!=direction:actions.append(make(r["id"],kind,target_base=goal))
            return actions
        if s["phase"]=="PITCH_READY":
            self.receiver=None
            return [make(f"{team}.P01","pitch",direction_i32=[0,-1000000,47000],power_u16=32768)]
        if s["phase"]!="BALL_IN_PLAY":return []
        fielders=[p for p in s["players"] if p["team_id"]==team]
        b=s["ball"];held=b["holder_id"]
        plans={p["id"]:make(p["id"],"catch",enabled=True) for p in fielders if not p["active_intents"].get("catch",False)}
        if held:
            self.receiver=None
            forces=[r for r in s["runners"] if r["force_obligation"] is not None]
            if forces:
                target=min(forces,key=lambda r:(r["force_obligation"],r["id"]))["force_obligation"]
                receiver=f"{team}.P{ {1:3,2:4,3:5,4:2}[target]:02}"
                point=BASES[target%4]
                if receiver==held or math.dist(xy(players[held]),point)<.25:
                    plans[held]=move(held,point)
                    return list(plans.values())
            elif held!=f"{team}.P01":receiver=f"{team}.P01";point=[0,18.44]
            else:return list(plans.values())
            plans[receiver]=move(receiver,point)
            start=xy(players[held]);dx,dy=point[0]-start[0],point[1]-start[1]
            distance=math.hypot(dx,dy)
            if distance<.8:
                plans[held]=move(held,point)
            else:
                dz=.5*9.80665*(distance/40)**2
                scale=1000000/max(abs(dx),abs(dy),abs(dz),1)
                plans[held]=make(held,"throw",direction_i32=[round(v*scale) for v in [dx,dy,dz]],power_u16=65535)
                self.receiver=(receiver,point)
                print(f"throw {held} -> {receiver}",file=sys.stderr,flush=True)
            return list(plans.values())
        position=[int(v)/ONE for v in b["position_q"]];velocity=[int(v)/ONE for v in b["velocity_q"]]
        if b["mode"]=="thrown" and self.receiver and sum(velocity[i]*(self.receiver[1][i]-position[i]) for i in (0,1))>0:
            receiver,point=self.receiver;plans[receiver]=move(receiver,point)
            return list(plans.values())
        self.receiver=None
        if b["mode"]=="rolling":t=.10
        else:t=max(0,(velocity[2]+math.sqrt(max(0,velocity[2]**2+2*9.80665*max(0,position[2]-.5))))/9.80665)
        target=[max(-84,min(84,position[0]+velocity[0]*t)),max(-14,min(104,position[1]+velocity[1]*t))]
        chaser=min(fielders,key=lambda p:(math.dist(xy(p),target),p["id"]))
        plans[chaser["id"]]=move(chaser["id"],target)
        if math.dist(xy(chaser),position[:2])<1.9 and position[2]<2.5 and s["sim_tick"]>=chaser.get("dive_ready_tick",10**9):
            plans[chaser["id"]]=make(chaser["id"],"dive")
        return list(plans.values())


def main():
    bot=Bot()
    for line in sys.stdin:
        m=json.loads(line)
        if m["type"]=="shutdown":break
        if m["type"]=="init":
            bot.seed=int(m["seed"]);bot.team=m["team_id"];reply={"type":"ready","protocol_version":"1.0.0"}
        else:reply={"type":"action","protocol_version":"1.0.0","decision_id":m["decision_id"],"actions":bot.decide(m)}
        print(json.dumps(reply,separators=(",",":")),flush=True)


if __name__=="__main__":main()
