import {useEffect,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {ukrainianPartName,translatedCategoryCount} from './planPartsUkrainian';
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
   <p>Перелік типів запчастин із plan.parts (не кількість окремих деталей на донорі):</p>
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
    <PlanPartsBatch key={picked} vehicleId={String(vehicle.id)} ktype={picked} selected={selectedCategories} disabled={busy||savedKtype!==picked} />
   </div>
   <p style={{margin:'8px 0'}}>Українські назви зі словника: <strong>{translatedCategoryCount(categories.map(c=>c.name))}</strong> із {categories.length}. Неперекладені терміни залишені оригінальними для точності.</p>
   <div style={{maxHeight:310,overflowY:'auto',border:'1px solid #dae5e0',borderRadius:9}}>
    {categories.map(c=><div key={c.pt_id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:8,padding:'9px 12px',borderBottom:'1px solid #e7efeb'}}>
     <label style={{display:'flex',gap:8,alignItems:'center',flex:1}}><input type="checkbox" disabled={busy} checked={selectedTypes.includes(c.pt_id)} onChange={e=>setSelectedTypes(old=>e.target.checked?[...old,c.pt_id]:old.filter(id=>id!==c.pt_id))}/><span><strong>{ukrainianPartName(c.name).uk}</strong>{ukrainianPartName(c.name).translated&&<small style={{display:'block',color:'#61746c'}}>Оригінал: {c.name}</small>}{!ukrainianPartName(c.name).translated&&<small style={{display:'block',color:'#9a611c'}}>Потрібен перевірений український відповідник</small>}<small style={{display:'block'}}>{c.article_count.toLocaleString('uk-UA')} артикулів</small></span></label>
     <button type="button" disabled={paidDisabled} className="secondary" onClick={()=>getArticles(c.pt_id)}>Артикули (до 2 токенів)</button>
    </div>)}
   </div>
  </div>}
  {phase==='articles'&&<section style={{marginTop:12}}>
   <h4>{selected?ukrainianPartName(selected.name).uk:'Обрана категорія'} · {articles.length.toLocaleString('uk-UA')} артикулів</h4>
   <p>Унікальних назв: <strong>{new Set(articles.map(a=>a.part_name.toLocaleLowerCase('uk-UA')).filter(Boolean)).size}</strong>. Аналоги різних виробників не можна автоматично додавати як окремі фізичні деталі.</p>
   <div style={{maxHeight:350,overflowY:'auto'}}>
    <table><thead><tr><th>Деталь</th><th>Виробник</th><th>Артикул</th></tr></thead>
     <tbody>{articles.slice(0,showAll?articles.length:80).map(a=><tr key={a.art_id}><td>{a.part_name?ukrainianPartName(a.part_name).uk:'Назва не вказана постачальником'}{ukrainianPartName(a.part_name).translated&&<small style={{display:'block',color:'#61746c'}}>Оригінал: {a.part_name}</small>}</td><td>{a.brand}</td><td>{a.article_nr}</td></tr>)}</tbody>
    </table>
   </div>
   {!showAll&&articles.length>80&&<button type="button" className="secondary" onClick={()=>setShowAll(true)}>Показати всі {articles.length.toLocaleString('uk-UA')} артикулів без нового запиту</button>}
  </section>}
  <small>Відомості постачальника показуються для аналізу; автоматичне перенесення у склад не увімкнене без перевірки ліцензії й зіставлення фізичних деталей. Платіжна модель CarPot вимкнена.</small>
 </section>;
}
