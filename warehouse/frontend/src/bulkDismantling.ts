import type {Row} from './api';
import type {QuickScope} from './quickDismantling';
export type BulkIntent={version:1;scope:QuickScope;action:string;ids:string[];reason:string;lines:Record<string,Row>;cursor:number;expectedEtag:string;pending?:Row;results:Row[];preBlocked:Row[]};
export const batchSize=(action:string)=>action==='receipt'?100:1000;
export const bulkStorageKey=(s:QuickScope)=>'warehouse.bulk-plan.1:'+JSON.stringify(s);
export function restoreBulk(raw:string|null,scope:QuickScope):BulkIntent|null{
 if(!raw||raw.length>4*1024*1024)return null;
 try{const r=JSON.parse(raw);if(r.version!==1||JSON.stringify(r.scope)!==JSON.stringify(scope)||!Array.isArray(r.ids)||!r.ids.length||new Set(r.ids).size!==r.ids.length||r.ids.some((id:unknown)=>typeof id!=='string')||!Number.isInteger(r.cursor)||r.cursor<0||r.cursor>r.ids.length||!Array.isArray(r.results)||!r.lines||typeof r.lines!=='object'||!/^[a-f0-9]{64}$/.test(r.expectedEtag)||!['present','absent','exclude','restore','unchecked','not_applicable','dismantled','receipt'].includes(r.action))return null;
 if(r.pending&&(r.pending.action!==r.action||!Array.isArray(r.pending.ids)||JSON.stringify(r.pending.ids)!==JSON.stringify(r.ids.slice(r.cursor,r.cursor+batchSize(r.action)))||!/^[a-f0-9-]{36}$/.test(r.pending.request_key)||Object.keys(r.pending).some(k=>!['action','ids','etag','request_key','confirm','reason','lines','preview_token'].includes(k))))return null;
 return r;
 }catch{return null;}
}
export function eligibleFor(items:Row[],action:string){return items.filter(i=>i.eligibility?.[action]===null);}
export function blockedReasons(items:Row[],action:string){const result:Record<string,number>={};for(const i of items){const r=i.eligibility?.[action];if(r)result[r]=(result[r]||0)+1;}return result;}
export function selectionState(ids:string[],selected:Set<string>){const n=ids.filter(id=>selected.has(id)).length;return {checked:ids.length>0&&n===ids.length,mixed:n>0&&n<ids.length,count:n};}
export function newIntent(scope:QuickScope,action:string,ids:string[],etag:string,reason='',lines:Record<string,Row>={},preBlocked:Row[]=[]):BulkIntent{return {version:1,scope,action,ids:[...new Set(ids)],expectedEtag:etag,reason,lines,cursor:0,results:[],preBlocked};}
export async function runBatches(intent:BulkIntent,io:{preview:(ids:string[],action:string)=>Promise<Row>;post:(payload:Row)=>Promise<Row>;checkpoint:(value:BulkIntent)=>void}){
 while(intent.cursor<intent.ids.length){
  if(!intent.pending){
   const ids=intent.ids.slice(intent.cursor,intent.cursor+batchSize(intent.action)),p=await io.preview(ids,intent.action);
   if(p.etag!==intent.expectedEtag)throw Error('Список змінився між порціями. Зупинено без повторення виконаних дій; перегляньте решту позицій.');
   if(intent.action==='receipt'&&p.eligible_ids.some((id:string)=>!intent.lines[id]))throw Error('Змінилася придатність деталей. Перегляньте кількості перед новим надходженням.');
   intent.pending={ids,action:intent.action,etag:p.etag,request_key:crypto.randomUUID(),reason:intent.reason,confirm:['dismantled','receipt'].includes(intent.action),...(intent.action==='receipt'?{preview_token:p.preview_token,lines:ids.filter(id=>intent.lines[id]).map(id=>intent.lines[id])}:{})};io.checkpoint(intent);
  }
  let result:Row;
  try{result=await io.post(intent.pending);}catch(e){if(typeof (e as Row)?.status==='number'&&(e as Row).status<500){delete intent.pending;io.checkpoint(intent);}throw e;}
  intent.results.push(result);intent.cursor+=intent.pending.ids.length;intent.expectedEtag=result.etag;delete intent.pending;io.checkpoint(intent);
 }
 return {updated:intent.results.reduce((n,r)=>n+r.updated,0),skipped:intent.results.reduce((n,r)=>n+r.skipped,0)+(intent.preBlocked?.length||0),batches:intent.results.length,part_ids:intent.results.flatMap(r=>r.part_ids||[])};
}
export function receiptLinesValid(lines:Record<string,Row>){return Object.values(lines).every(r=>Number.isInteger(r.quantity)&&r.quantity>=1&&r.quantity<=1000000&&(!r.location||r.location.length<=120)&&(r.selling_price==null||/^\d{1,12}(\.\d{1,2})?$/.test(String(r.selling_price))));}
