'use strict';
const DEFAULT_PROFILE={schema_version:'1.0.0',visual_profile_id:'primitive-v1',model_asset_id:null,model_scale:1,model_origin_correction:[0,0,0],visual_offset_local:[0,0,0],role_offsets:{},anchors:{origin:'feet_center',glove:'visual_only',bat:'visual_only'}};
function validateProfile(value){
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('profile must be an object');
  if(Object.keys(value).sort().join()!==Object.keys(DEFAULT_PROFILE).sort().join())throw new Error('unknown or missing profile field');
  if(value.schema_version!=='1.0.0')throw new Error('unsupported visual profile version');
  const id=s=>typeof s==='string'&&s.length<=128&&/^[A-Za-z0-9_.:-]+$/.test(s);
  if(!id(value.visual_profile_id)||value.model_asset_id!==null&&!id(value.model_asset_id))throw new Error('invalid visual asset ID');
  const number=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
  const vector=(v,n)=>Array.isArray(v)&&v.length===n&&v.every(x=>number(x,-10,10));
  if(!number(value.model_scale,.1,4)||!vector(value.model_origin_correction,3)||!vector(value.visual_offset_local,3))throw new Error('invalid visual transform');
  if(!value.role_offsets||Array.isArray(value.role_offsets)||typeof value.role_offsets!=='object')throw new Error('invalid role offsets');
  const roles=['P','C','1B','2B','3B','SS','LF','CF','RF','batter','runner'];
  for(const [key,v] of Object.entries(value.role_offsets))if(!roles.includes(key)||!vector(v,2))throw new Error('invalid role offset');
  if(!value.anchors||Object.keys(value.anchors).sort().join()!=='bat,glove,origin'||value.anchors.origin!=='feet_center'||!id(value.anchors.glove)||!id(value.anchors.bat))throw new Error('invalid visual anchors');
  return structuredClone(value);
}
module.exports={validateProfile,DEFAULT_PROFILE};
