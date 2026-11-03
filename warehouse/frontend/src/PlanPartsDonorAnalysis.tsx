import {useContext,useEffect,useRef,useState} from 'react';
import {TeamIdentity} from './permissions';
import {api,ApiError,type Row} from './api';
import {ukrainianPartName} from './planPartsUkrainian';
import PlanPartsBatch from './PlanPartsBatch';

type Match={ktype:number;modification:string;year_from?:number;year_to?:number;power_kw?:number;power_ps?:number};
type Category={pt_id:number;name:string;article_count:number};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};

export default function PlanPartsDonorAnalysis({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const [matches,setMatches]=useState<Match[]>([]);
 const [picked,setPicked]=useState<number>(Number(vehicle.ktype)||0);
 const [savedKtype,setSavedKtype]=useState<number>(Number(vehicle.ktype)||0);
 const [selectedTypes,setSelectedTypes]=useState<number[]>([]);
 const [categories,setCategories]=useState<Category[]>([]);
 const [machineNames,setMachineNames]=useState<Record<string,string>>({});
 const [translationStatus,setTranslationStatus]=useState('');
 const [translationLoading,setTranslationLoading]=useState(false);
 const [addingType,setAddingType]=useState<number|null>(null);
 const [addedTypes,setAddedTypes]=useState<Record<number,string>>({});
 const [addMessage,setAddMessage]=useState('');
 const addLock=useRef(false);

 const translationBusy=useRef(false);

 const [articles,setArticles]=useState<Article[]>([]);
 const [activeCategory,setActiveCategory]=useState<number>(0);
 const [phase,setPhase]=useState<'initial'|'matching'|'categories'|'articles'>('initial');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false),[showAll,setShowAll]=useState(false);
 const [cooldownUntil,setCooldownUntil]=useState(0),[secondsLeft,setSecondsLeft]=useState(0);
 useEffect(()=>{
   if(!cooldownUntil){setSecondsLeft(0);return;}
   const tick=()=>setSecondsLeft(Math.max(0,Math.ceil((cooldownUntil-Date.now())/1000)));
   tick();
   const interval=window.setInterval(tick,1000);
   return ()=>window.clearInterval(interval);
 },[cooldownUntil]);
 const paidDisabled=busy||secondsLeft>0;
 const donorId=encodeURIComponent(String(vehicle.id));
 const teamIdentity=useContext(TeamIdentity);
 const categoryScope='plan-parts-categories-v1:'+String(teamIdentity?.id||'unknown')+':'+String(vehicle.id)+':'+picked;
 // Short-lived category metadata in this browser only; full paid article data
 // stays in the backend's bounded in-memory cache.
 useEffect(()=>{
  if(!picked)return;
  let active=true;
  const restore=(items:Category[])=>{
   if(!active)return;
   setCategories(items);
   setSelectedTypes(items.map(c=>c.pt_id));
   setPhase('categories');
  };
  try{
   const entry=JSON.parse(sessionStorage.getItem(categoryScope)||'null');
   if(entry?.until>Date.now()&&Array.isArray(entry.categories)){
    restore(entry.categories as Category[]);
    if(Array.isArray(entry.selectedTypes)){
     const valid=new Set((entry.categories as Category[]).map(c=>c.pt_id));
     setSelectedTypes(entry.selectedTypes.filter((id:unknown)=>typeof id==='number'&&valid.has(id)));
    }
    return ()=>{active=false;};
   }
  }catch{/* Browser storage is optional */}
  // This endpoint is strictly cache-only. An empty/expired cache must not
  // silently trigger another paid request.
  void api<{categories:Category[]}>('/plan-parts/categories/recover?vehicle_id='+donorId+'&ktype='+picked,'POST')
   .then(result=>{
    restore(result.categories);
    try{sessionStorage.setItem(categoryScope,JSON.stringify({until:Date.now()+30*60*1000,categories:result.categories,selectedTypes:result.categories.map(c=>c.pt_id)}));}catch{}
   }).catch(()=>{/* User can explicitly refresh with the paid lookup button */});
  return ()=>{active=false;};
 },[categoryScope,donorId,picked]);
 async function run(fn:()=>Promise<void>){
  if(gate.current)return;
  gate.current=true;setBusy(true);setError('');
  try{await fn();}catch(e){
   if(e instanceof ApiError&&e.status===429){
    const reported=Number((e.message.match(/через\\s+(\\d+)\\s*с/)||[])[1]);
    const wait=Number.isFinite(reported)&&reported>0?Math.min(300,reported):30;
    setCooldownUntil(Date.now()+wait*1000);
   }
   setError((e as Error).message);
  }
  finally{gate.current=false;setBusy(false);}
 }
 function discover(){void run(async()=>{
  const result=await api<{matches:Match[]}>('/plan-parts/vehicle-matches/lookup?vehicle_id='+donorId,'POST');
  setMatches(result.matches);setPhase('matching');setCategories([]);setArticles([]);
  if(!result.matches.length)setError('Точних кандидатів за маркою, моделлю та роком немає. Уточніть автомобіль.');
 });}
 function selectKtype(ktype:number){
  setPicked(ktype);setCategories([]);setArticles([]);setActiveCategory(0);setSelectedTypes([]);
 }
 function getCategories(){if(!picked)return;void run(async()=>{
  const result=await api<{categories:Category[]}>('/plan-parts/categories/lookup?vehicle_id='+donorId+'&ktype='+picked,'POST');
  setCategories(result.categories);setSelectedTypes(result.categories.map(c=>c.pt_id));setArticles([]);setActiveCategory(0);setPhase('categories');
  try{sessionStorage.setItem(categoryScope,JSON.stringify({until:Date.now()+30*60*1000,categories:result.categories}));}catch{/* optional */}
 });}
 function getArticles(ptId:number){void run(async()=>{
  const result=await api<{articles:Article[]}>('/plan-parts/articles/lookup?vehicle_id='+donorId+'&ktype='+picked+'&pt_id='+ptId,'POST');
  setArticles(result.articles);setActiveCategory(ptId);setPhase('articles');setShowAll(false);
 });}
 function saveModification(){if(!picked)return;void run(async()=>{
   await api('/plan-parts/vehicle-modification/select?vehicle_id='+donorId,'POST',{ktype:picked});
   setSavedKtype(picked);
   onSaved(await api('/vehicles/'+donorId));
  });}
 useEffect(()=>{
  if(!picked||categories.length===0)return;
  try{
   const entry=JSON.parse(sessionStorage.getItem(categoryScope)||'null');
   if(entry?.until>Date.now()&&Array.isArray(entry.categories)){
    sessionStorage.setItem(categoryScope,JSON.stringify({...entry,selectedTypes}));
   }
  }catch{/* Browser storage is optional */}
 },[selectedTypes,categoryScope,picked,categories.length]);

 async function addSelectedType(category:Category){
  if(addLock.current||savedKtype!==picked||!picked)return;
  const name=localizedName(category.name).trim();
  if(!/[А-Яа-яІіЇїЄєҐґ]/.test(name)){
   setAddMessage('Спочатку перекладіть назву українською або уточніть її у словнику.');
   return;
  }
  addLock.current=true;setAddingType(category.pt_id);setAddMessage('');
  try{
   const result=await api<{created:boolean;received:boolean;part_id:string;name:string;quantity:number}>(
    '/plan-parts/donor-parts/add?vehicle_id='+donorId,'POST',
    {ktype:picked,pt_id:category.pt_id,ukrainian_name:name});
   setAddedTypes(old=>({...old,[category.pt_id]:result.part_id}));
   setAddMessage(result.received
    ? '«'+result.name+'» додано на склад. Залишок: '+result.quantity+'.'
    : '«'+result.name+'» уже на складі. Залишок: '+result.quantity+'. Повторного надходження немає.');
  }catch(err){setAddMessage('Не вдалося додати: '+(err as Error).message);}
  finally{addLock.current=false;setAddingType(null);}
 }
 function localizedName(name:string){
  const reviewed=ukrainianPartName(name);
  return reviewed.translated?reviewed.uk:(machineNames[name]||reviewed.uk);
 }
 async function translateAllCategories(){
  if(translationBusy.current||!categories.length)return;
  const missing=Array.from(new Set(categories.map(c=>c.name)))
   .filter(name=>!ukrainianPartName(name).translated&&!machineNames[name]);
  if(!missing.length){setTranslationStatus('Усі назви перекладено.');return;}
  translationBusy.current=true;setTranslationLoading(true);setTranslationStatus('Перекладаємо назви деталей українською…');
  try{
   const result=await api<{configured:boolean;translations:Record<string,string>;untranslated:string[]}>(
    '/plan-parts/translations/lookup','POST',{names:missing});
   setMachineNames(old=>({...old,...result.translations}));
   if(!result.configured){
    setTranslationStatus('Для перекладу решти назв необхідно налаштувати WAREHOUSE_DEEPL_API_KEY у staging. Словник уже доступний.');
   }else{
    setTranslationStatus('Автоматичний переклад завершено. Технічні назви можна уточнювати вручну.');
   }
  }catch(e){setTranslationStatus('Сервіс перекладу недоступний: '+(e as Error).message);}
  finally{translationBusy.current=false;setTranslationLoading(false);}
 }
 useEffect(()=>{
  if(!categories.length)return;
  // Translate unknown generic names for every model; same English name is shared.
  void translateAllCategories();
 // A new category set, not translation state, triggers the request.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[categories]);
 useEffect(()=>{
  const missing=Array.from(new Set(articles.map(a=>a.part_name).filter(Boolean)))
   .filter(name=>!ukrainianPartName(name).translated&&!machineNames[name]);
  if(!missing.length)return;
  let active=true;
  void api<{translations:Record<string,string>}>('/plan-parts/translations/lookup','POST',{names:missing.slice(0,400)})
   .then(result=>{if(active)setMachineNames(old=>({...old,...result.translations}));})
   .catch(()=>{/* Do not block supplier articles when translation provider is down */});
  return ()=>{active=false;};
 // Only an incoming new set of articles triggers the translation.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[articles]);
 const selected=categories.find(c=>c.pt_id===activeCategory);
 const selectedCategories=categories.filter(c=>selectedTypes.includes(c.pt_id));
 const estimatedTokens=selectedCategories.length*2;
 const selectedOffers=selectedCategories.reduce((n,c)=>n+c.article_count,0);
 return <section aria-label="Каталог plan.parts для автомобіля" className="catalogue-formation" style={{display:'block',marginTop:12}}>
  <h3>Професійний каталог запчастин · plan.parts</h3>
  <p>Прямий пошук модифікації та реальних артикулів. Дані доступні лише власнику в тестовому режимі.</p>
  <p><strong>{vehicle.manufacturer} {vehicle.model} · {vehicle.year}</strong>{picked?<> · K-Type <strong>{picked}</strong></>:null}</p>
  <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
   <button type="button" disabled={paidDisabled} onClick={discover}>{busy&&phase==='initial'?'Шукаємо…':'Знайти модифікації (1 токен)'}</button>
   {picked>0&&<button type="button" disabled={paidDisabled} className="secondary" onClick={getCategories}>Категорії та кількість (1 токен)</button>}
  </div>
  {busy&&<p role="status">Отримуємо дані plan.parts…</p>}
  {secondsLeft>0&&<p role="status" aria-live="polite">Повторні платні запити будуть доступні через <strong>{secondsLeft} с</strong>. Збережений K-Type та вже отримані результати залишаються доступними.</p>}
  {error&&<p role="alert" className="error">{error}</p>}
  {matches.length>0&&<div style={{marginTop:12}}>
   <label>Оберіть точну модифікацію автомобіля
    <select disabled={busy} value={picked} onChange={e=>selectKtype(Number(e.target.value))}>
     <option value={0}>Не вибрано</option>
     {matches.map(m=><option key={m.ktype} value={m.ktype}>{m.modification} · {m.year_from??'—'}–{m.year_to??'дотепер'} · {m.power_kw??'—'} кВт · K-Type {m.ktype}</option>)}
    </select>
   </label>
   <small>Рік та модель не гарантують точну комплектацію. Зіставте двигун, потужність і КПП до вибору.</small>
   {picked>0&&<div style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap',marginTop:8}}><button type="button" className="secondary" disabled={busy||savedKtype===picked} onClick={saveModification}>{savedKtype===picked?'Модифікацію збережено':'Закріпити K-Type за автомобілем'}</button><small>{savedKtype===picked?'K-Type записаний у картку цього автомобіля.':'Вибір тимчасовий, доки не закріплений за автомобілем.'}</small></div>}
  </div>}
  {categories.length>0&&<div style={{marginTop:14}}>
   <p>Категорій: <strong>{categories.length}</strong> · Артикулів aftermarket: <strong>{categories.reduce((n,c)=>n+c.article_count,0).toLocaleString('uk-UA')}</strong></p>
   <p>Перелік типів запчастин із plan.parts. «Додати на склад» одним натисканням створює запчастину і оприбутковує 1 одиницю для вибраного автомобіля. Раніше додані позиції з нульовим залишком також оприбутковуються без дублювання. Артикули завантажувати не потрібно.</p>
   <div style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'center',margin:'10px 0'}}>
    <button type="button" disabled={busy||selectedTypes.length===categories.length} className="secondary" onClick={()=>setSelectedTypes(categories.map(c=>c.pt_id))}>Вибрати всі ({categories.length})</button>
    <button type="button" disabled={busy||selectedTypes.length===0} className="secondary" onClick={()=>setSelectedTypes([])}>Зняти вибір</button>
    <span>Вибрано: <strong>{selectedTypes.length}</strong> із {categories.length}</span>
   </div>
   <div style={{padding:14,background:'#edf6f2',border:'1px solid #b8dacd',borderRadius:10,marginBottom:10}}>
    <strong>Розрахунок повного завантаження артикулів</strong>
    <p style={{margin:'8px 0'}}>Типів деталей: <strong>{selectedTypes.length}</strong> · Пропозицій aftermarket у вибраних типах: <strong>{selectedOffers.toLocaleString('uk-UA')}</strong></p>
    <p style={{margin:'8px 0'}}>Запитів: <strong>{selectedTypes.length}</strong> × 2 токени = <strong>{estimatedTokens.toLocaleString('uk-UA')} токенів</strong></p>
    <small>Це орієнтовна верхня межа за поточним тарифом для окремих запитів. Нульові або неуспішні відповіді можуть не тарифікуватися. Баланс plan.parts тут не перевіряється. Розрахунок не витрачає токенів.</small>
    <div style={{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap',margin:'12px 0'}}>
     {selectedTypes.length===1&&<button type="button" disabled={paidDisabled} onClick={()=>getArticles(selectedTypes[0])}>Отримати артикули вибраного типу</button>}
     {selectedTypes.length>1&&<strong>Обрано {selectedTypes.length} типів — запуск нижче</strong>}
     {selectedTypes.length===0&&<strong>Оберіть хоча б один тип запчастин</strong>}
    </div>
    <p style={{margin:'8px 0'}}>Після отримання артикули з’являться під списком. Повторні однакові запити протягом 30 хвилин використовують тимчасовий кеш Backend без нових звернень до plan.parts, доки сервер не перезапущено.</p>
    <PlanPartsBatch key={picked} vehicleId={String(vehicle.id)} ktype={picked} selected={selectedCategories} disabled={busy||savedKtype!==picked} translatedNames={machineNames} />
   </div>
   <p style={{margin:'8px 0'}}>Українські назви: <strong>{categories.filter(c=>ukrainianPartName(c.name).translated||Boolean(machineNames[c.name])).length}</strong> із {categories.length}. Машинний переклад застосовується для назв, відсутніх у словнику. <button type="button" className="secondary" disabled={translationLoading} onClick={()=>void translateAllCategories()}>{translationLoading?'Перекладаємо…':'Повторити переклад відсутніх назв'}</button>{translationStatus&&<small style={{display:'block'}} role="status">{translationStatus}</small>}</p>
   {addMessage&&<p role="status" aria-live="polite">{addMessage}</p>}
   <div style={{maxHeight:310,overflowY:'auto',border:'1px solid #dae5e0',borderRadius:9}}>
    {categories.map(c=><div key={c.pt_id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:8,padding:'9px 12px',borderBottom:'1px solid #e7efeb'}}>
     <label style={{display:'flex',gap:8,alignItems:'center',flex:1}}><input type="checkbox" disabled={busy} checked={selectedTypes.includes(c.pt_id)} onChange={e=>setSelectedTypes(old=>e.target.checked?[...old,c.pt_id]:old.filter(id=>id!==c.pt_id))}/><span><strong>{localizedName(c.name)}</strong>{(ukrainianPartName(c.name).translated||Boolean(machineNames[c.name]))&&<small style={{display:'block',color:'#61746c'}}>Оригінал: {c.name}</small>}{!ukrainianPartName(c.name).translated&&!machineNames[c.name]&&<small style={{display:'block',color:'#9a611c'}}>Потрібен перевірений український відповідник</small>}<small style={{display:'block'}}>{c.article_count.toLocaleString('uk-UA')} артикулів</small></span></label>
     <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
      <button type="button" disabled={addingType!==null||savedKtype!==picked||Boolean(addedTypes[c.pt_id])} className="secondary" onClick={()=>void addSelectedType(c)}>{addedTypes[c.pt_id]?'Додано':addingType===c.pt_id?'Додаємо…' :'Додати на склад'}</button>
      <button type="button" disabled={paidDisabled} className="secondary" onClick={()=>getArticles(c.pt_id)}>Артикули (до 2 токенів)</button>
     </div>
    </div>)}
   </div>
  </div>}
  {phase==='articles'&&<section style={{marginTop:12}}>
   <h4>{selected?localizedName(selected.name):'Обрана категорія'} · {articles.length.toLocaleString('uk-UA')} артикулів</h4>
   <p>Унікальних назв: <strong>{new Set(articles.map(a=>a.part_name.toLocaleLowerCase('uk-UA')).filter(Boolean)).size}</strong>. Якщо назва артикула відсутня, показано назву типу з plan.parts. Аналоги різних виробників не можна автоматично додавати як окремі фізичні деталі.</p>
   <div style={{maxHeight:350,overflowY:'auto'}}>
    <table><thead><tr><th>Деталь</th><th>Виробник</th><th>Артикул</th></tr></thead>
     <tbody>{articles.slice(0,showAll?articles.length:80).map(a=><tr key={a.art_id}><td>{a.part_name?localizedName(a.part_name):(selected?localizedName(selected.name):'Назва категорії не визначена')}{ukrainianPartName(a.part_name).translated&&<small style={{display:'block',color:'#61746c'}}>Оригінал: {a.part_name}</small>}</td><td>{a.brand}</td><td>{a.article_nr}</td></tr>)}</tbody>
    </table>
   </div>
   {!showAll&&articles.length>80&&<button type="button" className="secondary" onClick={()=>setShowAll(true)}>Показати всі {articles.length.toLocaleString('uk-UA')} артикулів без нового запиту</button>}
  </section>}
  <small>Відомості постачальника показуються для аналізу; автоматичне перенесення у склад не увімкнене без перевірки ліцензії й зіставлення фізичних деталей. Платіжна модель CarPot вимкнена.</small>
 </section>;
}
