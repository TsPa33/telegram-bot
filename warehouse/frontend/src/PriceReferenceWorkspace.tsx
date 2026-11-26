import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {api,ApiError,csrf,money,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';
import {pricesChanged} from './MarketPricing';
import {chooseReference,defaultRule,summary,type Rule} from './priceReferencePolicy';
import './price-reference-workspace.css';

type Job={rows:Row[];phase:'lookup'|'review'|'apply'|'done';rule:Rule;overwrite:boolean};
type Controls={job:Job|null;busy:boolean;paused:boolean;error:string;start:(target:string,rule:Rule,overwrite:boolean)=>Promise<void>;resume:()=>void;pause:()=>void;apply:()=>void;applyOne:(id:string)=>void;reset:()=>void;selected:number;vehicle:boolean};
const Context=createContext<Controls|null>(null);
const LIMIT=5000;
const delay=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
const denied=(e:unknown)=>e instanceof ApiError&&[401,403].includes(e.status);
const uncertain=(e:unknown)=>!(e instanceof ApiError)||e.status>=500;
export function PriceReferenceProvider({children,selectedIds,vehicleId,query}:{children:ReactNode;selectedIds:string[];vehicleId:string;query:string}){
 const identity=useContext(TeamIdentity),can=useCan(),scope=JSON.stringify([identity?.id,identity?.workspace_account_id||identity?.id]);
 const allowed=identity?.role==='DIRECTOR'&&(!identity.workspace_account_id||identity.workspace_account_id===identity.id)&&['inventory.view','catalog.view','market.check','parts.change_price'].every(can);
 const storage='warehouse.reference-job.v1:'+scope;
 return allowed?<JobProvider key={storage} storage={storage} selectedIds={selectedIds} vehicleId={vehicleId} query={query}>{children}</JobProvider>:<>{children}</>;
}
function JobProvider({children,storage,selectedIds,vehicleId,query}:{children:ReactNode;storage:string;selectedIds:string[];vehicleId:string;query:string}){
 const [job,setJob]=useState<Job|null>(()=>{try{const j=JSON.parse(sessionStorage.getItem(storage)||'null');return j&&Array.isArray(j.rows)&&j.rows.length<=LIMIT?j:null;}catch{return null;}});
 const [busy,setBusy]=useState(false),[paused,setPaused]=useState(!!job&&['lookup','apply'].includes(job.phase)),[error,setError]=useState('');
 const guard=useRef(false),stop=useRef(false),mounted=useRef(true),current=useRef(job);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;stop.current=true;};},[]);
 function persist(j:Job|null){
  if(j)sessionStorage.setItem(storage,JSON.stringify(j));else sessionStorage.removeItem(storage);
  current.current=j;if(mounted.current)setJob(j);
 }
 function change(id:string,patch:Row){const j=current.current!;persist({...j,rows:j.rows.map(r=>r.id===id?{...r,...patch}:r)});}
 async function run(fn:(fence:()=>void)=>Promise<void>){
  if(guard.current)return;guard.current=true;stop.current=false;setBusy(true);setPaused(false);setError('');
  const token=csrf();const fence=()=>{if(stop.current||!mounted.current||csrf()!==token)throw Error('Процес призупинено.');};
  try{await fn(fence);}catch(e){if(mounted.current){setPaused(true);setError((e as Error).message||'Операцію призупинено');}}
  finally{guard.current=false;if(mounted.current){setBusy(false);if(stop.current)setPaused(true);}}
 }
 async function idsFor(target:string,fence:()=>void){
  if(target==='selected')return [...new Set(selectedIds)];
  const q=new URLSearchParams(target==='filtered'?query:'');if(target==='vehicle')q.set('vehicle_id',vehicleId);
  for(const key of ['limit','offset','in_stock','category_facets','condition'])q.delete(key);
  const ids:string[]=[];let cursor='';
  do{fence();if(cursor)q.set('after_id',cursor);const page=await api('/pricing/selection?'+q);fence();
   ids.push(...page.ids);if(ids.length>LIMIT)throw Error('Понад 5000 позицій. Виберіть автомобіль або категорію; часткову операцію не запущено.');
   const next=page.truncated?page.next_after_id:'';
   if(page.truncated&&(!next||next===cursor))throw Error('Не вдалося завершити вибір усіх позицій.');
   cursor=next;
  }while(cursor);
  return [...new Set(ids)];
 }
 async function lookup(fence:()=>void){
  for(const r of current.current!.rows){
   if(r.state!=='pending')continue;fence();
   try{
    const ctx=await api('/parts/'+r.id+'/price-context');fence();
    if(!ctx.eligible||(!current.current!.overwrite&&ctx.selling_price!=null)){change(r.id,{state:'skipped',name:ctx.name,reason:!ctx.eligible?'Неактивна деталь':'Власну ціну збережено'});continue;}
    const result=await api('/parts/'+r.id+'/market-reference','POST',{});fence();
    if(result.price_token!==ctx.price_token){change(r.id,{state:'attention',name:ctx.name,reason:'Дані змінилися — потрібна повторна перевірка'});continue;}
    const chosen=chooseReference(result,ctx,current.current!.rule);
    change(r.id,chosen?{state:'ready',name:ctx.name,value:chosen.value,currency:ctx.currency,token:ctx.price_token,old:ctx.selling_price,count:chosen.group.offer_count,match:chosen.group.match,observed_at:chosen.group.observed_at}:{state:'attention',name:ctx.name,reason:'Немає єдиної порівнюваної групи з 3+ цінами'});
    if(result.live_enabled)await delay(3200);
   }catch(e){if(stop.current||!mounted.current||denied(e)||uncertain(e))throw e;change(r.id,{state:'error',reason:(e as Error).message});}
  }
  fence();persist({...current.current!,phase:'review'});
 }
 async function applyRows(fence:()=>void,only?:string){
  for(const r of current.current!.rows){
   if(only&&r.id!==only)continue;
   if(!['ready','uncertain'].includes(r.state))continue;fence();
   // Persist the exact request before sending it. A lost response is replayed
   // with the same key; never obtain a newer token to overwrite another edit.
   const body=r.body||{selling_price:r.value,currency:r.currency,expected_token:r.token,request_key:crypto.randomUUID()};
   change(r.id,{state:'uncertain',body});
   try{await api('/parts/'+r.id+'/price','PATCH',body);change(r.id,{state:'applied',body:null});}
   catch(e){if(denied(e)||uncertain(e))throw e;change(r.id,{state:'error',body:null,reason:(e as Error).message});}
   fence();
  }
  const j=current.current!;persist({...j,phase:j.rows.some(r=>r.state==='ready'||r.state==='uncertain')?'review':'done'});
 }
 async function start(target:string,rule:Rule,overwrite:boolean){await run(async fence=>{
  if(current.current?.rows.some(r=>r.state==='uncertain'))throw Error('Спочатку перевірте непідтверджений запис ціни.');
  const ids=await idsFor(target,fence);fence();if(!ids.length)throw Error('Немає вибраних активних запчастин.');if(ids.length>LIMIT)throw Error('Не більше 5000 позицій за одну перевірку.');
  persist({rows:ids.map(id=>({id,state:'pending'})),phase:'lookup',rule,overwrite});await lookup(fence);
 });}
 function resume(){void run(async fence=>{const j=current.current;if(!j)return;if(j.phase==='lookup')await lookup(fence);else if(j.phase==='apply'||j.rows.some(r=>r.state==='uncertain')){persist({...j,phase:'apply'});try{await applyRows(fence);}finally{pricesChanged();}}});}
 function apply(){void run(async fence=>{const j=current.current;if(!j||j.phase!=='review')return;persist({...j,phase:'apply'});try{await applyRows(fence);}finally{pricesChanged();}});}
 function applyOne(id:string){void run(async fence=>{const j=current.current;if(!j||j.phase!=='review'||j.rows.some(r=>r.state==='uncertain'))return;persist({...j,phase:'apply'});try{await applyRows(fence,id);}finally{pricesChanged();}});}
 function reset(){if(guard.current||current.current?.rows.some(r=>r.state==='uncertain'))return;try{persist(null);setPaused(false);setError('');}catch(e){setError((e as Error).message);}}
 return <Context.Provider value={{job,busy,paused,error,start,resume,pause:()=>{stop.current=true;setPaused(true);},apply,applyOne,reset,selected:selectedIds.length,vehicle:!!vehicleId}}>{children}</Context.Provider>;
}
export function PriceReferenceToolbar(){
 const c=useContext(Context),[target,setTarget]=useState('filtered'),[rule,setRule]=useState<Rule>(defaultRule),[overwrite,setOverwrite]=useState(false),[confirm,setConfirm]=useState(false),[open,setOpen]=useState(false);
 useEffect(()=>setConfirm(false),[c?.job?.phase,c?.job?.rows.length]);
 if(!c)return null;
 const j=c.job,s=summary(j?.rows||[]),locked=c.busy||!!j;
 const lookup=j?.phase==='lookup',apply=j?.phase==='apply'||j?.phase==='done';
 const progress=lookup?s.checked:s.applied+s.attention+s.skipped;
 return <section className="price-workspace" aria-label="Масове уточнення цін">
  <header><strong>Масове уточнення цін</strong><button type="button" className="secondary" onClick={()=>setOpen(v=>!v)}>{open?'Згорнути':'Налаштувати'}</button></header>
  {(open||j)&&<><div className="price-workspace-controls">
   <label>Запчастини<select aria-label="Обсяг уточнення цін" value={target} disabled={locked} onChange={e=>setTarget(e.target.value)}><option value="filtered">Поточний пошук / категорія</option><option value="selected">Вибрані ({c.selected})</option>{c.vehicle&&<option value="vehicle">Усі запчастини автомобіля</option>}<option value="all">Увесь активний склад</option></select></label>
   <label>Правило<select value={rule.mode} disabled={locked} onChange={e=>setRule({...rule,mode:e.target.value as Rule['mode']})}><option value="average">Середня ціна</option><option value="minimum">Мінімальна ціна</option><option value="maximum">Максимальна ціна</option></select></label>
   <label>Коригування, %<input aria-label="Коригування ціни" value={rule.percent} disabled={locked} onChange={e=>setRule({...rule,percent:e.target.value})} inputMode="decimal"/></label>
  </div><label className="check-inline"><input type="checkbox" checked={overwrite} disabled={locked} onChange={e=>setOverwrite(e.target.checked)}/>Дозволити заміну встановлених цін</label>
  <label className="check-inline"><input type="checkbox" checked={rule.similar} disabled={locked} onChange={e=>setRule({...rule,similar:e.target.checked})}/>Враховувати схожі деталі (сумісність не підтверджена)</label>
  {!j&&<button type="button" className="primary" disabled={c.busy||(target==='selected'&&!c.selected)||!(/^-?\d{1,3}(\.\d{1,2})?$/.test(rule.percent))||Number(rule.percent)<-99||Number(rule.percent)>100} onClick={()=>void c.start(target,rule,overwrite)}>Отримати орієнтири</button>}
  {j&&<><div className="price-workspace-progress" role="status" aria-live="polite"><strong>{lookup?'Прогрес уточнення':apply?'Прогрес встановлення':'Орієнтири готові'}</strong><progress max={s.total||1} value={lookup?s.checked:apply?progress:s.checked}/><span>{lookup?s.checked:apply?progress:s.checked} із {s.total}</span></div>
  <div className="price-workspace-counts"><span>Готово: {s.ready}</span><span>Встановлено: {s.applied}</span><span>Потребує уваги: {s.attention}</span><span>Пропущено: {s.skipped}</span>{s.uncertain>0&&<span>Не підтверджено: {s.uncertain}</span>}</div>
  {c.busy&&<button type="button" disabled={c.paused} onClick={c.pause}>{c.paused?'Призупиняємо…':'Призупинити'}</button>}
  {!c.busy&&(c.paused||s.uncertain>0||j.phase==='lookup'||j.phase==='apply')&&<button type="button" onClick={c.resume}>Продовжити</button>}
  {j.phase==='review'&&!c.busy&&s.ready>0&&!s.uncertain&&<><p>Ціни ще не змінено. Перевірте орієнтири; {j.overwrite?'дозволено заміну встановлених цін':'наявні ціни зберігаються'}.</p><label className="check-inline"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>Підтверджую встановлення {s.ready} цін</label><button className="primary" disabled={!confirm} onClick={()=>{setConfirm(false);c.apply();}}>Додати ціни масово</button></>}
  {!c.busy&&!s.uncertain&&<button type="button" className="secondary" onClick={c.reset}>Нова перевірка</button>}
  <details><summary>Результати перевірки</summary><div className="price-workspace-results">{j.rows.filter(r=>r.state!=='pending').slice(0,100).map(r=><div key={r.id}><span>{r.name||'Запчастина'}</span><small>{r.value?money(r.value,r.currency):r.reason||'—'} · {r.state==='applied'?'Встановлено':r.state==='ready'?'Готово':r.state==='skipped'?'Пропущено':'Потребує уваги'}</small></div>)}</div>{j.rows.length>100&&<small>Перші 100 результатів; інші доступні у списку запчастин.</small>}</details></>}
  {c.error&&<p role="alert">{c.error}</p>}
  </>}
 </section>;
}
export function PriceReferenceRow({part}:{part:Row}){
 const c=useContext(Context),r=c?.job?.rows.find(r=>r.id===part.id);
 if(!r||!c)return null;
 return <div className={'price-workspace-row state-'+r.state}>
  <span>{r.state==='ready'?'Орієнтир: '+money(r.value,r.currency):r.state==='applied'?'Ціну встановлено':r.state==='pending'?'Очікує уточнення':r.state==='uncertain'?'Перевірка запису ціни':r.state==='skipped'?'Пропущено: '+r.reason:'Потребує уваги'}</span>
  {r.state==='ready'&&c.job?.phase==='review'&&<button type="button" disabled={c.busy||c.job.rows.some(r=>r.state==='uncertain')} onClick={()=>c.applyOne(part.id)}>{r.old!=null?'Замінити ціну':'Додати ціну'}</button>}
 </div>;
}
