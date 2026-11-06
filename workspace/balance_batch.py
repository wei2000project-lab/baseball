"""Reproducible in-process baseline-Bot matches (same simultaneous decision API)."""
import argparse
from contextlib import redirect_stderr
import hashlib
import json
from pathlib import Path
import sys
import time

from baseball_engine import BaseballEngine
from configuration import default_config
from numeric import stream_seed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bots/base_bot"))
from bot import Bot


def simulate(seed, config, bot_class=Bot):
    engine = BaseballEngine(config, str(seed))
    bots = {team: bot_class() for team in ("away", "home")}
    for team, bot in bots.items():
        bot.team = team
        bot.seed = stream_seed(str(seed), "bot:" + team)
    counts = dict(contacts=0, fair_balls=0, home_runs=0, fair_outs=0,
                  hits=0, safe_reaches=0, reaches_on_error=0, fouls=0, fielding_errors=0, caps=0)
    play = None
    last_phase = None
    while not engine.terminal_result():
        s = engine.state
        batches = []
        if s["sim_tick"] % config["rules"]["decision_interval_ticks"] == 0 or s["phase"] != last_phase:
            last_phase = s["phase"]
            observations = {team: engine.observe(team) for team in bots}
            for team, bot in bots.items():
                requested = bot.decide(dict(state=observations[team], decision_id=str(s["sim_tick"])))
                batches.append(engine.validate_intents(team, requested))
        result = engine.step(batches)
        for event in result["events"]:
            kind, p = event["type"], event["payload"]
            if kind == "BatContact":
                counts["contacts"] += 1
                play = dict(batter=p["batter_id"], fair=False, out=False, safe=False, hr=False, error=False, fly_fair=None)
            if kind == "HalfInningCapped": counts["caps"] += 1
            if kind == "FieldingError": counts["fielding_errors"] += 1
            if play is None: continue
            if kind == "FieldingError" and not play["safe"]:play["error"] = True
            if kind == "BallCaught" and p.get("before_first_ground_contact") and "position_q" in p:
                play["fly_fair"] = engine.native.fair(p["position_q"],config["physics"]["ball_radius_q"])
            if kind in ("FairBallDeclared", "HomeRun"):
                play["fair"] = True
            if kind == "HomeRun": play["hr"] = True
            if kind == "RunnerOut" and p["runner_id"] == play["batter"]:
                play["out"] = True
                # P7 fly catches did not emit a fair declaration. Its baseline
                # Bot only bats inside +/-40 degrees (all fair). V2 supplies position.
                if p["reason"] == "flyout": play["fair"] = play["fly_fair"] is not False
            if kind in ("BaseTouched", "BaseAwarded") and p["runner_id"] == play["batter"] and p["base"] >= 1:
                play["safe"] = True
            if kind == "StrikeCalled" and p.get("foul"):
                counts["fouls"] += 1
                play = None
            elif kind == "PlayEnded":
                if play["fair"]:
                    counts["fair_balls"] += 1
                    counts["home_runs"] += play["hr"]
                    counts["fair_outs"] += play["out"]
                    safe=play["safe"] and not play["out"]
                    counts["safe_reaches"] += safe
                    counts["hits"] += safe and not play["error"]
                    counts["reaches_on_error"] += safe and play["error"]
                play = None
    result = engine.terminal_result()
    return dict(seed=seed, **counts, **{k: result[k] for k in ("status", "score", "completed_halves", "sim_tick", "reason")})


def report(games, config, label):
    completed = [g for g in games if g["status"] == "completed"]
    fair = sum(g["fair_balls"] for g in completed)
    halves = sum(sum(g["completed_halves"].values()) for g in completed)
    return dict(label=label, seeds=[g["seed"] for g in games], n=len(games), completed=len(completed),
        config=config, bot_sha256=hashlib.sha256((ROOT / "bots/base_bot/bot.py").read_bytes()).hexdigest(),
        measurement="in_process; same Bot observations, validation, simultaneous batches; no IPC/record I/O",
        denominators="HR/fair BIP; batter retired/fair BIP; safe >=1 base without batter out or prior fielding error/fair BIP (includes HR); runs/completed halves; ticks/completed games. Error before first safe base is scored ROE, not hit.",
        totals={k: sum(g[k] for g in completed) for k in ("contacts", "fair_balls", "home_runs", "fair_outs", "hits", "safe_reaches", "reaches_on_error", "fouls", "fielding_errors", "caps")},
        metrics=dict(home_run_rate=sum(g["home_runs"] for g in completed)/max(fair,1),
            fair_out_rate=sum(g["fair_outs"] for g in completed)/max(fair,1),
            hit_rate=sum(g["hits"] for g in completed)/max(fair,1),
            runs_per_half=sum(sum(g["score"].values()) for g in completed)/max(halves,1),
            ticks_per_game=sum(g["sim_tick"] for g in completed)/max(len(completed),1)), games=games)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument("--regulation-ticks", type=int, default=1200)
    p.add_argument("--label", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--config")
    p.add_argument("--combine", nargs="+", help="combine completed cohorts with identical configs and disjoint seeds")
    p.add_argument("--check-targets", action="store_true")
    args = p.parse_args()
    if args.n < 1: p.error("--n must be positive")
    if args.combine:
        sources=[json.loads(Path(name).read_text(encoding="utf-8")) for name in args.combine]
        config=sources[0]["config"]
        if any(source["config"]!=config for source in sources):p.error("combined configs differ")
        games=[dict(game) for source in sources for game in source["games"]]
        if len({game["seed"] for game in games})!=len(games):p.error("combined seeds overlap")
        for game in games:
            game.setdefault("safe_reaches",game["hits"]);game.setdefault("reaches_on_error",0)
        result=report(games,config,args.label)
        result["source_reports"]=args.combine
        result["source_fingerprints"]=[{k:source.get(k) for k in ("engine_build_id","native_build_id","bot_sha256")} for source in sources]
        result["bot_sha256"]=sources[0]["bot_sha256"] if all(s.get("bot_sha256")==sources[0]["bot_sha256"] for s in sources) else None
        result["measurement"]="Aggregate of recorded simulation cohorts; no new matches or seed selection"
        return save_report(result,args)
    config = json.loads(Path(args.config).read_text()) if args.config else default_config()
    config["rules"]["regulation_ticks"] = args.regulation_ticks
    games = []
    from recording import source_hash
    fingerprints=dict(engine_build_id=source_hash(),native_build_id=source_hash(native=True),
                      bot_sha256=hashlib.sha256((ROOT / "bots/base_bot/bot.py").read_bytes()).hexdigest())
    start = time.perf_counter()
    with open("NUL" if sys.platform == "win32" else "/dev/null", "w") as sink, redirect_stderr(sink):
        for seed in range(args.seed_start, args.seed_start + args.n):
            game = simulate(seed, config)
            games.append(game)
            print(f"{args.label} seed={seed} {game['status']} {game['score']} ticks={game['sim_tick']}", flush=True)
    result = report(games, config, args.label)
    result.update(fingerprints)
    result["wall_seconds"] = round(time.perf_counter() - start, 3)
    return save_report(result,args)


def save_report(result,args):
    result["targets"]={"home_run_rate":[.05,.10],"fair_out_rate":[.65,.75],"runs_per_half":[.5,2]}
    result["target_checks"]={k:lo<=result["metrics"][k]<=hi for k,(lo,hi) in result["targets"].items()}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], indent=2))
    if result["n"]!=result["completed"]:return 1
    return 2 if args.check_targets and not all(result["target_checks"].values()) else 0


if __name__ == "__main__": sys.exit(main())
