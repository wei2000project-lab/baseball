"""Refresh embedded config/state/action shapes from the authoritative contracts."""
import copy
import json
from pathlib import Path
from configuration import default_config,VERSION

ROOT=Path(__file__).resolve().parent


def main():
    path=ROOT/"contracts/config.schema.json"
    schema=json.loads(path.read_text(encoding="utf-8"));config=default_config()
    schema["properties"]["version"]={"const":VERSION}
    for group in ("rules","physics","field"):
        shape=schema["properties"][group]
        for key,value in config[group].items():
            if key=="version":shape["properties"][key]={"const":VERSION}
            elif key not in shape["properties"]:
                shape["properties"][key]=({"type":"integer","minimum":0,"maximum":10000000} if type(value)is int
                    else {"type":"string","pattern":"-?(0|[1-9][0-9]*)","maxLength":32})
        shape["required"]=list(config[group])
    path.write_text(json.dumps(schema,indent=2)+"\n",encoding="utf-8")
    state=json.loads((ROOT/"contracts/state.schema.json").read_text(encoding="utf-8"))
    observation=copy.deepcopy(state);observation["properties"].pop("rng_stream_states")
    observation["required"].remove("rng_stream_states")
    actions=json.loads((ROOT/"contracts/action.schema.json").read_text(encoding="utf-8"))
    path=ROOT.parent/"bots/protocol/message.schema.json";message=json.loads(path.read_text(encoding="utf-8"))
    for variant in message["anyOf"]:
        props=variant["properties"];kind=props["type"]["const"]
        if kind=="init":
            caps=props["capabilities"]["properties"]
            for group in ("rules","physics","field"):caps[group+"_config"]=schema["properties"][group]
        elif kind=="observe":props["state"]=observation
        elif kind=="action":props["actions"]=actions["properties"]["actions"]
    path.write_text(json.dumps(message,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":main()
