from configuration import validate_config
from scan_advancement import checks,loss,candidates,config_for,TARGETS


def valid_report():
    return dict(n=40,completed=40,metrics=dict(runs_per_half=2,runner_advance_rate=.425,
        outfield_extra_base_rate=.6,double_play_rate=.05))


def test_selection_requires_every_metric_and_rejects_zero_denominators():
    r=valid_report();assert all(checks(r).values())
    for key in TARGETS:
        bad=valid_report();bad['metrics'][key]=None
        assert not all(checks(bad).values()) and loss(bad)>loss(r)
    bad=valid_report();bad['completed']=39
    assert loss(bad)>100


def test_fixed_multidimensional_grid_produces_valid_configs():
    first=candidates(32)
    assert first==candidates(32) and len({tuple(p.values()) for p in first})==32
    for p in first:validate_config(config_for(p))


def test_resume_cache_rejects_changed_sources_seeds_or_config(tmp_path):
    import json
    import pytest
    from scan_advancement import evaluate
    class NoSimulation:
        def submit(self,*args):raise AssertionError('cache miss')
    params=candidates(1)[0];config=config_for(params)
    path=tmp_path/'c000/screen.json';path.parent.mkdir()
    cached=dict(search_identity='frozen',seeds=[0],config=config)
    path.write_text(json.dumps(cached))
    assert evaluate(NoSimulation(),[('c000',params)],range(1),'screen',tmp_path,'frozen',{})['c000']==cached
    for key,value in (('search_identity','changed'),('seeds',[1]),('config',{})):
        path.write_text(json.dumps(dict(cached,**{key:value})))
        with pytest.raises(AssertionError,match='cache miss'):
            evaluate(NoSimulation(),[('c000',params)],range(1),'screen',tmp_path,'frozen',{})
