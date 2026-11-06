"""Explicit maintenance command; tests never rewrite their golden expectations."""
import json
from pathlib import Path
from native import Native
from configuration import default_config,VERSION
from numeric import q,ONE,digest


def main():
    n=Native();c=default_config();root=Path(__file__).resolve().parent/'tests/golden'
    position=[q(x) for x in (0,0,10)];velocity=[q(x) for x in (1,2,0)];trace=[]
    for _ in range(100):
        parts=n.trace(position,velocity,c);trace+=parts
        position,velocity=parts[-1]['position_q'],parts[-1]['velocity_q']
    (root/'p1.json').write_text(json.dumps(dict(platform='Windows x64 / Zig 0.13.0',physics_version=VERSION,
        trajectory_sha256=digest(trace),position_q=position,velocity_q=velocity),indent=2)+'\n')
    contacts=[]
    for power in (20000,45000,65535):
        for timing in (2,4,6,8):
            v,quality=n.contact(dict(power_u16=power,azimuth_mdeg=0,elevation_mdeg=38000),
                ['0',q('.75'),q('.875')],timing*ONE,12*ONE,c)
            contacts.append([v,int(quality)])
    skills=[];p=c['physics']
    for speed in (0,4,9):
        for ball in ([q(-35),'0','0'],['0',q(40),'0']):
            skills.append(n.field_skill(0,[q(speed),'0'],ball,p))
            skills.append(n.field_skill(1,[q(speed),'0'],ball,p))
    pitches=[]
    for power in (0,32768,65535):
        _,v=n.action('pitch',dict(power_u16=power,direction_i32=[0,-1000000,47000]),p)
        for phase in range(1,7):pitches.append(list(n.pitch_scatter(v,q('18.44'),phase,p)))
    roll=[];position=['0',q(10),q('.037')];velocity=[q(12),'0','0']
    for _ in range(400):
        parts=n.trace(position,velocity,c,rolling=True);roll+=parts
        position,velocity=parts[-1]['position_q'],parts[-1]['velocity_q']
    movement=[];position=['0',q(20)];velocity=['0','0']
    for _ in range(600):
        result=n.move(position,velocity,[q(10),q(50)],p,q('.001'),field=c['field']);movement.append(result)
        position,velocity=result['position_q'],result['velocity_q']
    (root/'balance-v2.json').write_text(json.dumps(dict(physics_version=VERSION,config_hash=digest(c),
        contact_trace_sha256=digest(contacts),contacts=contacts,skills=skills,pitches=pitches,
        skill_trace_sha256=digest(skills),pitch_trace_sha256=digest(pitches),
        rolling_trace_sha256=digest(roll),fielder_trace_sha256=digest(movement)),indent=2)+'\n')
    print('Regenerated p1 + balance-v2 native traces')


if __name__=='__main__':main()
