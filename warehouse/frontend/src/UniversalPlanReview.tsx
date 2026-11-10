import {useContext,useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';

/** Explicit reconciliation using existing managed-plan tokens; never a stock receipt. */
export default function UniversalPlanReview({vehicle,onSaved}:{vehicle:Row;onSaved:()=>Promise<unknown>}){
 const who=useContext(TeamIdentity),can=useCan(),epoch=useRef(0),active=useRef(false);
 const scope=JSON.stringify([who?.id,who?.workspace_account_id,vehicle.id]);
 const [reviewLimit,setReviewLimit]=useState(30);
 const [plan,setPlan]=useState<Row|null>(null),[resolutions,setResolutions]=useState<Row>({}),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[done,setDone]=useState(false);
 const pending=useRef<{body:string;key:string}|null>(null);
 useEffect(()=>{epoch.current++;setReviewLimit(30);setPlan(null);setResolutions({});setDirty(false);setError('');setDone(false);pending.current=null;active.current=false;setBusy(false);return()=>{epoch.current++}},[scope]);
 if(!can('catalog.view'))return null;
 async function work(save=false){
  if(active.current)return;active.current=true;setBusy(true);setError('');const ticket=epoch.current;
  try{const body={facts:[],resolutions};
   if(save){if(!plan||dirty||plan.counts.review)throw Error('Спочатку перевірте всі неоднозначні зіставлення');
    const serialized=JSON.stringify({...body,token:plan.token});if(pending.current?.body!==serialized)pending.current={body:serialized,key:crypto.randomUUID()};
    await api(`/vehicles/${vehicle.id}/universal-plan`,'POST',{...body,token:plan.token,request_key:pending.current.key,confirm:true});
    if(ticket!==epoch.current)return;pending.current=null;setDone(true);setPlan(null);setResolutions({});setDirty(false);await onSaved();
   }else{const result=await api(`/vehicles/${vehicle.id}/universal-plan/preview`,'POST',body);if(ticket===epoch.current){setPlan(result);setDirty(false);setDone(false);}}
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}finally{if(ticket===epoch.current){active.current=false;setBusy(false)}}
 }
 return <details className="assembly-plan-review"><summary>Перевірити оновлення конструктивного плану</summary><p>Потенційний перелік із перевіреного довідника. Невідома застосовність потребує перевірки на автомобілі. Залишки не створюються, попередні рішення зберігаються.</p>
 {error&&<p role="alert">{error}</p>}{done&&<p role="status">План оновлено. Складські залишки не змінено.</p>}
 <button disabled={busy} onClick={()=>void work()}>Переглянути зміни плану</button>
 {plan&&<><p>Нових позицій: {plan.counts.new} · Наявних: {plan.counts.existing} · Потрібні рішення: {plan.counts.review} · Пропущено: {plan.counts.skipped}.</p><p>Історичних позицій, що залишаться: {plan.retained_historical_ids.length}. Наявність довідкового вузла не підтверджує його фактичний склад.</p>
 <div>{plan.proposals.filter((p:Row)=>p.action==='review'||resolutions[p.id]).slice(0,reviewLimit).map((p:Row)=><label key={p.id}>{p.item.name}<select aria-label={`Рішення для ${p.item.name}`} value={resolutions[p.id]?.action==='link'?resolutions[p.id].item_id:resolutions[p.id]?.action||''} disabled={busy} onChange={e=>{setDirty(true);setResolutions(old=>({...old,[p.id]:e.target.value==='skip'?{action:'skip',reason:'Користувач вирішив залишити поточний запис без змін'}:{action:'link',item_id:e.target.value,reason:'Явне зіставлення з наявною позицією користувачем'}}))}}><option value="" disabled>Оберіть рішення</option><option value="skip">Залишити попередні дані без змін</option>{p.candidates.map((r:Row)=><option key={r.id} value={r.id}>{r.name}{r.protected?' · зі складською історією':''}</option>)}</select></label>)}</div>
 {plan.proposals.filter((p:Row)=>p.action==='review'||resolutions[p.id]).length>reviewLimit&&<button onClick={()=>setReviewLimit(n=>n+30)}>Показати ще 30 рішень</button>}
 {can('dismantling.manage')&&<button disabled={busy||dirty||plan.counts.review>0||vehicle.archived} onClick={()=>void work(true)}>Зберегти перевірені зміни плану</button>}</>}
 </details>;
}
