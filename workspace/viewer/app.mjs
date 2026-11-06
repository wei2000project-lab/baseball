import {meters,clamp,timeLabel,floorIndex,sample,ChunkCache,advanceCursor} from './core.mjs';
import {drawField,drawBases} from './field.mjs';
const $=id=>document.getElementById(id),api=window.baseball;
const PHASE={INIT:'初始化',PLATE_APPEARANCE_SETUP:'打席準備',PITCH_READY:'投球準備',PITCH_IN_FLIGHT:'投球中',PITCH_RESET:'下一球準備',BALL_IN_PLAY:'活球',HALF_TRANSITION:'攻守交換',BALL_RECOVERY:'收球',GAME_OVER:'比賽結束',ABORTED:'比賽中止'};
const MODE={dead:'死球',pitcher_held:'投手持球',pitched:'投球飛行',batted_airborne:'擊球飛行',rolling:'地面滾動',fielder_held:'守備持球',thrown:'傳球飛行'};
const EVENT={GameStarted:'比賽開始',HalfInningStarted:'半局開始',PlateAppearanceStarted:'打席開始',PitchReleased:'投球',SwingStarted:'揮棒',BatContact:'擊中球',GroundContact:'球觸地',WallContact:'撞牆反彈',BallCaught:'接住球',FairBallDeclared:'界內球',FoulBallDeclared:'界外球',HomeRun:'全壘打',BaseAwarded:'授壘',StrikeCalled:'好球',BallCalled:'壞球',PitchClockViolation:'投球逾時',Strikeout:'三振',Walk:'四壞保送',HitByPitch:'觸身球',BaseTouched:'觸壘',RunnerOut:'跑者出局',RunPending:'得分待確認',RunScored:'得分確認',RunCancelled:'得分取消',PlayEnded:'本球結束',RegulationExpired:'時間到，完成目標局',HalfInningCapped:'半局達上限',HalfInningEnded:'半局結束',GameEnded:'比賽結束',GameAborted:'比賽中止',ThrowReleased:'傳球',ReturnCompleted:'回壘完成',AdministrativeBallRecovery:'死球收球',ActionRejected:'動作遭拒絕'};
const REASON={flyout:'接殺',force:'封殺',tag:'觸殺',appeal:'回壘申訴',overtaking:'跑者超越',strikeout:'三振'};
let metadata=null,cache=null,currentFrame=null,playing=false,cursor=0,previousNow=null,exactHash='',seekEpoch=0,recordEpoch=0,profile={},trail=[],hitTargets=[],eventKey='',animationBusy=false,framesDrawn=0,fpsStart=performance.now(),loading=false;
const options={debug:false,offsets:true,scale:1};
function message(text,error=false){$('message').textContent=text;$('message').classList.toggle('error',error);}
function setPlaying(value){playing=value;$('play').textContent=value?'Ⅱ 暫停':'▶ 播放';previousNow=null;if(value)exactHash='';}
function showLoading(value){loading=value;$('loading').classList.toggle('hidden',!value);if(value)setPlaying(false);}
function error(error){setPlaying(false);showLoading(false);metadata=null;cache=null;exactHash='';seekEpoch++;recordEpoch++;message(String(error?.message||error),true);$('verification').textContent='無法驗證';$('verification').className='badge bad';$('seek-state').textContent='未完成驗證';}
function draw(){hitTargets=drawField($('field'),currentFrame,metadata,options,trail,profile);drawBases($('bases'),currentFrame);}
function render(f,exact=false){
  if(!f)return;currentFrame=f;
  $('away-score').textContent=f.score.away;$('home-score').textContent=f.score.home;
  $('inning').textContent=`第 ${f.inning} 局 ${f.half==='top'?'上半':'下半'}`;$('phase').textContent=PHASE[f.phase]||f.phase;
  for(const field of ['outs','balls','strikes'])$(field).textContent=f[field];
  $('clock').textContent=timeLabel(cursor);$('expired').textContent=f.regulation_expired?`時限已到 → 完成第 ${f.finish_after_inning} 局`:'時限內 · 模擬時間';
  $('ball-height').textContent=`${meters(f.ball.position_q[2]).toFixed(2)} m`;$('ball-mode').textContent=MODE[f.ball.mode]||f.ball.mode;
  $('holder').textContent=`持球者：${f.ball.holder_id||'無'}`;$('pending').textContent=`待確認得分：${f.pending_runs.length}`;
  $('fair').textContent=`界內／界外：${{fair:'界內',foul:'界外',undecided:'尚未定案'}[f.ball.fair_foul_status]||'—'}`;
  $('tick-label').textContent=`tick ${Math.floor(cursor)} / ${metadata.total_ticks}`;$('timeline').value=Math.floor(cursor);
  if(document.activeElement!==$('tick-input'))$('tick-input').value=Math.floor(cursor);
  $('seek-state').textContent=exact?`精確狀態 ${exactHash.slice(0,16)} · tick ${f.tick}`:'播放插值 · 暫停後讀取精確狀態';
  $('seek-state').title=exactHash;
  $('runner-count').textContent=`${f.runners.length} 位跑者`;
  $('runner-list').textContent=f.runners.length?f.runners.map(r=>`${r.id} · ${r.last_legal_base===0?'打者':r.last_legal_base+' 壘'}${r.force_obligation?' → 強迫 '+r.force_obligation+' 壘':''}${r.retouch_obligation?' · 欠回壘 '+r.retouch_obligation:''}`).join('\n'):'目前無跑者';
  $('runner-list').style.whiteSpace='pre-line';
  if(playing&&['pitched','batted_airborne','rolling','thrown'].includes(f.ball.mode)){trail.push(f.ball.position_q.map(meters));if(trail.length>70)trail.shift();}else trail=[];
  draw();
}
async function seek(tick){
  if(!metadata||loading)return;setPlaying(false);const epoch=++seekEpoch;
  cursor=clamp(Math.round(tick),0,metadata.total_ticks);$('seek-state').textContent='讀取 TXT 差分…';
  try{const result=await api.seek(cursor);if(epoch!==seekEpoch)return;exactHash=result.state_hash;trail=[];render(result.frame,true);message(`精確定位完成 · ${result.elapsed_ms} ms · ${exactHash}${profile.load_warning?' · '+profile.load_warning:''}`);await updateEvents(cursor);}
  catch(e){if(epoch===seekEpoch)error(e);}
}
async function loaded(data){
  seekEpoch++;recordEpoch++;metadata=data.metadata;cache=new ChunkCache(index=>api.chunk(index),3);cursor=0;exactHash='';eventKey='';showLoading(false);$('empty').classList.add('hidden');
  $('record-name').textContent=data.name;$('timeline').max=metadata.total_ticks;$('tick-input').max=metadata.total_ticks;$('duration').textContent=timeLabel(metadata.total_ticks,false);
  const status=metadata.verification.verification_status;$('verification').textContent=status==='verified_record'?'✓ TXT 完整性驗證通過':'記錄未封存 · 僅可預覽';$('verification').className='badge '+(status==='verified_record'?'good':'warn');
  const innings=$('inning-jump');innings.replaceChildren(new Option('跳至半局',''));
  for(const entry of metadata.navigation.filter(e=>e.type==='HalfInningStarted'))innings.add(new Option(`${entry.payload.inning} 局${entry.payload.half==='top'?'上':'下'}`,String(entry.tick)));
  message(`${metadata.total_frames.toLocaleString()} 影格 · 來源 ${metadata.source_hash.slice(0,16)} · 不執行 Bot`);
  await seek(0);
}
async function nearby(tick){
  const meta=metadata,source=cache;if(!meta||!source)return {frames:[],events:[],index:0};
  const index=Math.max(0,floorIndex(meta.chunks,tick,c=>c.first_tick));
  const chunks=[await source.get(index)];if(index+1<meta.chunks.length)chunks.push(await source.get(index+1));
  return {frames:chunks.flatMap(c=>c.frames),events:chunks.flatMap(c=>c.events),index};
}
async function updateEvents(tick){
  if(!metadata)return;const epoch=recordEpoch,data=await nearby(tick);if(epoch!==recordEpoch)return;
  const visible=data.events.filter(e=>e.sim_tick<=tick+1&&e.type!=='ActionAccepted').slice(-40).reverse();
  const key=visible.map(e=>e.seq).join(',');if(key===eventKey)return;eventKey=key;$('events').replaceChildren();
  if(!visible.length){const p=document.createElement('p');p.className='muted';p.textContent='目前區間尚無事件';$('events').append(p);}
  for(const event of visible){const row=document.createElement('button');row.className='event-row'+(['HomeRun','RunScored','RunnerOut','GameEnded','RegulationExpired'].includes(event.type)?' important':'');
    const t=document.createElement('time');t.textContent=timeLabel(event.sim_tick,false);const text=document.createElement('span');text.textContent=(EVENT[event.type]||event.type)+(event.payload.reason&&REASON[event.payload.reason]?' · '+REASON[event.payload.reason]:'');
    const detail=document.createElement('span');detail.className='event-detail';detail.textContent=event.payload.runner_id||event.payload.fielder_id||event.payload.batter_id||'';text.append(detail);row.append(t,text);
    row.addEventListener('click',()=>{ $('inspector').textContent=JSON.stringify(event,null,2);seek(Math.min(metadata.total_ticks,event.sim_tick+1)); });$('events').append(row);
  }
}
async function animate(now){
  requestAnimationFrame(animate);
  if(!playing||!metadata||animationBusy||loading){previousNow=now;return;}
  if(previousNow===null){previousNow=now;return;}
  const elapsed=Math.min(.25,(now-previousNow)/1000);previousNow=now;cursor=advanceCursor(cursor,elapsed,Number($('speed').value),metadata.total_ticks);
  animationBusy=true;const epoch=recordEpoch;
  try{const data=await nearby(cursor);if(playing&&epoch===recordEpoch){render(sample(data.frames,cursor));framesDrawn++;if(now-fpsStart>1000){$('fps').textContent=`${Math.round(framesDrawn*1000/(now-fpsStart))} FPS`;fpsStart=now;framesDrawn=0;}await updateEvents(cursor);if(metadata&&cursor>=metadata.total_ticks)await seek(metadata.total_ticks);}}
  catch(e){if(epoch===recordEpoch){error(e);setPlaying(false);}}finally{animationBusy=false;}
}
function nextBall(direction){if(!metadata)return;const entries=metadata.navigation.filter(e=>e.type!=='HalfInningStarted').map(e=>({...e,tick:Math.min(metadata.total_ticks,e.tick+1)}));const item=direction>0?entries.find(e=>e.tick>cursor):entries.findLast(e=>e.tick<cursor);if(item)seek(item.tick);}
$('open').onclick=async()=>{try{await api.open();}catch(e){error(e);}};
$('reload').onclick=async()=>{try{await api.reload();}catch(e){error(e);}};
$('cancel').onclick=async()=>{await api.cancel();showLoading(false);metadata=null;cache=null;exactHash='';seekEpoch++;recordEpoch++;$('verification').textContent='已取消 · 尚未驗證';$('verification').className='badge warn';$('seek-state').textContent='未完成驗證';message('已取消讀取；原比賽記錄未變更');};
$('play').onclick=()=>{if(!metadata||loading)return;if(playing)seek(Math.floor(cursor));else if(cursor>=metadata.total_ticks)seek(0);else{setPlaying(true);fpsStart=performance.now();framesDrawn=0;}};
$('step').onclick=()=>seek(Math.floor(cursor)+1);$('step-back').onclick=()=>seek(Math.floor(cursor)-1);
$('previous').onclick=()=>nextBall(-1);$('next').onclick=()=>nextBall(1);
$('timeline').oninput=()=>{setPlaying(false);$('tick-label').textContent=`tick ${$('timeline').value} / ${metadata?.total_ticks||0}`;};
$('timeline').onchange=()=>seek(Number($('timeline').value));$('go').onclick=()=>seek(Number($('tick-input').value));
$('tick-input').onkeydown=e=>{if(e.key==='Enter')seek(Number(e.target.value));};
$('inning-jump').onchange=e=>{if(e.target.value!=='')seek(Number(e.target.value));};
for(const id of ['debug','offsets','scale'])$(id).oninput=()=>{options.debug=$('debug').checked;options.offsets=$('offsets').checked;options.scale=Number($('scale').value);draw();};
$('field').onclick=event=>{const rect=$('field').getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;const target=hitTargets.find(p=>Math.hypot(p.x-x,p.y-y)<18);if(target){const p=currentFrame.players.find(p=>p.id===target.id);$('inspector').textContent=JSON.stringify({...p,position_m:p.position_q.map(meters)},null,2);}};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;if(e.code==='Space'){e.preventDefault();$('play').click();}if(e.code==='ArrowRight')$('step').click();if(e.code==='ArrowLeft')$('step-back').click();});
new ResizeObserver(draw).observe($('field'));
api.onLoaded(data=>loaded(data).catch(error));api.onProgress(data=>{if(!loading){seekEpoch++;recordEpoch++;metadata=null;cache=null;exactHash='';$('verification').textContent='讀取驗證中';$('verification').className='badge';}showLoading(true);$('loading-text').textContent=data.message||`讀取 TXT · ${timeLabel(data.sim_tick,false)} / ${timeLabel(data.total_ticks,false)}`;$('progress').value=data.total_ticks?data.sim_tick/data.total_ticks*100:0;});api.onError(error);
profile=await api.profile();draw();const existing=await api.current();if(existing)await loaded(existing);
requestAnimationFrame(animate);
