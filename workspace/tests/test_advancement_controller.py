"""Benchmark fixture correctness; these policies are never installed as real Bots."""
import balance_batch  # supplies the baseline Bot import path
from experiments.advance_controller import Bot,BASES
from numeric import q
from test_p3 import batted_engine,holder


def controller(e,team):
    bot=Bot();bot.team=team;bot.config=e.config
    return bot


def decide(bot,e):return bot.decide(dict(state=e.observe(bot.team),decision_id=str(e.state['sim_tick'])))


def test_tag_up_requires_retouch_before_attempting_one_base():
    e=batted_engine((1,));holder(e,base=3);s=e.state;r=s['runners'][0]
    s['runners']=[r];r.update(force_obligation=None,retouch_obligation=1,last_legal_base=1,target_base=None)
    s['ball'].update(has_touched_ground_since_bat=False)
    bot=controller(e,'away');actions=decide(bot,e)
    assert any(a['kind']=='return_to_base' and a['target_base']==1 for a in actions)
    assert not any(a['kind']=='run_to_base' for a in actions)
    r['retouch_obligation']=None;r['target_base']=None
    actions=decide(bot,e)
    assert any(a['kind']=='run_to_base' and a['target_base']==2 for a in actions)


def test_pending_throw_keeps_receiver_at_the_accepted_destination():
    e=batted_engine((1,));holder(e,base=3);p=e.player('home.P03')
    p['pending_throw']=dict(action={},running_velocity_q=['0','0']);p['throw_release_tick']=e.state['sim_tick']+27
    bot=controller(e,'home');bot.receiver=('home.P04',BASES[2])
    actions=decide(bot,e)
    receiver=next(a for a in actions if a['player_id']=='home.P04')
    assert receiver['kind']=='move' and receiver['target_q']==[q(v) for v in BASES[2]]
    assert bot.receiver==('home.P04',BASES[2])
    assert next(a for a in actions if a['player_id']==p['id'])['kind']=='hold'
