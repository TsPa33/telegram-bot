import type {Row} from './api';
export type QuickScope={actor:string;workspace:string;vehicle:string};
export type PendingQuick={version:1;scope:QuickScope;payload:Row};
export const quickStorageKey=(scope:QuickScope)=>'warehouse.quick-plan.1:'+JSON.stringify(scope);
export function readQuick(raw:string|null,scope:QuickScope):PendingQuick|null{
 if(!raw||raw.length>1024*1024)return null;
 try{const r=JSON.parse(raw);const p=r.payload;
  if(r.version!==1||JSON.stringify(r.scope)!==JSON.stringify(scope)||!p||p.confirm!==true||!Array.isArray(p.facts)||p.facts.length>200||!/^[a-f0-9]{64}$/.test(p.etag)||!/^[a-f0-9-]{36}$/.test(p.request_key))return null;
  if(Object.keys(p).some(k=>!['facts','selected','resolutions','reset_trial','confirm','etag','token','request_key'].includes(k)))return null;
  return r;
 }catch{return null;}
}
export function makeQuick(scope:QuickScope,payload:Row):PendingQuick{
 return {version:1,scope,payload:{...payload,request_key:crypto.randomUUID()}};
}
