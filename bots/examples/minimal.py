"""Protocol-only passive Bot; useful for clock violation scenarios."""
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "shutdown":
        break
    reply = {"protocol_version": "1.0.0"}
    if message["type"] == "init":
        reply["type"] = "ready"
    else:
        reply.update(type="action", decision_id=message["decision_id"], actions=[])
    print(json.dumps(reply), flush=True)
