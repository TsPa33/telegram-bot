import {useContext,useEffect,useRef,useState} from 'react';
import {TeamIdentity} from './permissions';
import {api,ApiError,type Row} from './api';
import {ukrainianPartName} from './planPartsUkrainian';
import PlanPartsBatch from './PlanPartsBatch';
import './plan-parts-workspace.css';

type Match={ktype:number;modification:string;year_from?:number;year_to?:number;power_kw?:number;power_ps?:number};
type Category={pt_id:number;name:string;article_count:number};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};

export default function PlanPartsDonorAnalysis({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const donorId=encodeURIComponent(String(vehicle.id));
 const [matches,setMatches]=useState<Match[]>([]);
 const [partQuery,setPartQuery]=useState('');
 const [stockFilter,setStockFilter]=useState('all');
 const [onlyCategory,setOnlyCategory]=useState('all');
 const [showTechnical,setShowTechnical]=useState(false);
 const [showArticleTools,setShowArticleTools]=useState(false);
 const [showMaintenance,setShowMaintenance]=useState(false);
 const [batchBusy,setBatchBusy]=useState(false);
 const [confirmBatch,setConfirmBatch]=useState(false);
 const [batchProgress,setBatchProgress]=useState(0);
 const stopBatch=useRef(false);
 const [picked,setPicked]=useState<number>(Number(vehicle.ktype)||0);
 const [savedKtype,setSavedKtype]=useState<number>(Number(vehicle.ktype)||0);
 const [selectedTypes,setSelectedTypes]=useState<number[]>([]);
 const [categories,setCategories]=useState<Category[]>([]);
 const [machineNames,setMachineNames]=useState<Record<string,string>>({});
 const [translationStatus,setTranslationStatus]=useState('');
 const [translationLoading,setTranslationLoading]=useState(false);
 const [addingType,setAddingType]=useState<number|null>(null);
 type StoredPart={id:string;pt_id:number|null;name:string;quantity:number;archived:boolean};
 const [stockParts,setStockParts]=useState<StoredPart[]>([]);
 const [duplicateStockNames,setDuplicateStockNames]=useState<{name:string;count:number}[]>([]);
 const [stockStatusLoading,setStockStatusLoading]=useState(false);
 const [stockStatusError,setStockStatusError]=useState('');
 const nameKey=(s:string)=>s.trim().toLocaleLowerCase('uk-UA').replace(/\s+/g,' ');
 const alreadyStored=(c:Category)=>stockParts.find(p=>!p.archived&&(p.pt_id===c.pt_id||nameKey(p.name)===nameKey(localizedName(c.name))));
 async function refreshStockStatus(){
  if(!picked||savedKtype!==picked)return;
  setStockStatusLoading(true);
  try{
   const r=await api<{parts:StoredPart[];duplicate_names:{name:string;count:number}[]}>('/plan-parts/donor-parts/status?vehicle_id='+donorId+'&ktype='+picked);
   setStockParts(r.parts);setDuplicateStockNames(r.duplicate_names||[]);setStockStatusError('');
  }catch(e){setStockStatusError('Не вдалося перевірити фактичний статус складу: '+(e as Error).message);}
  finally{setStockStatusLoading(false);}
 }
 useEffect(()=>{
  if(!picked||savedKtype!==picked){setStockParts([]);setDuplicateStockNames([]);return;}
  void refreshStockStatus();
  // Reload only when donor/confirmed modification changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[donorId,picked,savedKtype]);
 const [addMessage,setAddMessage]=useState('');
 type ClassRow={part_id:string;name:string;kind:string;section:string|null;mapping:string;action:string};
 type ClassPreview={rows:ClassRow[];total:number;can_apply:number;needs_review:number;already_categorized:number};
 const [classificationPreview,setClassificationPreview]=useState<ClassPreview|null>(null);
 const [classLoading,setClassLoading]=useState(false);
 const [classMessage,setClassMessage]=useState('');

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
   setSelectedTypes([]);
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
    try{sessionStorage.setItem(categoryScope,JSON.stringify({until:Date.now()+30*60*1000,categories:result.categories,selectedTypes:[]}));}catch{}
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
  setMatches(result.matches);setPhase('matching');setArticles([]);
  if(!result.matches.length)setError('Точних кандидатів за маркою, моделлю та роком немає. Уточніть автомобіль.');
 });}
 function selectKtype(ktype:number){
  setPicked(ktype);setCategories([]);setArticles([]);setActiveCategory(0);setSelectedTypes([]);
 }
 function getCategories(){if(!picked)return;void run(async()=>{
  const result=await api<{categories:Category[]}>('/plan-parts/categories/lookup?vehicle_id='+donorId+'&ktype='+picked,'POST');
  setCategories(result.categories);setSelectedTypes([]);setArticles([]);setActiveCategory(0);setPhase('categories');
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
   await refreshStockStatus();
   onSaved(await api('/vehicles/'+donorId));
   setAddMessage(result.received
    ? '«'+result.name+'» додано на склад. Залишок: '+result.quantity+'.'
    : '«'+result.name+'» уже на складі. Залишок: '+result.quantity+'. Повторного надходження немає.');
  }catch(err){setAddMessage('Не вдалося додати: '+(err as Error).message);}
  finally{addLock.current=false;setAddingType(null);}
 }
 async function receivePreviousSelections(){
  if(addLock.current||!picked||savedKtype!==picked)return;
  addLock.current=true;setAddingType(-1);setAddMessage('Оприбутковуємо раніше додані позиції…');
  try{
   const r=await api<{received_count:number}>(
    '/plan-parts/donor-parts/receive-pending?vehicle_id='+donorId+'&ktype='+picked,'POST');
   setAddMessage(r.received_count
    ? 'Оприбутковано раніше вибраних запчастин: '+r.received_count+'. Залишок кожної: 1.'
    : 'Усі раніше додані запчастини вже враховані на складі.');
   onSaved(await api('/vehicles/'+donorId));
   await refreshStockStatus();
  }catch(err){setAddMessage('Не вдалося оприбуткувати раніше додані: '+(err as Error).message);}
  finally{addLock.current=false;setAddingType(null);}
 }
 async function previewStockClassification(){
  if(!picked||savedKtype!==picked)return;
  setClassLoading(true);setClassMessage('');
  try{
   const result=await api<ClassPreview>('/plan-parts/donor-parts/classification/preview?vehicle_id='+donorId+'&ktype='+picked);
   setClassificationPreview(result);
  }catch(e){setClassMessage('Не вдалося перевірити категорії: '+(e as Error).message);}
  finally{setClassLoading(false);}
 }
 async function applyStockClassification(){
  if(!picked||savedKtype!==picked||!classificationPreview?.can_apply)return;
  setClassLoading(true);
  try{
   const result=await api<{updated_count:number;needs_review:number}>(
    '/plan-parts/donor-parts/classification/apply?vehicle_id='+donorId+'&ktype='+picked,'POST');
   setClassMessage('Категорії призначено для '+result.updated_count+' позицій. Ще потребують перевірки: '+result.needs_review+'. Залишки, ціни й фізичне розміщення не змінено.');
   await previewStockClassification();
   onSaved(await api('/vehicles/'+donorId));
  }catch(e){setClassMessage('Не вдалося оновити категорії: '+(e as Error).message);}
  finally{setClassLoading(false);}
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
 async function addSelectedToStock(){
  if(addLock.current||batchBusy||!picked||picked!==savedKtype||stockStatusError||stockStatusLoading)return;
  const pending=categories.filter(c=>selectedTypes.includes(c.pt_id)&&!alreadyStored(c));
  setConfirmBatch(false);
  if(!pending.length){setAddMessage('Нових вибраних запчастин немає.');return;}
  addLock.current=true;stopBatch.current=false;setBatchBusy(true);setBatchProgress(0);
  let done=0;
  try{
   for(let offset=0;offset<pending.length;offset+=30){
    if(stopBatch.current)break;
    const subset=pending.slice(offset,offset+30);
    const valid=subset.filter(c=>/[А-Яа-яІіЇїЄєҐґ]/.test(localizedName(c.name)));
    if(valid.length!==subset.length)throw Error('Деякі назви не перекладено. Повторіть переклад і звірте склад.');
    const response=await api<{results:{pt_id:number;ok:boolean;error?:string}[];attempted:number}>(
     '/plan-parts/donor-parts/add-batch?vehicle_id='+donorId,'POST',
     {items:valid.map(c=>({ktype:picked,pt_id:c.pt_id,ukrainian_name:localizedName(c.name)}))});
    done+=response.results.filter(r=>r.ok).length;
    setBatchProgress(done);
    if(response.results.some(r=>!r.ok)||response.attempted<valid.length){
     throw Error((response.results.find(r=>!r.ok)?.error||'Операцію перервано')+'. Оновіть статус складу перед повтором.');
    }
   }
   setSelectedTypes([]);
   setAddMessage('Опрацьовано: '+done+' типів.'+(stopBatch.current?' Завантаження зупинено.':''));
  }catch(e){
   setAddMessage('Опрацьовано: '+done+'. '+(e as Error).message);
  }finally{
   try{await refreshStockStatus();onSaved(await api('/vehicles/'+donorId));}
   catch(e){setAddMessage(v=>v+' Не вдалося перевірити залишки: '+(e as Error).message);}
   addLock.current=false;setBatchBusy(false);
  }
 }
 // Presentation-only categorization. Actual saved categories are resolved on
 // the backend against the workspace taxonomy; ambiguous names stay "Інші".
 const sectionOf=(c:Category)=>{
  const raw=(c.name+' '+localizedName(c.name)).toLocaleLowerCase('uk-UA');
  if(/tool|puller|інструмент|знімач|fluid|антифриз|паста для|олива|lubricant/.test(raw))return 'Обладнання та матеріали';
  if(/brake|гальм|супорт|колодк/.test(raw))return 'Гальмівна система';
  if(/steering|кермов|рульов/.test(raw))return 'Кермове керування';
  if(/suspension|shock absorber|strut|стабілізатор|підвіск|амортиз/.test(raw))return 'Підвіска і ходова';
  if(/headlight|bulb|tail light|direction indicator|lamp|фар|ламп|ліхтар|освітл/.test(raw))return 'Освітлення';
  if(/air conditioning|heater|клімат|кондиціон|обігрів|пічк/.test(raw))return 'Кліматична система';
  if(/transmission|gearbox|drive shaft|differential|трансміс|шрус|диференціал|коробк.{0,9}передач/.test(raw))return 'Трансмісія та привід';
  if(/fuel|engine|filter|coolant|crankshaft|camshaft|turbo|двигун|палив|фільтр|охолодж|турбін/.test(raw))return 'Двигун і системи';
  if(/window|mirror|door|bumper|wing|fender|body panel|кузов|дзеркал|двер|капот|бампер/.test(raw))return 'Кузов і зовнішні деталі';
  if(/sensor|alternator|wiring|relay|starter|battery|датчик|генератор|реле|акумулятор|стартер/.test(raw))return 'Електрика та електроніка';
  return 'Інші деталі';
 };
 const filteredCategories=categories.filter(c=>{
  const name=localizedName(c.name).toLocaleLowerCase('uk-UA');
  const search=partQuery.trim().toLocaleLowerCase('uk-UA');
  const stored=alreadyStored(c);
  return (!search||name.includes(search)||c.name.toLocaleLowerCase().includes(search)||String(c.pt_id).includes(search))
   &&(stockFilter==='all'||(stockFilter==='stored'?Boolean(stored):!stored))
   &&(onlyCategory==='all'||sectionOf(c)===onlyCategory);
 });
 const chosenNew=categories.filter(c=>selectedTypes.includes(c.pt_id)&&!alreadyStored(c)).length;
 const selected=categories.find(c=>c.pt_id===activeCategory);
 const selectedCategories=categories.filter(c=>selectedTypes.includes(c.pt_id));
 const estimatedTokens=selectedCategories.length*2;
 const selectedOffers=selectedCategories.reduce((n,c)=>n+c.article_count,0);
 return <section aria-label="Розбір автомобіля та запчастини" className="cp-plan">
  <div className="cp-plan-layout">
   <div className="cp-plan-main">
    <div className="cp-plan-panel">
     <h3>1. Модифікація та джерело</h3>
     <div className="cp-plan-source">
      <div><small>Джерело</small><strong>plan.parts API</strong></div>
      <div><small>Автомобіль</small><strong>{vehicle.manufacturer} {vehicle.model} · {vehicle.year}</strong></div>
      <div><small>Модифікація</small><strong>{matches.find(m=>m.ktype===picked)?.modification||'K-Type '+(picked||'не визначено')}</strong></div>
     </div>
     <div className="cp-plan-metrics"><span>{categories.length.toLocaleString('uk-UA')} типів</span><span>{categories.reduce((sum,c)=>sum+c.article_count,0).toLocaleString('uk-UA')} артикулів</span>{categories.length>0&&<span className="cp-plan-good">Каталог завантажено</span>}</div>
     <div className="cp-plan-lookup">
      <button type="button" disabled={paidDisabled} onClick={discover}>{busy?'Завантаження…':'Знайти модифікацію'}</button>
      {picked>0&&<button type="button" className="secondary" disabled={paidDisabled} onClick={getCategories}>{categories.length?'Оновити каталог':'Завантажити каталог'}</button>}
      <button type="button" className="secondary cp-plan-text-button" onClick={()=>setShowTechnical(v=>!v)} aria-expanded={showTechnical}>Технічні деталі {showTechnical?'▴':'▾'}</button>
     </div>
     {matches.length>0&&<div className="cp-plan-match"><label htmlFor="cp-plan-modification">Оберіть модифікацію</label><select id="cp-plan-modification" disabled={busy} value={picked} onChange={e=>selectKtype(Number(e.target.value))}><option value={0}>Оберіть модифікацію</option>{matches.map(m=><option key={m.ktype} value={m.ktype}>{m.modification} · {m.year_from??'—'}–{m.year_to??'дотепер'} · {m.power_kw??'—'} кВт · K-Type {m.ktype}</option>)}</select>{picked>0&&savedKtype!==picked&&<button type="button" disabled={busy} onClick={saveModification}>Підтвердити модифікацію</button>}</div>}
     {showTechnical&&<div className="cp-plan-tech"><p>Поточний K-Type: <strong>{picked||'—'}</strong>. Збережений: <strong>{savedKtype||'—'}</strong>. Дані Plan.Parts належать конкретній модифікації; перевірте двигун та КПП.</p><p>Для завантаження артикулів потрібний окремий платний запит. Повторні дані можуть надходити з кешу.</p></div>}
     {busy&&<p role="status">Отримуємо дані каталогу…</p>}
     {secondsLeft>0&&<p role="status">Наступний платний запит доступний через {secondsLeft} с.</p>}
     {error&&<p role="alert" className="cp-plan-error">{error}</p>}
    </div>
    <div className="cp-plan-panel">
     <div className="cp-plan-heading"><h3>2. Підібрані запчастини</h3>{categories.length>0&&<small>{filteredCategories.length} із {categories.length}</small>}</div>
     <div className="cp-plan-filters">
      <input aria-label="Пошук запчастин" placeholder="Пошук запчастини або типу…" value={partQuery} onChange={e=>setPartQuery(e.target.value)}/>
      <select aria-label="Категорія" value={onlyCategory} onChange={e=>setOnlyCategory(e.target.value)}><option value="all">Усі категорії</option>{[...new Set(categories.map(sectionOf))].sort((a,b)=>a.localeCompare(b,"uk")).map(group=><option key={group} value={group}>{group}</option>)}</select>
      <select aria-label="Статус" value={stockFilter} onChange={e=>setStockFilter(e.target.value)}><option value="all">Усі статуси</option><option value="new">Не на складі</option><option value="stored">Вже на складі</option></select>
     </div>
     {categories.length>0?<><div className="cp-plan-select-actions"><button type="button" className="secondary" onClick={()=>setSelectedTypes(categories.map(c=>c.pt_id))}>Вибрати всі</button><button type="button" className="secondary" onClick={()=>setSelectedTypes([])}>Зняти вибір</button><small>Вибрано: {selectedTypes.length}</small></div>
      {stockStatusError&&<p role="alert" className="cp-plan-error">{stockStatusError}</p>}
      {duplicateStockNames.length>0&&<p role="alert" className="cp-plan-error">У складі виявлено дублікати: {duplicateStockNames.map(d=>d.name+' ('+d.count+')').join(', ')}. Автоматичне видалення вимкнено.</p>}
      <div className="cp-plan-list">
       {[...new Set(filteredCategories.map(sectionOf))].sort((a,b)=>a.localeCompare(b,'uk')).map(group=>{
        const groupParts=filteredCategories.filter(c=>sectionOf(c)===group);
        const pending=groupParts.filter(c=>!alreadyStored(c));
        const groupSelected=pending.filter(c=>selectedTypes.includes(c.pt_id));
        return <section key={group} className="cp-plan-group">
         <div className="cp-plan-group-heading">
          <div><strong>{group}</strong><small>{groupParts.length} типів · доступні до додавання: {pending.length}</small></div>
          <button type="button" className="secondary" disabled={!pending.length||batchBusy||addingType!==null} onClick={()=>{
           const ids=new Set(pending.map(c=>c.pt_id));
           setSelectedTypes(old=>groupSelected.length===pending.length?old.filter(id=>!ids.has(id)):[...new Set([...old,...ids])]);
          }}>{pending.length&&groupSelected.length===pending.length?'Зняти вибір категорії':'Вибрати всю категорію'}</button>
         </div>
         {groupParts.map(c=>{const stored=alreadyStored(c);const localized=localizedName(c.name);return <div key={c.pt_id} className="cp-plan-part">
          <label className="cp-plan-part-name"><input type="checkbox" checked={selectedTypes.includes(c.pt_id)} onChange={e=>setSelectedTypes(old=>e.target.checked?[...new Set([...old,c.pt_id])]:old.filter(id=>id!==c.pt_id))}/><span><strong>{localized}</strong><small>{c.name!==localized?c.name:'Тип '+c.pt_id}</small></span></label>
          <span className="cp-plan-part-tag">{sectionOf(c)}</span>
          <span className={stored?'cp-plan-status is-stored':'cp-plan-status'}>{stored?'На складі · '+stored.quantity+' шт.':'Нове'}</span>
          <button type="button" className={stored?'secondary':'cp-plan-add'} disabled={addingType!==null||batchBusy||stockStatusLoading||Boolean(stockStatusError)||savedKtype!==picked||Boolean(stored)} onClick={()=>void addSelectedType(c)}>{stored?'Вже на складі':addingType===c.pt_id?'Додаємо…':'Додати на склад'}</button>
          <button type="button" className="secondary" disabled={paidDisabled} onClick={()=>getArticles(c.pt_id)}>Артикули</button>
         </div>})}
        </section>;
       })}
       {filteredCategories.length===0&&<p className="cp-plan-empty">За заданими фільтрами запчастин не знайдено.</p>}
      </div>
     </>:<div className="cp-plan-empty">Оберіть модифікацію та завантажте каталог, щоб побачити перелік запчастин.</div>}
     {addMessage&&<p role="status" aria-live="polite">{addMessage}</p>}
    </div>
    {phase==='articles'&&<div className="cp-plan-panel">
     <h3>Артикули: {selected?localizedName(selected.name):'Запчастина'} ({articles.length})</h3>
     <div className="cp-plan-article-scroll"><table><thead><tr><th>Деталь</th><th>Виробник</th><th>Артикул</th></tr></thead><tbody>{articles.slice(0,showAll?articles.length:80).map(a=><tr key={a.art_id}><td>{a.part_name?localizedName(a.part_name):(selected?localizedName(selected.name):'Деталь')}</td><td>{a.brand}</td><td>{a.article_nr}</td></tr>)}</tbody></table></div>
     {!showAll&&articles.length>80&&<button type="button" className="secondary" onClick={()=>setShowAll(true)}>Показати решту артикулів</button>}
    </div>}
    {categories.length>0&&<div className="cp-plan-panel cp-plan-maintenance">
     <button type="button" className="secondary" aria-expanded={showArticleTools} onClick={()=>setShowArticleTools(v=>!v)}>Масове отримання артикулів {showArticleTools?'▴':'▾'}</button>
     {showArticleTools&&<div><p>Вибрано {selectedTypes.length} типів · {selectedOffers.toLocaleString('uk-UA')} пропозицій · орієнтовно до {estimatedTokens} токенів. Запити виконуються тільки після вашої дії.</p><PlanPartsBatch key={picked} vehicleId={String(vehicle.id)} ktype={picked} selected={selectedCategories} disabled={busy||savedKtype!==picked} translatedNames={machineNames}/></div>}
     <button type="button" className="secondary" aria-expanded={showMaintenance} onClick={()=>setShowMaintenance(v=>!v)}>Сервісні операції {showMaintenance?'▴':'▾'}</button>
     {showMaintenance&&<div className="cp-plan-tools">
      <button type="button" className="secondary" disabled={translationLoading} onClick={()=>void translateAllCategories()}>{translationLoading?'Перекладаємо…':'Оновити українські назви'}</button>{translationStatus&&<p role="status">{translationStatus}</p>}
      <button type="button" className="secondary" disabled={stockStatusLoading} onClick={()=>void refreshStockStatus()}>Оновити статус складу</button>
      <button type="button" className="secondary" disabled={addingType!==null||savedKtype!==picked} onClick={()=>void receivePreviousSelections()}>Оприбуткувати раніше додані</button>
      <button type="button" className="secondary" disabled={classLoading||savedKtype!==picked} onClick={()=>void previewStockClassification()}>Перевірити категорії складу</button>
      {classificationPreview&&<><p>Для класифікації: {classificationPreview.can_apply}; потребують перевірки: {classificationPreview.needs_review}.</p><button type="button" disabled={classLoading||!classificationPreview.can_apply} onClick={()=>void applyStockClassification()}>Застосувати перевірені категорії</button></>}
      {classMessage&&<p role="status">{classMessage}</p>}
     </div>}
    </div>}
   </div>
   <aside className="cp-plan-summary">
    <h3>3. Дії</h3>
    <div className="cp-plan-summary-lines">
     <div><span>Обрано</span><strong>{selectedTypes.length} типів</strong></div>
     <div><span>Готово до додавання</span><strong>{chosenNew}</strong></div>
     <div><span>Вже на складі</span><strong>{categories.filter(c=>Boolean(alreadyStored(c))).length}</strong></div>
     <div><span>Режим</span><strong>plan.parts API</strong></div>
    </div>
    {batchBusy&&<div role="status" className="cp-plan-batch-status">Опрацьовано: {batchProgress} <button type="button" className="secondary" onClick={()=>{stopBatch.current=true;}}>Зупинити після поточної групи</button></div>}
    {confirmBatch&&<div role="alertdialog" aria-label="Підтвердження додавання на склад" className="cp-plan-confirm">
     <strong>Додати {chosenNew} вибраних типів на склад?</strong>
     <p>Кожна нова запчастина матиме залишок 1 шт. Повторні записи не створюються. Токени plan.parts не витрачаються.</p>
     <button type="button" onClick={()=>void addSelectedToStock()}>Підтвердити</button>
     <button type="button" className="secondary" onClick={()=>setConfirmBatch(false)}>Скасувати</button>
    </div>}
    <button type="button" className="cp-plan-bulk" disabled={!chosenNew||batchBusy||addingType!==null||savedKtype!==picked||stockStatusLoading||Boolean(stockStatusError)} onClick={()=>setConfirmBatch(true)}>{batchBusy?'Додаємо…':'＋ Додати вибрані на склад'}</button>
    <a className="cp-plan-stock-link" href="/inventory">Відкрити склад</a>
    <p className="cp-plan-summary-note">Запчастини додаються з кількістю 1. Повторне оприбуткування вже наявних позицій заблоковано.</p>
   </aside>
  </div>
 </section>;
}
