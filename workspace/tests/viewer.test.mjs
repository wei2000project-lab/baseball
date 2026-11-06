import test from 'node:test';
import assert from 'node:assert/strict';
import {Q,timeLabel,floorIndex,sample,ChunkCache,visualPosition,advanceCursor} from '../viewer/core.mjs';
import profileValidation from '../viewer/profile.cjs';
import fs from 'node:fs';
const make=(tick,x,cut=false)=>({tick,cut,inning:1,half:'top',phase:'BALL_IN_PLAY',score:{away:0,home:0},ball:{mode:'batted_airborne',holder_id:null,position_q:[String(x*Q),'0',String(Q)]},players:[{id:'away.P01',position_q:['0','0']}]});
test('binary search includes exact ticks and chunk boundaries',()=>{
  assert.equal(floorIndex([{tick:0},{tick:4},{tick:8}],4),1);
  assert.equal(floorIndex([{tick:0},{tick:4},{tick:8}],3),0);
  assert.equal(floorIndex([{tick:2}],0),-1);
});
test('interpolation preserves authority and never crosses contact cuts',()=>{
  const a=make(0,0),b=make(4,4),before=JSON.stringify([a,b]);
  assert.equal(sample([a,b],2).ball.position_q[0],String(2*Q));
  assert.equal(JSON.stringify([a,b]),before);
  b.cut=true;assert.equal(sample([a,b],3).ball.position_q[0],'0');
  assert.equal(sample([a,b],4).ball.position_q[0],String(4*Q));
  b.cut=false;b.ball.mode='fielder_held';b.ball.holder_id='home.P01';
  assert.equal(sample([a,b],3).ball.position_q[0],'0');
});
test('quarter and eight speed and frame rates reach the same logical tick',()=>{
  let quarter=0,eight=0,lowerFps=0;
  for(let i=0;i<480;i++)quarter=advanceCursor(quarter,1/120,.25,1000);
  for(let i=0;i<15;i++)eight=advanceCursor(eight,1/120,8,1000);
  for(let i=0;i<120;i++)lowerFps=advanceCursor(lowerFps,1/30,.25,1000);
  assert.equal(quarter,120);assert.equal(eight,120);assert.equal(lowerFps,120);
  assert.equal(advanceCursor(999,1,8,1000),1000);
  assert.equal(timeLabel(120),'00:01.000');assert.equal(timeLabel(108000,false),'15:00');
});
test('visual offsets and origin corrections never mutate logical positions',()=>{
  const p={role:'P',position_q:[String(Q),String(2*Q)]},profile={role_offsets:{P:[3,-1]},visual_offset_local:[1,1,0],model_origin_correction:[2,0,0]};
  assert.deepEqual(visualPosition(p,profile,true),[7,2]);
  assert.deepEqual(visualPosition(p,profile,false),[1,2]);
  assert.deepEqual(p.position_q,[String(Q),String(2*Q)]);
});
test('LRU keeps at most three chunks and coalesces concurrent requests',async()=>{
  let calls=0;const cache=new ChunkCache(async index=>{calls++;return {index};},3);
  assert.deepEqual(await Promise.all([cache.get(0),cache.get(0)]),[{index:0},{index:0}]);assert.equal(calls,1);
  for(let i=1;i<20;i++)await cache.get(i);
  assert.equal(cache.cache.size,3);assert.equal(cache.pending.size,0);
});
test('delivered visual profile accepts finite offsets and stays independent',()=>{
  const raw=JSON.parse(fs.readFileSync(new URL('../../model/visual_profiles/default.json',import.meta.url),'utf8'));
  const value=profileValidation.validateProfile(raw);assert.equal(value.visual_profile_id,'primitive-v1');
  value.model_scale=4;assert.equal(raw.model_scale,1);
});
test('invalid visual transforms and unknown fields fail closed',()=>{
  const raw=structuredClone(profileValidation.DEFAULT_PROFILE);
  for(const invalid of [{...raw,model_scale:NaN},{...raw,model_scale:Infinity},{...raw,visual_offset_local:[0,0]},{...raw,typo:1}])assert.throws(()=>profileValidation.validateProfile(invalid));
});
