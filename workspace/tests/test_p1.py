"""P1 exit suite: native-only physics, geometry, continuous motion and ties."""
import copy
import math
import pytest
import json
from pathlib import Path
from native import Native
from numeric import ONE, q, digest
from configuration import default_config


@pytest.fixture
def native(): return Native()


@pytest.fixture
def config(): return default_config()


def v(*values): return [q(x) for x in values]


def test_free_fall_golden_and_determinism(native, config):
    start, velocity = v(0, 0, 10), v(1, 2, 0)
    expected = None
    for repeat in range(10):
        position, speed = start, velocity
        trace = []
        for _ in range(100):
            segments = native.trace(position, speed, config)
            position, speed = segments[-1]["position_q"], segments[-1]["velocity_q"]
            trace += segments
        if expected is None: expected = digest(trace)
        assert digest(trace) == expected
    golden = json.loads((Path(__file__).parent / "golden/p1.json").read_text())
    assert expected == golden["trajectory_sha256"]
    assert position == golden["position_q"] and speed == golden["velocity_q"]
    step = native.trace(start, velocity, config)[0]
    assert step["velocity_q"][2] == str(-int(config["physics"]["gravity_q"]) // 120 + 1)
    assert step["position_q"][0] == str(ONE // 120)


def test_ground_bounce_and_one_gravity_application(native, config):
    segments = native.trace(v(0, 0, ".04"), v(3, 0, -2), config)
    assert segments[0]["event"] == "ground"
    assert len(segments) == 2
    assert sum(s["consumed_q"] for s in segments) == ONE
    assert int(segments[0]["position_q"][2]) == int(config["physics"]["ball_radius_q"])
    assert segments[1]["velocity_q"] == segments[0]["velocity_q"]
    assert int(segments[1]["velocity_q"][2]) > 0


def test_rolling_stops_exactly(native, config):
    p, speed = v(0, 10, ".037"), v(1, 0, 0)
    for _ in range(120):
        segment = native.trace(p, speed, config, rolling=True)[-1]
        p, speed = segment["position_q"], segment["velocity_q"]
    assert speed == ["0", "0", "0"]
    assert native.trace(p, speed, config, rolling=True)[-1]["position_q"] == p


def test_wall_rebound_home_run_boundary_and_foul_exit(native, config):
    wall = native.trace(v(0, "99.99", 1), v(0, 10, 0), config)
    assert wall[0]["event"] == "wall" and int(wall[0]["velocity_q"][1]) < 0
    over = native.trace(v(0, "99.99", 4), v(0, 10, 0), config)
    assert over[0]["event"] == "out"
    foul = native.trace(v("84.99", 1, 4), v(10, 0, 0), config)
    assert foul[0]["event"] == "out"


def test_swept_bat_box_no_tunneling_and_closed_boundaries(native, config):
    box = config["field"]["bat_box_q"]
    t = native.sweep_box(v(0, 10, 1), v(0, -10, 1), box)
    assert 0 < t < ONE
    assert native.sweep_box(v(".55", 10, 1), v(".55", -10, 1), box) == t
    assert native.sweep_box(v(".55001", 10, 1), v(".55001", -10, 1), box) == -1
    assert native.sweep_box(v(0, 0, 1), v(0, 0, 1), box) == 0
    # Tiny motion must not overflow slab ratios far outside the segment.
    assert native.sweep_box(["1",q(20),q(1)], ["2",q(20),q(1)], box) == -1


def test_relative_moving_glove_and_height(native):
    assert 0 <= native.sweep_cylinder(v(-2,0,1),v(2,0,1),v(0,0,0),v(0,0,0),q(".65"),q("2.5")) < ONE
    assert native.sweep_cylinder(v(-2,0,3),v(2,0,3),v(0,0,0),v(0,0,0),q(".65"),q("2.5")) == -1
    t = native.sweep_cylinder(v(0,0,1),v(0,0,1),v(-2,0,0),v(2,0,0),q(".65"),q("2.5"))
    assert 0 < t < ONE
    # Tangent at an exactly representable instant.
    assert abs(native.sweep_cylinder(v(-2,1,1),v(2,1,1),v(0,0,0),v(0,0,0),q(1),q(2)) - ONE//2) <= 2


def test_multiple_fielders_stable_id_tie(native, config):
    players = [{"id": id, "start_q": v(0,0), "end_q": v(0,0), "catch_enabled": True}
               for id in ["home.P09", "home.P02", "home.P05"]]
    a = native.find_catches(v(-2,0,1),v(2,0,1),players,config["physics"])
    b = native.find_catches(v(-2,0,1),v(2,0,1),players[::-1],config["physics"])
    assert a == b and a[0]["player_id"] == "home.P02"


@pytest.mark.parametrize("target", [("19.398","19.398"),(0,"38.796"),("-19.398","19.398"),(0,0)])
def test_acceleration_speed_and_instant_base_stop(native, config, target):
    dest = v(*target)
    position = [str(int(dest[0])-2*ONE),dest[1]]
    speed = v(0,0)
    for _ in range(500):
        previous = [int(n) for n in speed]
        step = native.move(position,speed,dest,config["physics"],q(".30"))
        position, speed = step["position_q"],step["velocity_q"]
        if step["stopped"]:
            assert speed == ["0","0"]
            assert 0 <= step["touch_q"] <= ONE
            break
        assert math.isqrt(sum((int(a)-b)**2 for a,b in zip(speed,previous))) <= int(q(10))//120+3
        assert math.isqrt(sum(int(a)**2 for a in speed)) <= int(q(7))+3
    else: pytest.fail("runner did not reach base")
    assert math.isqrt(sum((int(a)-int(b))**2 for a,b in zip(position,dest))) <= int(q(".30"))+10


def test_base_pass_through_and_simultaneous_arrival(native, config):
    position, speed, target = v(0,0),v(7,0),v(".3",0)
    a = native.move(position,speed,target,config["physics"],q(".3"),stop_on_touch=False)
    b = native.move(position,speed,target,config["physics"],q(".3"),stop_on_touch=False)
    assert a == b and a["touch_q"] == 0 and a["velocity_q"] != ["0","0"]


def test_action_clamps_zero_direction_and_cordic(native, config):
    action = {"direction_i32":[0,-1000001,0],"power_u16":100000}
    normalized, speed = native.action("pitch",action,config["physics"])
    assert normalized == {"direction_i32":[0,-1000000,0],"power_u16":65535}
    assert speed == v(0,-45,0)
    with pytest.raises(ValueError): native.action("pitch",dict(action,direction_i32=[0,0,0]),config["physics"])
    normalized, speed = native.action("swing",{"power_u16":65535,"azimuth_mdeg":0,"elevation_mdeg":0},config["physics"])
    assert abs(int(speed[0])) < 1000 and abs(int(speed[2])) < 1000
    assert abs(int(speed[1])-int(q(55))) < 1000
    for _ in range(10):
        assert native.action("swing",normalized,config["physics"])[1] == speed


def test_fair_geometry_boundaries_and_numeric_overflow(native):
    assert native.fair(v(10,10)) and native.fair(v(-10,10))
    assert not native.fair(v("10.001",10))
    assert not native.fair(v(0,-1))
    with pytest.raises(ValueError): native.numeric(0,str((1<<63)-1),str((1<<63)-1))
    with pytest.raises(ValueError): native.trace(v(1001,0,1),v(0,0,0),default_config())
