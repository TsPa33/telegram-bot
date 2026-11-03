import {useContext,useEffect,useRef,useState} from 'react';
import {TeamIdentity} from './permissions';
import {api,ApiError,type Row} from './api';
import {ukrainianPartName} from './planPartsUkrainian';
import PlanPartsBatch from './PlanPartsBatch';

type Match={ktype:number;modification:string;year_from?:number;year_to?:number;power_kw?:number;power_ps?:number};
type Category={pt_id:number;name:string;article_count:number};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};

export default function PlanPartsDonorAnalysis({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const donorId=encodeURIComponent(String(vehicle.id));
 const [matches,setMatches]=useState<Match[]>([]);
 const [search,setSearch]=useState('');
 const [stockFilter,setStockFilter]=useState<'all'|'new'|'added'>('all');
 const [sectionFilter,setSectionFilter]=useState('all');
 const [visibleLimit,setVisibleLimit]=useState(70);
 const [confirmBulk,setConfirmBulk]=useState(false);
 const [bulkBusy,setBulkBusy]=useState(false);
 const [bulkDone,setBulkDone]=useState(0);
 const [bulkNotice,setBulkNotice]=useState('');
 const bulkAbort=useRef(false);
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
 const sectionOf=(c:Category)=>{
  const n=(localizedName(c.name)+' '+c.name).toLocaleLowerCase('uk-UA');
  if(/brake|гальм|супорт|колодк/.test(n))return 'Гальмівна система';
  if(/steering|кермов|рульов/.test(n))return 'Кермове керування';
  if(/suspension|strut|shock absorber|підвіск|амортиз|стабілізатор/.test(n))return 'Підвіска і ходова';
  if(/air conditioning|клімат|кондиціон|обігрів/.test(n))return 'Кліматична система';
  if(/bulb|light|indicator|фар|ламп|ліхтар|освітл/.test(n))return 'Освітлення';
  if(/fuel|engine|filter|coolant|crankshaft|двигун|палив|фільтр|охолодж/.test(n))return 'Двигун і системи';
  if(/tool|інструмент|знімач|fluid|олива|паста/.test(n))return 'Обладнання та матеріали';
  if(/transmission|shaft|gearbox|диференціал|трансміс|привідн/.test(n))return 'Трансмісія';
  return 'Інші деталі';
 };
 const filteredCategories=categories.filter(c=>{
  if(search.trim()&&!((localizedName(c.name)+' '+c.name).toLocaleLowerCase('uk-UA').includes(search.trim().toLocaleLowerCase('uk-UA'))))return false;
  if(sectionFilter!=='all'&&sectionOf(c)!==sectionFilter)return false;
  if(stockFilter==='added'&&!alreadyStored(c))return false;
  if(stockFilter==='new'&&alreadyStored(c))return false;
  return true;
 });
 const addedCount=categories.filter(c=>Boolean(alreadyStored(c))).length;
 const selectedToAdd=categories.filter(c=>selectedTypes.includes(c.pt_id)&&!alreadyStored(c));
 const canBulkAdd=savedKtype===picked&&picked>0&&!bulkBusy&&!busy&&!stockStatusLoading&&!stockStatusError&&addingType===null;
 async function addSelectedBatch(){
  if(!canBulkAdd||!selectedToAdd.length)return;
  setConfirmBulk(false);setBulkBusy(true);bulkAbort.current=false;setBulkDone(0);setBulkNotice('');
  let done=0;
  const queue=selectedToAdd.filter(c=>/[А-Яа-яІіЇїЄєҐґ]/.test(localizedName(c.name)));
  const untranslated=selectedToAdd.length-queue.length;
  try{
   for(let i=0;i<queue.length;i+=30){
    if(bulkAbort.current)break;
    const chunk=queue.slice(i,i+30);
    const reply=await api<{results:{pt_id:number;ok:boolean;error?:string}[];attempted:number}>(
     '/plan-parts/donor-parts/add-batch?vehicle_id='+donorId,'POST',
     {items:chunk.map(c=>({ktype:picked,pt_id:c.pt_id,ukrainian_name:localizedName(c.name)}))});
    done+=reply.results.filter(r=>r.ok).length;
    setBulkDone(done);
    if(reply.results.some(r=>!r.ok)||reply.attempted<chunk.length){
     const problem=reply.results.find(r=>!r.ok)?.error||'Пакет перервано';
     throw Error(problem+' Перевірте склад перед повтором.');
    }
   }
   setSelectedTypes([]);
   setBulkNotice('Опрацьовано '+done+' вибраних типів.'+(untranslated?' Неперекладених залишено: '+untranslated+'.':'')+(bulkAbort.current?' Виконання зупинено.':''));
  }catch(e){
   setBulkNotice('Успішно опрацьовано: '+done+'. '+(e as Error).message);
  }finally{
   try{await refreshStockStatus();onSaved(await api('/vehicles/'+donorId));}catch(e){setBulkNotice(v=>v+' Перевірка актуального стану не вдалася: '+(e as Error).message);}
   setBulkBusy(false);
  }
 }
 const selected=categories.find(c=>c.pt_id===activeCategory);
 const selectedCategories=categories.filter(c=>selectedTypes.includes(c.pt_id));
 const estimatedTokens=selectedCategories.length*2;
 const selectedOffers=selectedCategories.reduce((n,c)=>n+c.article_count,0);
 return __REPLACE_JSX__;
}
