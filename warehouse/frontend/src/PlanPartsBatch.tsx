import {useContext,useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {TeamIdentity} from './permissions';
import {ukrainianPartName} from './planPartsUkrainian';

type Category={pt_id:number;name:string;article_count:number};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};
type Summary={count:number;names:number;finishedAt:number};
type Checkpoint={scope:string;until:number;completed:Record<string,Summary>;uncertain:number[]};
const CHECKPOINT_TTL=30*60*1000;
const API_PACE_MS=3400; // Keep comfortably below the current 10 requests / 30 seconds local budget.

export default function PlanPartsBatch({
 vehicleId,ktype,selected,disabled
}:{
 vehicleId:string;ktype:number;selected:Category[];disabled:boolean
}){
 const identity=useContext(TeamIdentity);
 const scope='plan-parts-batch-v1:'+String(identity?.id||'')+':'+vehicleId+':'+ktype;
 const [completed,setCompleted]=useState<Record<string,Summary>>({});
 const [uncertain,setUncertain]=useState<number[]>([]);
 const [data,setData]=useState<Record<string,Article[]>>({});
 const [previewId,setPreviewId]=useState<number|null>(null);
 const [expanded,setExpanded]=useState(false);
 const [confirmation,setConfirmation]=useState(false);
 const [retryApproval,setRetryApproval]=useState<number|null>(null);
 const [running,setRunning]=useState(false);
 const [message,setMessage]=useState('');
 const [tokenLimit,setTokenLimit]=useState('');
 const stop=useRef(false),locked=useRef(false);
 const [doneCount,setDoneCount]=useState(0);
 const [totalCount,setTotalCount]=useState(0);

 useEffect(()=>{
  stop.current=true;
  try{
   const stored=JSON.parse(sessionStorage.getItem(scope)||'null') as Checkpoint|null;
   if(stored?.scope===scope&&stored.until>Date.now()){
    setCompleted(stored.completed||{});
    setUncertain(stored.uncertain||[]);
   }else{
    sessionStorage.removeItem(scope);
    setCompleted({});setUncertain([]);
   }
  }catch{setCompleted({});setUncertain([]);}
  setData({});setPreviewId(null);setConfirmation(false);setMessage('');
 },[scope]);

 function checkpoint(next:Record<string,Summary>,ambiguous:number[]){
  setCompleted(next);setUncertain(ambiguous);
  try{
   sessionStorage.setItem(scope,JSON.stringify({
    scope,until:Date.now()+CHECKPOINT_TTL,completed:next,uncertain:ambiguous
   } satisfies Checkpoint));
  }catch{setMessage('Браузер не зміг зберегти прогрес. Не закривайте вкладку до завершення.');}
 }
 const pending=selected.filter(c=>!completed[String(c.pt_id)]&&!uncertain.includes(c.pt_id));
 const completedSelected=selected.filter(c=>completed[String(c.pt_id)]);
 const selectedUncertain=selected.filter(c=>uncertain.includes(c.pt_id));
 const requiredTokens=pending.length*2;
 const budget=tokenLimit.trim()===''?requiredTokens:Number(tokenLimit);
 const validBudget=Number.isInteger(budget)&&budget>=2&&budget<=2000;
 const allowance=validBudget?Math.floor(budget/2):0;
 const nextCount=Math.min(pending.length,allowance);
 const maxSpend=nextCount*2;

 function handleStop(){stop.current=true;setMessage('Зупиняємо після поточного запиту. Уже отримані результати залишаються доступними.');}
 async function fetchArticleCategory(ptId:number){
  const path='/plan-parts/articles/lookup?vehicle_id='+encodeURIComponent(vehicleId)+
   '&ktype='+ktype+'&pt_id='+ptId;
  // 429 is a definite refusal, so waiting then retrying cannot double-charge
  // that rejected call. Other errors remain quarantined and never auto-replayed.
  for(let attempt=0;attempt<4;attempt++){
   if(stop.current)throw new Error('Завантаження зупинено користувачем');
   try{return await api<{articles:Article[]}>(path,'POST');}
   catch(err){
    if(!(err instanceof ApiError)||err.status!==429||attempt===3)throw err;
    const reported=Number((err.message.match(/через\\s+(\\d+)\\s*с/)||[])[1]);
    const seconds=Number.isFinite(reported)&&reported>0?Math.min(120,reported):30;
    setMessage('Досягнуто обмеження запитів. Автоматично продовжимо після '+seconds+' с; раніше завантажені типи не повторюємо.');
    await new Promise<void>(resolve=>window.setTimeout(resolve,(seconds+1)*1000));
   }
  }
  throw new Error('Не вдалося завершити платний запит');
 }
 async function begin(){
  if(locked.current||!confirmation||!validBudget||nextCount<1||disabled)return;
  locked.current=true;stop.current=false;setRunning(true);setConfirmation(false);
  setMessage('Завантаження почалося. Не закривайте цю вкладку.');
  let done={...completed},ambiguous=[...uncertain],finished=0;
  const queue=pending.slice(0,nextCount);
  setDoneCount(0);setTotalCount(queue.length);
  for(const cat of queue){
   if(stop.current)break;
   try{
    const response=await fetchArticleCategory(cat.pt_id);
    // A successful provider response has been validated by the backend.
    const articles=response.articles;
    done[String(cat.pt_id)]={
     count:articles.length,
     names:new Set(articles.map(a=>a.part_name.trim().toLocaleLowerCase('uk-UA')).filter(Boolean)).size,
     finishedAt:Date.now()
    };
    setData(previous=>({...previous,[String(cat.pt_id)]:articles}));
    finished++;
    setDoneCount(finished);
    checkpoint({...done},[...ambiguous]);
   }catch(err){
    if(stop.current){
     setMessage('Зупинено користувачем. Уже підтверджені типи збережено у прогресі цієї сесії.');
     break;
    }
    if(err instanceof ApiError&&err.status===429){
     const seconds=Number((err.message.match(/через\s+(\d+)\s*с/)||[])[1]);
     setMessage('Ліміт запитів: '+err.message+'. Уже завершені категорії не повторюються. Продовжіть після закінчення таймера.');
     break;
    }
    // A transport error can occur AFTER the supplier has charged for a 2xx.
    // Never automatically replay an ambiguous charge; quarantine that category.
    ambiguous=[...new Set([...ambiguous,cat.pt_id])];
    checkpoint({...done},[...ambiguous]);
    setMessage('Зупинено на «'+cat.name+'»: '+(err as Error).message+
     '. Статус оплати цього запиту невідомий; автоматичний повтор заблоковано.');
    break;
   }
   if(!stop.current&&finished<queue.length){
    await new Promise<void>(resolve=>window.setTimeout(resolve,API_PACE_MS));
   }
  }
  if(!stop.current&&finished===queue.length){
   setMessage('Завершено '+finished+' типів. Дані доступні в цій сесії для аналізу; склад не змінено.');
  }
  locked.current=false;setRunning(false);
 }
 async function recoverFromCache(ptId:number){
  if(locked.current||running)return;
  locked.current=true;setRunning(true);setMessage('Перевіряємо тимчасовий кеш без платного запиту…');
  try{
   const response=await api<{articles:Article[]}>(
    '/plan-parts/articles/recover?vehicle_id='+encodeURIComponent(vehicleId)+
    '&ktype='+ktype+'&pt_id='+ptId,'POST');
   const articles=response.articles;
   const next={...completed,[String(ptId)]:{
    count:articles.length,
    names:new Set(articles.map(a=>a.part_name.trim().toLocaleLowerCase('uk-UA'))).size,
    finishedAt:Date.now()
   }};
   const rest=uncertain.filter(id=>id!==ptId);
   setData(old=>({...old,[String(ptId)]:articles}));
   checkpoint(next,rest);
   setMessage('Дані відновлено з кешу без нового запиту до plan.parts.');
  }catch(err){
   setMessage('Відновлення без оплати не вдалося: '+(err as Error).message+
    '. Категорію залишено заблокованою, новий платний запит не виконувався.');
  }finally{locked.current=false;setRunning(false);}
 }
 async function openCompletedType(ptId:number){
  if(data[String(ptId)]){setPreviewId(ptId);return;}
  if(locked.current||running)return;
  locked.current=true;setMessage('Відновлюємо артикули з серверного кешу без платного запиту…');
  try{
   const result=await api<{articles:Article[]}>(
    '/plan-parts/articles/recover?vehicle_id='+encodeURIComponent(vehicleId)+
    '&ktype='+ktype+'&pt_id='+ptId,'POST');
   setData(previous=>({...previous,[String(ptId)]:result.articles}));
   setPreviewId(ptId);
   setMessage('Завантажені раніше артикули відновлено без нового запиту до plan.parts.');
  }catch(err){
   setMessage('Кеш артикулів уже недоступний: '+(err as Error).message+
    '. Нового платного запиту не виконано. Статистика попереднього завантаження збережена.');
  }finally{locked.current=false;}
 }
 const rows=previewId===null?[]:data[String(previewId)]||[];
 const thisSession=Object.keys(data).length;
 return <section aria-label="Пакетне завантаження plan.parts" style={{border:'1px solid #b8dacd',borderRadius:10,padding:14,margin:'12px 0',background:'#f7fbf9'}}>
  <h4 style={{margin:'0 0 8px'}}>Завантажити вибрані типи одним запуском</h4>
  <p>Вибрано: <strong>{selected.length}</strong> · Уже оброблено: <strong>{completedSelected.length}</strong> · Залишилось: <strong>{pending.length}</strong> · Максимально за нові запити: <strong>{requiredTokens} токенів</strong>.</p>
  {selectedUncertain.length>0&&<div role="alert">
   <p>Неоднозначних або перерваних запитів: {selectedUncertain.length}. Платний повтор заблоковано.</p>
   {selectedUncertain.map(c=><div key={c.pt_id} style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',margin:'6px 0'}}>
    <span>{ukrainianPartName(c.name).uk}</span>
    <button type="button" className="secondary" disabled={running} onClick={()=>void recoverFromCache(c.pt_id)}>Спробувати відновити з кешу · 0 токенів</button>
    <button type="button" className="secondary" disabled={running} onClick={()=>setRetryApproval(c.pt_id)}>Дозволити новий запит (може коштувати 2 токени)</button>
   </div>)}
  </div>}
  {retryApproval!==null&&<div role="alertdialog" aria-label="Підтвердження повторної оплати" style={{border:'1px solid #d8b17b',padding:12,borderRadius:8,margin:'10px 0'}}>
    <strong>Попередній платний запит міг бути оплачений</strong>
    <p>Продовження може витратити ще до 2 токенів на той самий тип. Кнопка нижче лише повертає його до черги, новий запит вимагатиме окремого підтвердження завантаження.</p>
    <button type="button" disabled={running} onClick={()=>{
     checkpoint(completed,uncertain.filter(id=>id!==retryApproval));
     setRetryApproval(null);
     setMessage('Тип розблоковано. Перед новим платним запитом перевірте розрахунок і підтвердіть завантаження.');
    }}>Розблокувати для нового запиту</button>
    <button type="button" className="secondary" onClick={()=>setRetryApproval(null)}>Скасувати</button>
  </div>}
  <label style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
   Ліміт токенів для цього запуску
   <input type="number" min="2" max="2000" step="2" placeholder={String(requiredTokens)} value={tokenLimit} disabled={running} onChange={e=>{setTokenLimit(e.target.value);setConfirmation(false);}} style={{maxWidth:125}}/>
   <small>Порожнє поле = всі вибрані, що ще не завантажені</small>
  </label>
  <p>У цьому запуску: <strong>{nextCount}</strong> типів, максимум <strong>{maxSpend}</strong> токенів за тарифом. Баланс плану не перевіряється. Операція використовує реальні платні API-запити.</p>
  {!confirmation&&!running&&<button type="button" disabled={disabled||pending.length===0||!validBudget||locked.current} onClick={()=>setConfirmation(true)}>Перейти до підтвердження завантаження</button>}
  {confirmation&&!running&&<div style={{border:'1px solid #d3c4a2',background:'#fffbef',borderRadius:8,padding:12}}>
    <strong>Підтвердити платні запити</strong>
    <p>CarPot послідовно завантажить до {nextCount} типів, за тарифом до {maxSpend} токенів. Уже завершені пропустить. Без поповнення балів CarPot чи створення складських позицій.</p>
    <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
     <button type="button" disabled={disabled} onClick={()=>void begin()}>Підтвердити й завантажити</button>
     <button type="button" className="secondary" onClick={()=>setConfirmation(false)}>Скасувати</button>
    </div>
  </div>}
  {running&&<div role="status" aria-live="polite">
    <strong>Завантаження: {doneCount} із {totalCount} типів</strong>
    <progress value={doneCount} max={Math.max(1,totalCount)} style={{display:'block',width:'100%',margin:'8px 0'}}/>
    <button type="button" className="secondary" onClick={handleStop}>Зупинити після поточного запиту</button>
    <small style={{display:'block'}}>Для виконання завантаження вкладка має залишатися відкритою. Темп обмежено, щоб не перевищувати ліміт plan.parts.</small>
   </div>}
  {message&&<p role="status">{message}</p>}
  {completedSelected.length>0&&<div style={{marginTop:12}}>
   <strong>Отримані типи ({completedSelected.length})</strong>
   <p>Артикулів у завершених типах: <strong>{completedSelected.reduce((a,c)=>a+(completed[String(c.pt_id)]?.count||0),0).toLocaleString('uk-UA')}</strong>. Це aftermarket-пропозиції, а не фізичні запчастини.</p>
   <button className="secondary" type="button" onClick={()=>setExpanded(v=>!v)}>{expanded?'Згорнути результати':'Переглянути результати'}</button>
   {expanded&&<div style={{maxHeight:300,overflowY:'auto',marginTop:8}}>
    {completedSelected.map(c=><div key={c.pt_id} style={{padding:8,borderBottom:'1px solid #dfe9e4'}}>
     <strong>{ukrainianPartName(c.name).uk}</strong> · {completed[String(c.pt_id)].count} артикулів · {completed[String(c.pt_id)].names} назв
     <button type="button" className="secondary" disabled={running} onClick={()=>void openCompletedType(c.pt_id)}>{data[String(c.pt_id)]?'Переглянути артикули':'Відновити артикули з кешу · 0 токенів'}</button>
    </div>)}
   </div>}
  </div>}
  {previewId!==null&&<div style={{marginTop:12}}>
   <strong>Артикули вибраного типу: {rows.length}</strong><p><small>Якщо назва артикула відсутня, показано українську назву його категорії з plan.parts — це не підтверджена назва конкретного товару.</small></p>
   <div style={{maxHeight:260,overflow:'auto'}}><table><thead><tr><th>Назва</th><th>Бренд</th><th>Артикул</th></tr></thead><tbody>
    {rows.map(a=><tr key={a.art_id}><td>{a.part_name?ukrainianPartName(a.part_name).uk:(selected.find(c=>c.pt_id===previewId)?ukrainianPartName(selected.find(c=>c.pt_id===previewId)!.name).uk:'Назва категорії не визначена')}</td><td>{a.brand}</td><td>{a.article_nr}</td></tr>)}
   </tbody></table></div>
  </div>}
  <small>Тимчасовий серверний кеш діє до 30 хвилин і зникає після перезапуску. Для завершених типів доступна окрема безоплатна спроба відновлення артикулів. У браузері зберігається тільки короткий контрольний список завершених типів. Якщо Backend перезапуститься, не можна гарантувати безкоштовне відновлення всіх артикулів. Для постійного комерційного каталогу потрібне ліцензійне погодження.</small>
 </section>;
}
