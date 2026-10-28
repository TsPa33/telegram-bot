import type {Row} from './api';
export type Decision={action:string;target_id?:string;name?:string};
export type Decisions=Record<string,Decision>;
export type Pending={kind:'preview'|'apply';operationId:string|null;previousId:string|null;sent:Decisions};
export type Review={job:Row|null;draft:Decisions;checked:Decisions;rows:Row[];pending:Pending|null;invalid:boolean;error:string;notice:string};
export const emptyReview=():Review=>({job:null,draft:{},checked:{},rows:[],pending:null,invalid:false,error:'',notice:''});
const canonical=(a:Decisions)=>JSON.stringify(Object.keys(a).sort().map(k=>[k,a[k].action,a[k].name||'',a[k].target_id||'']));
export const equal=(a:Decisions,b:Decisions)=>canonical(a)===canonical(b);
export const active=(j:Row|null)=>['queued','running'].includes(j?.operation?.status);
export const draftKey=(actor:string,job:Row)=>`warehouse:catalogue-draft:v1:${encodeURIComponent(actor)}:${job.id}:${job.file_sha256}`;
export const lastKey=(actor:string)=>`warehouse:catalogue-selection:v1:${encodeURIComponent(actor)}`;
export function complete(v?:Decision){return !!v&&(v.action==='create_name'?!!v.name?.trim():v.action==='target'?!!v.target_id:['skip','keep_existing','accept_incoming'].includes(v.action));}
function rowsFor(job:Row,old:Row[]=[],draft:Decisions={}){
 const rows=new Map<string,Row>();
 for(const r of old)if(r.required!==false||draft[r.key])rows.set(r.key,r);
 for(const r of job.report?.issues||[])rows.set(r.key,r);
 // Older clients never saved source labels. Recover the actual checked values
 // without inventing an original name or executing another preview.
 Object.entries(job.resolutions||{}).forEach(([key,value],index)=>{
  if(!rows.has(key)){
   const decision=value as Decision;
   rows.set(key,{key,name:`Збережена відповідність ${index+1}`,sourceUnavailable:true,kind:'',required:true,
    allowed_actions:[...new Set([decision.action,'skip'])],candidates:[]});
  }
 });
 return [...rows.values()];
}
function decisions(value:unknown):value is Decisions{
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length>10000)return false;
 return Object.entries(value).every(([key,v])=>key.length<=128&&v&&typeof v==='object'&&
  ['create_name','target','skip','keep_existing','accept_incoming'].includes(v.action)&&
  (v.name===undefined||typeof v.name==='string'&&v.name.length<=1000)&&
  (v.target_id===undefined||typeof v.target_id==='string'&&v.target_id.length<=36));
}
function validSaved(saved:Row|null,job:Row,actor:string){
 return !!saved&&saved.version===1&&saved.actor===actor&&saved.jobId===job.id&&saved.sha===job.file_sha256&&decisions(saved.draft)&&
  Array.isArray(saved.rows)&&saved.rows.length<=10000&&saved.rows.every((r:Row)=>r&&typeof r.key==='string'&&typeof r.name==='string'&&Array.isArray(r.allowed_actions)&&
   (!r.candidates||Array.isArray(r.candidates)&&r.candidates.length<=50))&&
  (!saved.pending||['preview','apply'].includes(saved.pending.kind)&&decisions(saved.pending.sent)&&
   [saved.pending.operationId,saved.pending.previousId].every(v=>v===null||typeof v==='string'));
}
export function openReview(job:Row,saved:Row|null,actor:string):Review{
 const checked=job.resolutions||{};
 const valid=validSaved(saved,job,actor);
 const submitted=job.operation?.submitted_resolutions;
 const recover=active(job)||job.operation?.status==='error';
 const draft=valid?saved!.draft:(recover&&submitted?submitted:checked);
 const state:Review={job,draft,checked,rows:rowsFor(job,valid?saved!.rows:[],draft),pending:valid?saved!.pending:(active(job)&&submitted?{kind:job.operation.kind,operationId:job.operation.id,previousId:null,sent:submitted}:null),
  invalid:valid?!!saved!.invalid:false,error:'',notice:valid?'Чернетку відновлено для цього файла й акаунта.':saved?'Невідповідну чернетку відхилено: перевірте файл і акаунт.':''};
 return reconcile(state,job);
}
export function savedReview(state:Review,actor:string){
 return {version:1,actor,jobId:state.job!.id,sha:state.job!.file_sha256,draft:state.draft,
  pending:state.pending,rows:state.rows,invalid:state.invalid};
}
export function editDecision(state:Review,key:string,value?:Decision):Review{
 const draft={...state.draft};if(value)draft[key]=value;else delete draft[key];
 return {...state,draft,error:'',notice:'',invalid:state.invalid};
}
export function begin(state:Review,kind:'preview'|'apply'):Review{
 return {...state,pending:{kind,operationId:null,previousId:state.job?.operation?.id||null,sent:structuredClone(state.draft)},invalid:true,error:'',notice:''};
}
export function accepted(state:Review,job:Row):Review{
 if(!state.job||!state.pending||job.id!==state.job.id||job.file_sha256!==state.job.file_sha256)return state;
 // 202 is an acknowledgement, never a validated replacement for local inputs.
 return {...state,job,pending:{...state.pending,operationId:job.operation?.id||null}};
}
export function reconcile(state:Review,job:Row):Review{
 if(!state.job||job.id!==state.job.id)return state;
 if(job.file_sha256!==state.job.file_sha256)return {...emptyReview(),job,checked:job.resolutions||{},draft:job.resolutions||{},rows:rowsFor(job),invalid:true,error:'SHA файла змінився. Попередню чернетку не відновлено; перевірте файл.'};
 const next={...state,job,checked:job.resolutions||{},rows:rowsFor(job,state.rows,state.draft)};
 const p=state.pending,op=job.operation;
 if(p){
  if(!p.operationId&&(!op||op.id===p.previousId)){
   return {...next,pending:null,invalid:true,error:state.error||'Сервер не підтвердив прийняття нової перевірки. Чернетку збережено; перевірте рішення повторно.'};
  }
  if(p.operationId&&op?.id!==p.operationId)return {...next,pending:null,invalid:true,error:'На сервері з’явилась інша операція. Ваші поля збережено; повторіть перевірку рішень.'};
  if(active(job))return {...next,pending:{...p,operationId:op.id},error:''};
  if(op?.status==='error')return {...next,pending:null,invalid:true,error:op.error||'Перевірка завершилась помилкою. Чернетку збережено.'};
  if(op?.status==='done'){
   if(p.kind==='preview'&&!equal(job.resolutions||{},p.sent))return {...next,pending:null,invalid:true,error:'Сервер завершив перевірку з іншими рішеннями. Ваші назви збережено; потрібна нова перевірка.'};
   return {...next,pending:null,invalid:false,error:'',notice:p.kind==='preview'?'Рішення перевірено сервером.':'Імпорт застосовано.'};
  }
  return {...next,invalid:true};
 }
 if(active(job))return {...next,invalid:true,error:''};
 if(op?.status==='error')return {...next,invalid:true,error:op.error||'Операція завершилась помилкою.'};
 // A newer report never replaces an unsaved draft. It only updates checked data.
 return {...next,invalid:state.invalid,error:state.error};
}
export const dirty=(s:Review)=>!equal(s.draft,s.checked);
export const canApply=(s:Review)=>s.job?.status==='ready'&&!s.pending&&!active(s.job)&&!dirty(s)&&!s.invalid&&!!s.job.preview_token;
export const showReport=(s:Review)=>!s.pending&&!active(s.job)&&!dirty(s)&&!s.invalid;
