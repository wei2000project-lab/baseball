"""Physical advancement accounting; automatic awards cannot inflate run metrics."""
from numeric import ONE

FIELDS=("plate_appearances","runner_opportunities","runner_advances","runner_attempts",
        "batter_first_reached","batter_second_reached","batter_second_attempts",
        "outfield_hits","outfield_extra_base_hits","outfield_runner_opportunities","outfield_runner_advances",
        "double_play_opportunities","double_plays","non_hr_fair_plays")


class AdvancementMetrics:
    def __init__(self):self.counts=dict.fromkeys(FIELDS,0);self.play=None;self.ledger=[]

    @staticmethod
    def before(state):
        b=state["ball"]
        distance=sum(int(v)**2 for v in b["position_q"][:2]) if b["origin"]=="batted" and b["has_touched_ground_since_bat"] else None
        return dict(runners={r["id"]:r["last_legal_base"] for r in state["runners"]},outs=state["outs"],ground_distance_squared=distance)

    def requests(self,batches):
        if not self.play:return
        for batch in batches:
            for a in batch["accepted_intents"]:
                if a["kind"]=="run_to_base":
                    self.play["attempts"][a["player_id"]]=max(a["target_base"],self.play["attempts"].get(a["player_id"],0))

    def feed(self,events,before,native,config):
        if self.play and not self.play["controlled"] and before.get("ground_distance_squared") is not None:
            self.play["outfield"] |= before["ground_distance_squared"] >= (45*ONE)**2
        for event in events:
            kind,p=event["type"],event["payload"]
            if kind=="PlayEnded":self.counts["plate_appearances"]+=1
            if kind=="BatContact":
                self.play=dict(batter=p["batter_id"],origins=dict(before["runners"]),outs_before=before["outs"],
                    fair=False,hr=False,outfield=False,ground_seen=False,first=False,error=False,
                    touched={},awards=set(),outs=set(),scored=set(),cancelled=set(),attempts={},flyout=False,controlled=False)
            x=self.play
            if x is None:continue
            if kind in ("FairBallDeclared","HomeRun"):x["fair"]=True
            if kind=="HomeRun":x["hr"]=True
            if kind=="BallCaught" and p.get("before_first_ground_contact"):
                x["fair"]=native.fair(p["position_q"],config["physics"]["ball_radius_q"])
            if kind=="BallCaught" and p.get("origin")=="batted":
                if not p.get("before_first_ground_contact"):
                    a,b=map(int,p["position_q"][:2]);x["outfield"] |= a*a+b*b>=(45*ONE)**2
                x["controlled"]=True
            if kind=="GroundContact" and not x["controlled"]:
                x["ground_seen"]=True
                a,b=map(int,p["position_q"][:2]);x["outfield"] |= a*a+b*b>=(45*ONE)**2
            if kind=="FieldingError" and not x["first"]:x["error"]=True
            if kind=="BaseAwarded":x["awards"].add((p["runner_id"],p["base"]))
            if kind=="BaseTouched" and (p["runner_id"],p["base"]) not in x["awards"]:
                pid=p["runner_id"];x["touched"][pid]=max(x["touched"].get(pid,0),p["base"])
                if pid==x["batter"] and p["base"]==1:x["first"]=True
            if kind=="RunnerOut":
                x["outs"].add(p["runner_id"])
                if p["runner_id"]==x["batter"] and p["reason"]=="flyout":x["flyout"]=True
            if kind=="RunScored":x["scored"].add(p["runner_id"])
            if kind=="RunCancelled":x["cancelled"].add(p["runner_id"])
            if kind=="StrikeCalled" and p.get("foul"):self.play=None
            elif kind=="PlayEnded":self.finish();self.play=None

    def finish(self):
        x=self.play;c=self.counts
        self.ledger.append({k:sorted(v) if isinstance(v,set) else v for k,v in x.items()})
        if not x["fair"] or x["hr"]:return
        c["non_hr_fair_plays"]+=1
        survivors=lambda pid:pid not in x["outs"] and pid not in x["cancelled"]
        advance=lambda pid,base:survivors(pid) and x["touched"].get(pid,base)>base
        origins={p:b for p,b in x["origins"].items() if 1<=b<=3}
        c["runner_opportunities"]+=len(origins)
        c["runner_advances"]+=sum(advance(pid,base) for pid,base in origins.items())
        c["runner_attempts"]+=sum(x["attempts"].get(pid,base)>base for pid,base in origins.items())
        if x["outs_before"]<=1 and origins:
            c["double_play_opportunities"]+=1;c["double_plays"]+=len(x["outs"])>=2
        if x["first"] and not x["flyout"]:
            c["batter_first_reached"]+=1
            c["batter_second_reached"]+=advance(x["batter"],1)
            c["batter_second_attempts"]+=x["attempts"].get(x["batter"],1)>=2
            if x["outfield"] and not x["error"]:
                c["outfield_hits"]+=1;c["outfield_extra_base_hits"]+=advance(x["batter"],1)
                c["outfield_runner_opportunities"]+=len(origins)
                c["outfield_runner_advances"]+=sum(advance(pid,base) for pid,base in origins.items())


def aggregate(games,halves):
    totals={key:sum(g.get(key,0) for g in games) for key in FIELDS}
    def ratio(a,b):return totals[a]/totals[b] if totals[b] else None
    metrics=dict(runner_advance_rate=ratio("runner_advances","runner_opportunities"),
        batter_extra_base_rate=ratio("batter_second_reached","batter_first_reached"),
        outfield_extra_base_rate=ratio("outfield_extra_base_hits","outfield_hits"),
        outfield_runner_advance_rate=ratio("outfield_runner_advances","outfield_runner_opportunities"),
        double_play_rate=ratio("double_plays","double_play_opportunities"),
        double_plays_per_fair_play=ratio("double_plays","non_hr_fair_plays"),
        runner_attempt_rate=ratio("runner_attempts","runner_opportunities"),
        plate_appearances_per_half=totals["plate_appearances"]/halves if halves else None,
        plate_appearances_per_game=totals["plate_appearances"]/len(games) if games else None)
    return totals,metrics
