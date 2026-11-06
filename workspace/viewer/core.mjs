export const Q = 4294967296;
export const meters = v => Number(v) / Q;
export const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
export const advanceCursor = (tick, seconds, speed, total) => clamp(tick+seconds*120*speed,0,total);
export function timeLabel(tick, milliseconds = true) {
  const ms = Math.floor(tick / 120 * 1000), minutes = Math.floor(ms / 60000), seconds = Math.floor(ms / 1000) % 60;
  return `${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}${milliseconds ? '.'+String(ms%1000).padStart(3,'0') : ''}`;
}
export function floorIndex(array, value, key = x => x.tick) {
  let lo = 0, hi = array.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (key(array[mid]) <= value) lo = mid + 1; else hi = mid; }
  return lo - 1;
}
export function sample(frames, tick) {
  const i = Math.max(0, floorIndex(frames, tick)), a = frames[i], b = frames[i+1];
  if (!a) return null;
  if (!b || b.tick === a.tick || b.cut || a.half !== b.half || a.inning !== b.inning || a.ball.mode !== b.ball.mode || a.ball.holder_id !== b.ball.holder_id) return a;
  const alpha = clamp((tick-a.tick)/(b.tick-a.tick), 0, 1);
  const position = (x,y) => x.map((v,j) => String(Math.round(Number(v)+(Number(y[j])-Number(v))*alpha)));
  const byId = new Map(b.players.map(p => [p.id,p]));
  return {...a, ball:{...a.ball,position_q:position(a.ball.position_q,b.ball.position_q)},
    players:a.players.map(p => byId.has(p.id) ? {...p,position_q:position(p.position_q,byId.get(p.id).position_q)} : p)};
}
export class ChunkCache {
  constructor(fetcher, max = 3) { this.fetcher=fetcher; this.max=max; this.cache=new Map();this.pending=new Map(); }
  async get(index) {
    if (this.cache.has(index)) { const value=this.cache.get(index);this.cache.delete(index);this.cache.set(index,value);return value; }
    if (this.pending.has(index)) return this.pending.get(index);
    const promise=this.fetcher(index).then(value => { this.cache.set(index,value);while(this.cache.size>this.max)this.cache.delete(this.cache.keys().next().value);return value; }).finally(()=>this.pending.delete(index));
    this.pending.set(index,promise);return promise;
  }
}
export function visualPosition(player, profile, enabled, slot) {
  const base=player.position_q.map(meters), offset=enabled ? profile?.role_offsets?.[slot || player.role] || [0,0] : [0,0];
  const global=enabled ? profile?.visual_offset_local || [0,0,0] : [0,0,0];
  const correction=enabled ? profile?.model_origin_correction || [0,0,0] : [0,0,0];
  return base.map((v,i)=>v+clamp(Number(offset[i])||0,-10,10)+clamp(Number(global[i])||0,-10,10)+clamp(Number(correction[i])||0,-10,10));
}
