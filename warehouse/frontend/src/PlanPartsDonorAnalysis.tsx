import {useRef,useState} from 'react';
import {api,type Row} from './api';

type Match={ktype:number;modification:string;year_from?:number;year_to?:number;power_kw?:number;power_ps?:number};
type Category={pt_id:number;name:string;article_count:number};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};

export default function PlanPartsDonorAnalysis({vehicle}:{vehicle:Row}){
 const [matches,setMatches]=useState<Match[]>([]);
 const [picked,setPicked]=useState<number>(Number(vehicle.ktype)||0);
 const [categories,setCategories]=useState<Category[]>([]);
 const [articles,setArticles]=useState<Article[]>([]);
 const [activeCategory,setActiveCategory]=useState<number>(0);
 const [phase,setPhase]=useState<'initial'|'matching'|'categories'|'articles'>('initial');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false),[showAll,setShowAll]=useState(false);
 const donorId=encodeURIComponent(String(vehicle.id));
 async function run(fn:()=>Promise<void>){
  if(gate.current)return;
  gate.current=true;setBusy(true);setError('');
  try{await fn();}catch(e){setError((e as Error).message);}
  finally{gate.current=false;setBusy(false);}
 }
 function discover(){void run(async()=>{
  const result=await api<{matches:Match[]}>('/plan-parts/vehicle-matches/lookup?vehicle_id='+donorId,'POST');
  setMatches(result.matches);setPhase('matching');setCategories([]);setArticles([]);
  if(!result.matches.length)setError('Точних кандидатів за маркою, моделлю та роком немає. Уточніть автомобіль.');
 });}
 function selectKtype(ktype:number){
  setPicked(ktype);setCategories([]);setArticles([]);setActiveCategory(0);
 }
 function getCategories(){if(!picked)return;void run(async()=>{
  const result=await api<{categories:Category[]}>('/plan-parts/categories/lookup?vehicle_id='+donorId+'&ktype='+picked,'POST');
  setCategories(result.categories);setArticles([]);setActiveCategory(0);setPhase('categories');
 });}
 function getArticles(ptId:number){void run(async()=>{
  const result=await api<{articles:Article[]}>('/plan-parts/articles/lookup?vehicle_id='+donorId+'&ktype='+picked+'&pt_id='+ptId,'POST');
  setArticles(result.articles);setActiveCategory(ptId);setPhase('articles');setShowAll(false);
 });}
 const selected=categories.find(c=>c.pt_id===activeCategory);
 return <section aria-label="Каталог plan.parts для автомобіля" className="catalogue-formation" style={{display:'block',marginTop:12}}>
  <h3>Професійний каталог запчастин · plan.parts</h3>
  <p>Прямий пошук модифікації та реальних артикулів. Дані доступні лише власнику в тестовому режимі.</p>
  <p><strong>{vehicle.manufacturer} {vehicle.model} · {vehicle.year}</strong>{picked?<> · K-Type <strong>{picked}</strong></>:null}</p>
  <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
   <button type="button" disabled={busy} onClick={discover}>{busy&&phase==='initial'?'Шукаємо…':'Знайти модифікації (1 токен)'}</button>
   {picked>0&&<button type="button" disabled={busy} className="secondary" onClick={getCategories}>Категорії та кількість (1 токен)</button>}
  </div>
  {busy&&<p role="status">Отримуємо дані plan.parts…</p>}
  {error&&<p role="alert" className="error">{error}</p>}
  {matches.length>0&&<div style={{marginTop:12}}>
   <label>Оберіть точну модифікацію автомобіля
    <select disabled={busy} value={picked} onChange={e=>selectKtype(Number(e.target.value))}>
     <option value={0}>Не вибрано</option>
     {matches.map(m=><option key={m.ktype} value={m.ktype}>{m.modification} · {m.year_from??'—'}–{m.year_to??'дотепер'} · {m.power_kw??'—'} кВт · K-Type {m.ktype}</option>)}
    </select>
   </label>
   <small>Рік та модель не гарантують точну комплектацію. Зіставте двигун, потужність і КПП до вибору.</small>
  </div>}
  {categories.length>0&&<div style={{marginTop:14}}>
   <p>Категорій: <strong>{categories.length}</strong> · Артикулів aftermarket: <strong>{categories.reduce((n,c)=>n+c.article_count,0).toLocaleString('uk-UA')}</strong></p>
   <p>Перелік категорій із plan.parts (не кількість окремих деталей на донорі):</p>
   <div style={{maxHeight:310,overflowY:'auto',border:'1px solid #dae5e0',borderRadius:9}}>
    {categories.map(c=><div key={c.pt_id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:8,padding:'9px 12px',borderBottom:'1px solid #e7efeb'}}>
     <span>{c.name} · <strong>{c.article_count.toLocaleString('uk-UA')}</strong> артикулів</span>
     <button type="button" disabled={busy} className="secondary" onClick={()=>getArticles(c.pt_id)}>Артикули (2 токени)</button>
    </div>)}
   </div>
  </div>}
  {phase==='articles'&&<section style={{marginTop:12}}>
   <h4>{selected?.name||'Обрана категорія'} · {articles.length.toLocaleString('uk-UA')} артикулів</h4>
   <p>Унікальних назв: <strong>{new Set(articles.map(a=>a.part_name.toLocaleLowerCase('uk-UA'))).size}</strong>. Аналоги різних виробників не можна автоматично додавати як окремі фізичні деталі.</p>
   <div style={{maxHeight:350,overflowY:'auto'}}>
    <table><thead><tr><th>Деталь</th><th>Виробник</th><th>Артикул</th></tr></thead>
     <tbody>{articles.slice(0,showAll?articles.length:80).map(a=><tr key={a.art_id}><td>{a.part_name}</td><td>{a.brand}</td><td>{a.article_nr}</td></tr>)}</tbody>
    </table>
   </div>
   {!showAll&&articles.length>80&&<button type="button" className="secondary" onClick={()=>setShowAll(true)}>Показати всі {articles.length.toLocaleString('uk-UA')} артикулів без нового запиту</button>}
  </section>}
  <small>Відомості постачальника показуються для аналізу; автоматичне перенесення у склад не увімкнене без перевірки ліцензії й зіставлення фізичних деталей. Платіжна модель CarPot вимкнена.</small>
 </section>;
}
