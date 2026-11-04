import {useCallback,useContext,useEffect,useMemo,useRef,useState} from 'react';
import {TeamIdentity} from './permissions';
import {api,ApiError,type Row} from './api';
import {ukrainianPartName} from './planPartsUkrainian';
import ArticleManager from './ArticleManager';
import {sections as corporateSections} from './PartsQuickCategories';
import {Boxes, LoaderCircle} from 'lucide-react';
import './plan-parts-workspace.css';

type Match={ktype:number;modification:string;year_from?:number;year_to?:number;power_kw?:number;power_ps?:number};
type Category={pt_id:number;name:string;article_count:number};

export default function PlanPartsDonorAnalysis({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const donorId=encodeURIComponent(String(vehicle.id));
 const [matches,setMatches]=useState<Match[]>([]);
 const [partQuery,setPartQuery]=useState('');
 const [stockFilter,setStockFilter]=useState('all');
 const [onlyCategory,setOnlyCategory]=useState('all');
 const [visibleLimit,setVisibleLimit]=useState(60);
 const [showTechnical,setShowTechnical]=useState(false);
 const [showMaintenance,setShowMaintenance]=useState(false);
 const [showStockList,setShowStockList]=useState(false);
 const [batchBusy,setBatchBusy]=useState(false);
 const [confirmBatch,setConfirmBatch]=useState(false);
 const [batchProgress,setBatchProgress]=useState(0);
 const [batchTotal,setBatchTotal]=useState(0);
 const [batchGroup,setBatchGroup]=useState('');
 const stopBatch=useRef(false);
 const [picked,setPicked]=useState<number>(Number(vehicle.ktype)||0);
 const [savedKtype,setSavedKtype]=useState<number>(Number(vehicle.ktype)||0);
 const [selectedTypes,setSelectedTypes]=useState<number[]>([]);
 const [categories,setCategories]=useState<Category[]>([]);
 const [catalogueSaved,setCatalogueSaved]=useState(false);
 const [machineNames,setMachineNames]=useState<Record<string,string>>({});
 const [translationStatus,setTranslationStatus]=useState('');
 const [translationLoading,setTranslationLoading]=useState(false);
 const [addingType,setAddingType]=useState<number|null>(null);
 type StoredPart={id:string;pt_id:number|null;name:string;quantity:number;archived:boolean;article_number?:string};
 const [stockParts,setStockParts]=useState<StoredPart[]>([]);
 const [duplicateStockNames,setDuplicateStockNames]=useState<{name:string;count:number}[]>([]);
 const [stockStatusLoading,setStockStatusLoading]=useState(false);
 const [stockStatusError,setStockStatusError]=useState('');
 const nameKey=(s:string)=>s.trim().toLocaleLowerCase('uk-UA').replace(/\s+/g,' ');
 // Index actual stock once. A linear scan for every displayed row was expensive.
 const storedIndex=useMemo(()=>{
  const byType=new Map<number,StoredPart>(),byName=new Map<string,StoredPart>();
  for(const part of stockParts){if(part.archived)continue;
   if(part.pt_id!==null&&!byType.has(part.pt_id))byType.set(part.pt_id,part);
   const key=nameKey(part.name);if(!byName.has(key))byName.set(key,part);
  }
  return {byType,byName};
 },[stockParts]);
 const alreadyStored=(c:Category)=>storedIndex.byType.get(c.pt_id)||storedIndex.byName.get(nameKey(localizedName(c.name)));
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

 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const gate=useRef(false);
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
   setCatalogueSaved(true);
   setSelectedTypes([]);
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
  setMatches(result.matches);
  if(!result.matches.length)setError('Точних кандидатів за маркою, моделлю та роком немає. Уточніть автомобіль.');
 });}
 function selectKtype(ktype:number){
  setPicked(ktype);setCategories([]);setSelectedTypes([]);
 }
 function getCategories(){if(!picked)return;void run(async()=>{
  const result=await api<{categories:Category[];from_saved?:boolean}>('/plan-parts/categories/lookup?vehicle_id='+donorId+'&ktype='+picked,'POST');
  setCategories(result.categories);setCatalogueSaved(Boolean(result.from_saved));setSelectedTypes([]);
  try{sessionStorage.setItem(categoryScope,JSON.stringify({until:Date.now()+30*60*1000,categories:result.categories}));}catch{/* optional */}
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
 const localizedName=useCallback((name:string)=>{
  const reviewed=ukrainianPartName(name);
  return reviewed.translated?reviewed.uk:(machineNames[name]||reviewed.uk);
 },[machineNames]);
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
 async function addSelectedToStock(){
  if(addLock.current||batchBusy||!picked||picked!==savedKtype||stockStatusError||stockStatusLoading)return;
  const pending=categories.filter(c=>selectedTypes.includes(c.pt_id)&&!alreadyStored(c));
  setConfirmBatch(false);
  if(!pending.length){setAddMessage('Нових вибраних запчастин немає.');return;}
  addLock.current=true;stopBatch.current=false;setBatchBusy(true);setBatchProgress(0);setBatchTotal(pending.length);setBatchGroup('Підготовка запчастин');
  let done=0;
  try{
   for(let offset=0;offset<pending.length;offset+=20){
    if(stopBatch.current)break;
    const subset=pending.slice(offset,offset+20);
    setBatchGroup('Оприбуткування · група '+(Math.floor(offset/20)+1)+' із '+Math.ceil(pending.length/20));
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
  if(/tool|puller|інструмент|знімач|fluid|антифриз|паста для|олива|lubricant/.test(raw))return 'Обладнання та витратні матеріали';
  if(/brake|гальм|супорт|колодк/.test(raw))return 'Гальмівна система';
  if(/steering|кермов|рульов/.test(raw))return 'Кермове управління';
  if(/suspension|shock absorber|strut|стабілізатор|підвіск|амортиз|кульов.{0,5}опор/.test(raw))return 'Підвіска та ходова частина';
  if(/headlight|bulb|tail light|direction indicator|lamp|фар|ламп|ліхтар|освітл/.test(raw))return 'Освітлення';
  if(/air conditioning|heater|клімат|кондиціон|обігрів|пічк/.test(raw))return 'Кліматична система';
  if(/transmission|gearbox|drive shaft|differential|трансміс|шрус|диференціал|коробк.{0,9}передач/.test(raw))return 'Трансмісія та привід';
  if(/airbag|seat belt|подушк.{0,10}безпек|ремен.{0,10}безпек/.test(raw))return 'Системи безпеки';
  if(/seat|dashboard|interior|килимок|салон|сидін|панель приладів/.test(raw))return 'Салон та інтер’єр';
  if(/window|mirror|door|bumper|wing|fender|body panel|кузов|дзеркал|двер|капот|бампер/.test(raw))return 'Кузов та зовнішні деталі';
  if(/sensor|alternator|wiring|relay|starter|battery|датчик|генератор|реле|акумулятор|стартер/.test(raw))return 'Електрика та електроніка';
  if(/fuel|engine|filter|coolant|crankshaft|camshaft|turbo|двигун|палив|фільтр|охолодж|турбін/.test(raw))return 'Двигун та його системи';
  return 'Потребують уточнення';
 };

 const selectedSet=useMemo(()=>new Set(selectedTypes),[selectedTypes]);
 // These labels and sections are invariant while selecting/checking boxes.
 const preparedCategories=useMemo(()=>categories.map(c=>({
  category:c,
  localized:localizedName(c.name),
  section:sectionOf(c)
 // Intentionally recompute only after catalogue or translations change.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 })),[categories,machineNames]);
 const sectionIndex=useMemo(()=>new Map(preparedCategories.map(x=>[x.category.pt_id,x.section])),[preparedCategories]);
 const sectionOfCached=(c:Category)=>sectionIndex.get(c.pt_id)||'Потребують уточнення';
 const filteredCategories=useMemo(()=>{
  const query=partQuery.trim().toLocaleLowerCase('uk-UA');
  return preparedCategories.filter(x=>{
   const stored=storedIndex.byType.get(x.category.pt_id)||storedIndex.byName.get(nameKey(x.localized));
   return (!query||x.localized.toLocaleLowerCase('uk-UA').includes(query)||x.category.name.toLocaleLowerCase().includes(query)||String(x.category.pt_id).includes(query))
    &&(stockFilter==='all'||(stockFilter==='stored'?Boolean(stored):!stored))
    &&(onlyCategory==='all'||x.section===onlyCategory);
  }).map(x=>x.category);
 },[preparedCategories,partQuery,stockFilter,onlyCategory,storedIndex]);
 const chosenNew=useMemo(()=>categories.filter(c=>selectedSet.has(c.pt_id)&&!alreadyStored(c)).length,[categories,selectedSet,storedIndex,machineNames]);
 const visibleCategories=filteredCategories.slice(0,visibleLimit);
 const visibleGroups=useMemo(()=>{
  const groups=new Map<string,Category[]>();
  for(const c of visibleCategories){
   const key=sectionOfCached(c);
   const existing=groups.get(key);
   if(existing)existing.push(c);else groups.set(key,[c]);
  }
  return [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],'uk'));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[filteredCategories,visibleLimit,sectionIndex]);
 useEffect(()=>{setVisibleLimit(60)},[onlyCategory,partQuery,stockFilter,picked]);
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
     <div className="cp-plan-metrics"><span>{categories.length.toLocaleString('uk-UA')} типів</span><span>{categories.reduce((sum,c)=>sum+c.article_count,0).toLocaleString('uk-UA')} артикулів</span>{categories.length>0&&<span className="cp-plan-good">{catalogueSaved?'Збережений каталог':'Каталог завантажено'}</span>}</div>
     <div className="cp-plan-lookup">
      <button type="button" disabled={paidDisabled} onClick={discover}>{busy?'Завантаження…':'Знайти модифікацію'}</button>
      {picked>0&&<button type="button" className="secondary" disabled={paidDisabled} onClick={getCategories}>{categories.length?'Повторно відкрити список':'Отримати список запчастин'}</button>}
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
     {categories.length>0&&<div className="cp-plan-classify">
      <div><strong>Категорії складу</strong><small>Для раніше доданих запчастин можна зіставити системи CarPot без зміни залишків і цін.</small></div>
      <button type="button" className="secondary" disabled={classLoading||savedKtype!==picked} onClick={()=>void previewStockClassification()}>{classLoading?'Перевірка…':'Перевірити відповідність'}</button>
      {classificationPreview&&<div className="cp-plan-classify-results"><span>Вже розподілені: {classificationPreview.already_categorized}</span><span>Можна розподілити: {classificationPreview.can_apply}</span><span>Потребують перевірки: {classificationPreview.needs_review}</span>
       {classificationPreview.can_apply>0&&<button type="button" disabled={classLoading} onClick={()=>void applyStockClassification()}>Застосувати перевірені ({classificationPreview.can_apply})</button>}
      </div>}
      {classMessage&&<p role="status">{classMessage}</p>}
     </div>}
     {categories.length>0&&<section className="cp-plan-corporate" aria-label="Швидкий вибір категорії">
      <h4>Швидкий вибір категорії</h4>
      <div className="cp-plan-corporate-tiles">
       <button type="button" aria-pressed={onlyCategory==='all'} className={'cp-plan-corporate-tile'+(onlyCategory==='all'?' selected':'')} onClick={()=>setOnlyCategory('all')}><Boxes size={22} strokeWidth={1.7} aria-hidden="true"/><span>Усі категорії</span></button>
       {corporateSections.map(section=>{const Icon=section.icon;return <button type="button" key={section.name} aria-pressed={onlyCategory===section.name} className={'cp-plan-corporate-tile'+(onlyCategory===section.name?' selected':'')} onClick={()=>setOnlyCategory(section.name)}><Icon size={22} strokeWidth={1.7} aria-hidden="true"/><span>{section.name}</span></button>})}
      </div>
     </section>}
     <div className="cp-plan-filters">
      <input aria-label="Пошук запчастин" placeholder="Пошук запчастини або типу…" value={partQuery} onChange={e=>setPartQuery(e.target.value)}/>
      
      <select aria-label="Статус" value={stockFilter} onChange={e=>setStockFilter(e.target.value)}><option value="all">Усі статуси</option><option value="new">Не на складі</option><option value="stored">Вже на складі</option></select>
     </div>
     {categories.length>0&&<ArticleManager key={picked} vehicleId={String(vehicle.id)} vehicleLabel={`${vehicle.manufacturer||''} ${vehicle.model||''} · ${vehicle.year||'—'} · Донор №${vehicle.number||'—'}`} ktype={picked} categories={categories} stockIndex={storedIndex} localizedName={localizedName} onSaved={refreshStockStatus} translatedNames={machineNames} disabled={paidDisabled||batchBusy||Boolean(stockStatusError)||savedKtype!==picked}/>}
     <div className="cp-plan-stock-disclosure"><div><strong>Перелік запчастин для розбору та оприбуткування</strong><small>Окремо від менеджера артикулів. Тут вибирають фізичні позиції для додавання на склад.</small></div><button type="button" className="secondary" aria-expanded={showStockList} onClick={()=>setShowStockList(v=>!v)}>{showStockList?'Згорнути перелік':'Відкрити перелік запчастин'}</button></div>
     {showStockList&&<div className="cp-plan-stock-workspace">
     {categories.length>0?<><div className="cp-plan-select-actions"><button type="button" className="secondary" onClick={()=>setSelectedTypes(categories.map(c=>c.pt_id))}>Вибрати всі</button><button type="button" className="secondary" onClick={()=>setSelectedTypes([])}>Зняти вибір</button><small>Вибрано: {selectedTypes.length}</small></div>
      {stockStatusError&&<p role="alert" className="cp-plan-error">{stockStatusError}</p>}
      {duplicateStockNames.length>0&&<p role="alert" className="cp-plan-error">У складі виявлено дублікати: {duplicateStockNames.map(d=>d.name+' ('+d.count+')').join(', ')}. Автоматичне видалення вимкнено.</p>}
      <div className="cp-plan-list">
       {visibleGroups.map(([group,groupParts])=>{
        const pending=filteredCategories.filter(c=>sectionOfCached(c)===group&&!alreadyStored(c));
        const groupSelected=pending.filter(c=>selectedSet.has(c.pt_id));
        return <section key={group} className="cp-plan-group">
         <div className="cp-plan-group-heading">
          <div><strong>{group}</strong><small>{groupParts.length} типів · доступні до додавання: {pending.length}</small></div>
          <button type="button" className="secondary" disabled={!pending.length||batchBusy||addingType!==null} onClick={()=>{
           const ids=new Set(pending.map(c=>c.pt_id));
           setSelectedTypes(old=>groupSelected.length===pending.length?old.filter(id=>!ids.has(id)):[...new Set([...old,...ids])]);
          }}>{pending.length&&groupSelected.length===pending.length?'Зняти вибір категорії':'Вибрати всю категорію'}</button>
         </div>
         {groupParts.map(c=>{const stored=alreadyStored(c);const localized=localizedName(c.name);return <div key={c.pt_id} className="cp-plan-part">
          <label className="cp-plan-part-name"><input type="checkbox" checked={selectedSet.has(c.pt_id)} onChange={e=>setSelectedTypes(old=>e.target.checked?[...new Set([...old,c.pt_id])]:old.filter(id=>id!==c.pt_id))}/><span><strong>{localized}</strong><small>{c.name!==localized?c.name:'Тип '+c.pt_id}</small></span></label>
          <span className="cp-plan-part-tag">{sectionOfCached(c)}</span>
          <span className={stored?'cp-plan-status is-stored':'cp-plan-status'}>{stored?'На складі · '+stored.quantity+' шт.':'Нове'}</span>
          <button type="button" className={stored?'secondary':'cp-plan-add'} disabled={addingType!==null||batchBusy||stockStatusLoading||Boolean(stockStatusError)||savedKtype!==picked||Boolean(stored)} onClick={()=>void addSelectedType(c)}>{stored?'Вже на складі':addingType===c.pt_id?'Додаємо…':'Додати на склад'}</button>
          {stored?.article_number?<span className="cp-plan-known-article" title="Артикул записаний у картку складу">{stored.article_number}</span>:<span className="cp-plan-article-hint">Артикул — у менеджері вище</span>}
         </div>})}
        </section>;
       })}
       {filteredCategories.length===0&&<p className="cp-plan-empty">За заданими фільтрами запчастин не знайдено.</p>}
      </div>
      {filteredCategories.length>visibleLimit&&<div className="cp-plan-load-more"><span>Показано {Math.min(visibleLimit,filteredCategories.length)} із {filteredCategories.length} типів. Вибір усієї категорії діє на повний перелік.</span><button type="button" className="secondary" onClick={()=>setVisibleLimit(v=>v+60)}>Показати ще 60</button></div>}
     </>:<div className="cp-plan-empty">Оберіть модифікацію та завантажте каталог, щоб побачити перелік запчастин.</div>}
     {addMessage&&<p role="status" aria-live="polite">{addMessage}</p>}
     </div>}
    </div>
    {categories.length>0&&<div className="cp-plan-panel cp-plan-maintenance">
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
    {batchBusy&&<div role="status" aria-live="polite" className="cp-plan-batch-status">
     <div className="cp-plan-batch-heading"><LoaderCircle className="cp-plan-spinner" size={18}/><strong>Додаємо запчастини на склад</strong><b>{Math.round(batchProgress/Math.max(1,batchTotal)*100)}%</b></div>
     <div className="cp-plan-progress-track" role="progressbar" aria-label="Прогрес оприбуткування" aria-valuemin={0} aria-valuemax={batchTotal} aria-valuenow={batchProgress}><div className="cp-plan-progress-fill" style={{width:Math.min(100,batchProgress/Math.max(1,batchTotal)*100)+'%'}}/></div>
     <p>Опрацьовано <strong>{batchProgress} із {batchTotal}</strong> · {batchGroup}</p>
     <small>Сторінка працює. Додаємо невеликими групами, кожна з перевіркою результату.</small>
     <button type="button" className="secondary" disabled={stopBatch.current} onClick={()=>{stopBatch.current=true;}}>Зупинити після поточної групи</button>
    </div>}
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
