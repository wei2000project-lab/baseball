import {meters,clamp,visualPosition} from './core.mjs';
export function drawField(canvas,frame,metadata,options,trail,profile) {
  const width=canvas.clientWidth,height=canvas.clientHeight,dpr=window.devicePixelRatio||1;
  if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);}
  const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,width,height);
  const scale=Math.min(width/187,height/130),home=[width/2,height-38];
  const point=(x,y,z=0)=>[home[0]+x*scale,home[1]-y*scale-z*scale*.8];
  const path=(pts,close=false)=>{c.beginPath();pts.forEach((p,i)=>{const a=point(...p);i?c.lineTo(...a):c.moveTo(...a);});if(close)c.closePath();};
  const circle=(x,y,r,color,fill=true)=>{c.beginPath();c.arc(x,y,r,0,Math.PI*2);fill?(c.fillStyle=color,c.fill()):(c.strokeStyle=color,c.stroke());};
  const arc=[];for(let i=-45;i<=45;i++)arc.push([100*Math.sin(i*Math.PI/180),100*Math.cos(i*Math.PI/180)]);
  path([[0,0],...arc],true);c.fillStyle='#174831';c.fill();
  for(let radius=20;radius<100;radius+=10){const pts=[];for(let i=-45;i<=45;i++)pts.push([radius*Math.sin(i*Math.PI/180),radius*Math.cos(i*Math.PI/180)]);path(pts);c.strokeStyle=radius%20===0?'#25573a':'#1b4c33';c.lineWidth=8*scale;c.globalAlpha=.35;c.stroke();c.globalAlpha=1;}
  path([[0,-3],[-24,18],[-19,30],[0,42],[19,30],[24,18]],true);c.fillStyle='#5b5438';c.globalAlpha=.78;c.fill();c.globalAlpha=1;
  const bases=metadata?.field?.bases_q?.map(v=>v.map(meters))||[[0,0],[19.398,19.398],[0,38.796],[-19.398,19.398]];
  path(bases,true);c.strokeStyle='#c6c29c';c.lineWidth=1;c.stroke();
  for(const end of [arc[0],arc.at(-1)]){path([[0,0],end]);c.strokeStyle='#dce0c9';c.lineWidth=1.3;c.stroke();}
  path(arc);c.strokeStyle='#8baf82';c.lineWidth=3;c.stroke();
  c.font='10px Consolas';c.fillStyle='#739378';c.textAlign='center';c.fillText('100 m',...point(0,102));
  const mound=point(0,18.44);circle(...mound,2*scale,'#8a7950');
  for(let i=0;i<4;i++){const p=point(...bases[i]);c.save();c.translate(...p);c.rotate(Math.PI/4);c.fillStyle='#f1e9ce';const r=Math.max(2,scale*.3);c.fillRect(-r,-r,r*2,r*2);c.restore();}
  if(options.debug){
    c.setLineDash([3,4]);path([[-85,-15],[-85,105],[85,105],[85,-15]],true);c.strokeStyle='#416e5b';c.lineWidth=1;c.stroke();c.setLineDash([]);
    for(const b of bases)circle(...point(...b),Math.max(1,scale*.3),'#c5e1a3',false);
    const a=point(-.55,.75),b=point(.55,-.3);c.strokeStyle='#ffe19b';c.strokeRect(a[0],a[1],b[0]-a[0],b[1]-a[1]);
  }
  const hitTargets=[];
  if(!frame)return hitTargets;
  const defense=frame.half==='top'?'home':'away',runners=new Set(frame.runners.map(r=>r.id));
  const visible=frame.players.filter(p=>p.team_id===defense||p.id===frame.batter_id||runners.has(p.id));
  for(const p of visible){
    const logical=point(...p.position_q.map(meters)),slot=runners.has(p.id)?'runner':p.id===frame.batter_id&&p.team_id!==defense?'batter':p.role;
    const display=point(...visualPosition(p,profile,options.offsets,slot));
    const color=p.team_id==='away'?'#ffc46b':'#64cee2';
    const size=6*clamp(options.scale*(Number(profile?.model_scale)||1),.3,4);
    if(options.debug){circle(...logical,Math.max(1.5,.65*scale),'#709e89',false);circle(...logical,1.5,'#d6e3cc');path([]);c.beginPath();c.moveTo(...logical);c.lineTo(...display);c.strokeStyle='#688f7c';c.stroke();}
    circle(display[0]+1,display[1]+2,size+2,'#00170e88');circle(...display,size,color);
    if(p.id===frame.ball.holder_id)circle(...display,size+4,'#ecf5b8',false);
    c.font='9px Consolas';c.textAlign='center';c.fillStyle='#e5ebd9';c.shadowColor='#05160d';c.shadowBlur=4;c.fillText(`${p.id.slice(-3)} · ${slot==='batter'?'打者':slot==='runner'?'跑者':p.role}`,display[0],display[1]-size-5);c.shadowBlur=0;
    hitTargets.push({id:p.id,x:display[0],y:display[1]});
  }
  if(trail.length>1){c.beginPath();trail.forEach((v,i)=>{const p=point(...v);i?c.lineTo(...p):c.moveTo(...p);});c.strokeStyle='#eddfaa55';c.lineWidth=1.2;c.stroke();}
  const pos=frame.ball.position_q.map(meters),shadow=point(pos[0],pos[1]),air=point(...pos);air[1]=Math.max(23,air[1]);
  circle(...shadow,Math.max(3,5-pos[2]/30),'#00150dc9');circle(...shadow,4,'#c9d6a95c',false);
  if(pos[2]>.4){c.beginPath();c.moveTo(...shadow);c.lineTo(...air);c.setLineDash([3,4]);c.strokeStyle='#dfdeaa75';c.lineWidth=1;c.stroke();c.setLineDash([]);}
  circle(...air,4,'#fff8d5');circle(...air,6,'#fff8d550',false);
  if(options.debug){
    const x=20,y=height-172,w=104,h=145;
    c.fillStyle='#08241ddf';c.fillRect(x,y,w,h);c.strokeStyle='#315b47';c.strokeRect(x,y,w,h);
    c.fillStyle='#7da28a';c.font='9px sans-serif';c.textAlign='center';c.fillText('本壘斷面 / X–Z',x+w/2,y+14);
    const cross=(vx,vz)=>[x+w/2+vx*55,y+h-18-vz*43];
    let a=cross(-.216,1.1),b=cross(.216,.5);c.fillStyle='#a7d99722';c.fillRect(...a,b[0]-a[0],b[1]-a[1]);c.strokeStyle='#b3d697';c.strokeRect(...a,b[0]-a[0],b[1]-a[1]);
    a=cross(-.55,1.5);b=cross(.55,.25);c.setLineDash([2,3]);c.strokeStyle='#e0c382';c.strokeRect(...a,b[0]-a[0],b[1]-a[1]);c.setLineDash([]);
    if(Math.abs(pos[1])<3&&Math.abs(pos[0])<.9&&pos[2]<2.6)circle(...cross(pos[0],pos[2]),3,'#fff3bb');
  }
  return hitTargets;
}

export function drawBases(canvas,frame){
  const c=canvas.getContext('2d');c.clearRect(0,0,canvas.width,canvas.height);
  const points=[[71,97],[112,57],[71,17],[30,57]];
  c.beginPath();points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.closePath();c.strokeStyle='#36505b';c.lineWidth=1;c.stroke();
  for(let i=0;i<4;i++){const occupied=frame?.runners.some(r=>r.last_legal_base===i&&i>0);c.save();c.translate(...points[i]);c.rotate(Math.PI/4);c.fillStyle=occupied?'#ffc46b':'#26404b';c.strokeStyle=occupied?'#ffe0ae':'#53717c';c.fillRect(-6,-6,12,12);c.strokeRect(-6,-6,12,12);c.restore();}
}
