from types import SimpleNamespace
from advancement_metrics import AdvancementMetrics,aggregate
from configuration import default_config
from numeric import q,ONE

CONFIG=default_config()
NATIVE=SimpleNamespace(fair=lambda p,r:int(p[1])+int(r)>=abs(int(p[0])))


def event(kind,**payload):return dict(type=kind,payload=payload)


def collect(events,runners=None,outs=0):
    m=AdvancementMetrics()
    start=event('BatContact',batter_id='b')
    m.feed([start,*events,event('PlayEnded')],dict(runners=runners or {},outs=outs),NATIVE,CONFIG)
    return m


def fair():return event('FairBallDeclared')
def touch(pid,base):return event('BaseTouched',runner_id=pid,base=base)
def out(pid,reason='tag'):return event('RunnerOut',runner_id=pid,reason=reason)
def caught(y,fly=False):return event('BallCaught',origin='batted',position_q=['0',q(y),q(1)],before_first_ground_contact=fly)


def test_actual_surviving_advancement_and_double_play_denominators():
    m=collect([fair(),touch('r',2),touch('b',1)],{'r':1})
    assert m.counts['runner_opportunities']==1 and m.counts['runner_advances']==1
    assert m.counts['batter_first_reached']==1 and m.counts['batter_second_reached']==0
    assert m.counts['double_play_opportunities']==1
    m=collect([fair(),touch('r',2),out('r'),out('b')],{'r':1})
    assert m.counts['runner_advances']==0 and m.counts['double_plays']==1


def test_hr_and_automatic_awards_do_not_inflate_physical_rates():
    m=collect([fair(),event('HomeRun'),event('BaseAwarded',runner_id='r',base=2),touch('r',2)],{'r':1})
    assert m.counts['runner_opportunities']==0
    m=collect([fair(),event('BaseAwarded',runner_id='b',base=1),touch('b',1),event('BaseAwarded',runner_id='b',base=2),touch('b',2)])
    assert m.counts['batter_first_reached']==m.counts['batter_second_reached']==0


def test_infield_grounder_rolling_into_outfield_is_an_outfield_hit():
    m=collect([event('GroundContact',position_q=['0',q(15),q('.037')]),fair(),touch('b',1),caught(60),touch('b',2)])
    assert m.counts['outfield_hits']==1 and m.counts['outfield_extra_base_hits']==1
    m=collect([event('GroundContact',position_q=['0',q(15),q('.037')]),fair(),touch('b',1),caught(35),touch('b',2)])
    assert m.counts['outfield_hits']==0


def test_touching_first_before_a_fly_out_is_not_reaching_first_safely():
    m=collect([touch('b',1),caught(60,True),out('b','flyout')])
    assert m.counts['batter_first_reached']==m.counts['outfield_hits']==0


def test_extra_base_out_and_cancelled_run_are_not_successful_advances():
    m=collect([fair(),touch('b',1),caught(60),touch('b',2),out('b')])
    assert m.counts['batter_first_reached']==1 and m.counts['batter_second_reached']==0
    m=collect([fair(),touch('r',4),event('RunCancelled',runner_id='r')],{'r':3})
    assert m.counts['runner_advances']==0


def test_zero_denominator_is_null_not_a_fake_zero_or_a_pass():
    totals,metrics=aggregate([dict(plate_appearances=6)],2)
    assert metrics['runner_advance_rate'] is None and metrics['outfield_extra_base_rate'] is None
    assert metrics['plate_appearances_per_half']==3 and metrics['plate_appearances_per_game']==6


def test_batter_journey_includes_later_pa_but_excludes_awards_and_new_half():
    from balance_batch import batter_journeys
    first=collect([fair(),touch('b',1)]).ledger[0]
    later=collect([fair(),touch('b',2)],{'b':1}).ledger[0]
    later['batter']='new'
    assert batter_journeys([first,later])==(1,1)
    awarded=collect([fair(),event('BaseAwarded',runner_id='b',base=2),touch('b',2)],{'b':1}).ledger[0]
    awarded['batter']='new'
    assert batter_journeys([first,awarded])==(1,0)
    reset=collect([fair()]).ledger[0];reset['batter']='new'
    assert batter_journeys([first,reset,later])==(1,0)
