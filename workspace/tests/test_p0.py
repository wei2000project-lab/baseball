import copy
import json
import pytest
from baseball_engine import BaseballEngine
from configuration import default_config, validate_config
from numeric import q, canonical, digest, strict_loads, RNG, stream_seed
from native import Native
from contracts import validate_named
from pathlib import Path
import subprocess
import sys


def test_snapshot_restore_and_observe_are_independent():
    engine = BaseballEngine(default_config())
    state = engine.snapshot()
    expected = engine.canonical_state_hash()
    engine.restore(json.loads(canonical(state)))
    assert engine.canonical_state_hash() == expected
    for _ in range(10):
        observation = engine.observe("home")
        observation["score"]["home"] = 99
        assert engine.canonical_state_hash() == expected


@pytest.mark.parametrize("field,value", [("regulation_ticks", -1), ("tick_rate_hz", 60), ("max_ticks", 1), ("max_ticks", True)])
def test_bad_config(field, value):
    config = default_config()
    config["rules"][field] = value
    with pytest.raises(ValueError):
        validate_config(config)


def test_unknown_config_and_bad_physics():
    config = default_config(); config["typo"] = 1
    with pytest.raises(ValueError): validate_config(config)
    config = default_config(); config["physics"]["gravity_q"] = "-1"
    with pytest.raises(ValueError): validate_config(config)


def test_numeric_and_canonical_vectors():
    assert q("0.5") == "2147483648"
    assert q("0.000000000116415321826934814453125") == "0"
    assert canonical({"z": "e\u0301", "a": "\n"}) == b'{"a":"\\u000a","z":"\xc3\xa9"}'
    native = Native()
    assert native.numeric(0, q("-1.5"), q("2")) == q(-3)
    assert native.numeric(1, q(-1), q(3)) == "-1431655765"
    assert native.numeric(2, q(4)) == q(2)
    with pytest.raises(ValueError): native.numeric(1, q(1), "0")
    with pytest.raises(ValueError): strict_loads('{"x":NaN}')
    with pytest.raises(ValueError): strict_loads('{"x":1,"x":2}')


def test_rng_vectors():
    rng = RNG(1)
    assert rng.state == [10451216379200822465, 13757245211066428519, 17911839290282890590, 8196980753821780235]
    assert rng.next() == 12966619160104079557
    assert stream_seed("42", "engine") != stream_seed("42", "setup")


def test_executable_contracts_and_reject_unknown_state():
    validate_named(default_config(), "config")
    engine = BaseballEngine(default_config())
    validate_named(engine.snapshot(), "state")
    snapshot = engine.snapshot(); snapshot["hidden"] = 3
    with pytest.raises(ValueError): engine.restore(snapshot)
    validate_named({"type":"action", "protocol_version":"1.0.0", "decision_id":"d1", "actions":[]}, "action")


def test_minimal_bot_handshake():
    bot = Path(__file__).resolve().parents[2] / "bots/examples/minimal.py"
    requests = [{"type":"init"}, {"type":"observe", "decision_id":"d1"}, {"type":"shutdown"}]
    run = subprocess.run([sys.executable, str(bot)], input="".join(json.dumps(m)+"\n" for m in requests),
                         text=True, capture_output=True, check=True, timeout=5)
    ready, action = map(json.loads, run.stdout.splitlines())
    assert ready == {"type":"ready", "protocol_version":"1.0.0"}
    validate_named(action, "action")
