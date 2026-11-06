'use strict';
// Only enabled by the trusted CLI --background-test switch. Never shows a window.
const fs=require('node:fs/promises');
const assert=require('node:assert/strict');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
exports.run=async({window,loadDirectory,getMetadata,root})=>{
  const index=process.argv.indexOf('--acceptance-config');
  if(index<0)throw new Error('Missing acceptance config');
  const config=JSON.parse(await fs.readFile(process.argv[index+1],'utf8'));
  const report={passed:false,mode:'invisible offscreen Electron; no desktop input or focus',checks:[],screenshot:config.screenshot};
  const js=code=>window.webContents.executeJavaScript(code,true);
  async function waitFor(code,label,timeout=20000){const start=Date.now();while(Date.now()-start<timeout){if(await js(code))return;await delay(25);}throw new Error('Timeout: '+label);}
  function passed(name,details={}){report.checks.push({name,...details});console.log('PASS '+name);}
  const snapshot=()=>js(`({tick:Number(document.getElementById('timeline').value),hash:document.getElementById('seek-state').title,away:Number(document.getElementById('away-score').textContent),home:Number(document.getElementById('home-score').textContent),outs:Number(document.getElementById('outs').textContent),height:parseFloat(document.getElementById('ball-height').textContent)})`);
  async function verifyTick(tick){
    await waitFor(`document.getElementById('seek-state').textContent.includes('· tick ${tick}')`,'exact tick '+tick);
    const actual=await snapshot(),expected=config.expected[String(tick)];assert.ok(expected,'reference missing tick '+tick);
    assert.equal(actual.hash,expected.state_hash);assert.equal(actual.away,expected.score.away);assert.equal(actual.home,expected.score.home);assert.equal(actual.outs,expected.outs);assert.equal(actual.height,expected.height_m);return actual;
  }
  async function seek(tick){await js(`document.getElementById('tick-input').value=${tick};document.getElementById('go').click()`);return verifyTick(tick);}
  try{
    assert.equal(window.isVisible(),false);
    window.webContents.setFrameRate(60);
    await waitFor(`Boolean(window.baseball)`,'preload');
    await loadDirectory(config.record);await verifyTick(0);
    report.source_hash=getMetadata().source_hash;
    assert.match(await js(`document.getElementById('verification').textContent`),/整場重算驗證通過/);
    passed('full replay verified and rendered');
    assert.deepEqual(await js(`[typeof window.require,typeof window.process]`),['undefined','undefined']);
    assert.equal(await js(`window.baseball.chunk('../manifest.json').then(()=>false,()=>true)`),true);
    passed('renderer has no Node; IPC rejects path-shaped chunk indexes');
    await seek(1000);await js(`document.getElementById('step').click()`);await verifyTick(1001);
    await js(`document.getElementById('step-back').click()`);await verifyTick(1000);passed('single tick forward and backward');
    await js(`document.getElementById('next').click()`);await waitFor(`document.getElementById('seek-state').textContent.includes('精確狀態')&&Number(document.getElementById('timeline').value)>1000`,'next pitch');
    const next=await snapshot();await verifyTick(next.tick);
    await js(`document.getElementById('previous').click()`);await waitFor(`document.getElementById('seek-state').textContent.includes('精確狀態')&&Number(document.getElementById('timeline').value)<${next.tick}`,'previous pitch');
    await verifyTick((await snapshot()).tick);passed('previous and next pitch navigation');
    const phases=getMetadata().navigation.filter(e=>e.type==='HalfInningStarted');
    if(phases.length>1){const tick=phases[1].tick;await js(`document.getElementById('inning-jump').value='${tick}';document.getElementById('inning-jump').dispatchEvent(new Event('change'))`);await verifyTick(tick);assert.match(await js(`document.getElementById('inning').textContent`),/下半/);passed('half-inning jump and scoreboard');}
    await seek(1000);
    for(const speed of ['.25','8']){
      await js(`document.getElementById('speed').value='${speed}';document.getElementById('play').click()`);
      await waitFor(`Number(document.getElementById('timeline').value)>1003`,'play '+speed);
      await delay(speed==='8'?1400:250);
      const fps=await js(`document.getElementById('fps').textContent`);
      await js(`document.getElementById('play').click()`);await waitFor(`document.getElementById('seek-state').textContent.includes('精確狀態')`,'pause exact');
      const paused=await snapshot();await seek(1000);passed('speed '+speed+' pauses and returns to identical state',{paused_tick:paused.tick,fps});
    }
    const before=(await snapshot()).hash;
    await js(`document.getElementById('offsets').click();document.getElementById('debug').click();document.getElementById('scale').value='2';document.getElementById('scale').dispatchEvent(new Event('input'))`);
    assert.equal((await snapshot()).hash,before);passed('offset, debug and scale leave authoritative hash unchanged');
    for(const [kind,tick] of Object.entries(config.selected)){await seek(tick);passed('state synchronization: '+kind,{tick});}
    if(config.selected.GroundContact){await seek(config.selected.GroundContact);await waitFor(`Array.from(document.querySelectorAll('.event-row')).some(e=>e.textContent.includes('球觸地'))`,'ground event');await js(`Array.from(document.querySelectorAll('.event-row')).find(e=>e.textContent.includes('球觸地')).click()`);await waitFor(`document.getElementById('inspector').textContent.includes('GroundContact')`,'event inspector');passed('event click and exact logical payload');}
    await seek(config.preview_tick);
    // Capture our invisible render buffer, not the user's screen.
    await delay(150);const image=await window.webContents.capturePage();await fs.writeFile(config.screenshot,image.toPNG());
    assert.deepEqual(image.getSize(),{width:1920,height:1080});
    passed('1920 x 1080 offscreen visual artifact',{size:image.getSize()});
    await seek(getMetadata().total_ticks);assert.equal((await snapshot()).hash,getMetadata().verification.summary.final_state_hash);passed('terminal state matches verified summary');
    await loadDirectory(config.audit_record);await waitFor(`document.getElementById('seek-state').textContent.includes('· tick 0')`,'audit record');
    await waitFor(`Array.from(document.querySelectorAll('.event-row')).some(e=>e.textContent.includes('動作遭拒絕'))`,'audit event');
    await js(`Array.from(document.querySelectorAll('.event-row')).find(e=>e.textContent.includes('動作遭拒絕')).click()`);
    await waitFor(`document.getElementById('inspector').textContent.includes('<svg')`,'literal hostile text');
    assert.equal(await js(`typeof window.__recordInjection`),'undefined');assert.equal(await js(`document.getElementById('inspector').querySelector('svg')===null`),true);passed('record HTML remains inert text');
    const loading=loadDirectory(config.record).then(()=>({loaded:true}),error=>({cancelled:error.message}));
    await waitFor(`!document.getElementById('loading').classList.contains('hidden')`,'cancel overlay');await js(`document.getElementById('cancel').click()`);
    assert.ok((await loading).cancelled);await waitFor(`document.getElementById('verification').textContent.includes('已取消')`,'cancel badge');passed('cancellation stops worker and clears verification claim');
    report.passed=true;
  }catch(error){report.error=error.stack;try{await fs.writeFile(config.screenshot.replace('.png','-failure.png'),(await window.webContents.capturePage()).toPNG());}catch{}throw error;}
  finally{await fs.writeFile(config.report,JSON.stringify(report,null,2)+'\n');}
};
