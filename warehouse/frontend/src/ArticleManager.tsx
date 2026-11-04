import {useCallback,useContext,useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './api';
import PlanPartsBatch from './PlanPartsBatch';
import {TeamIdentity} from './permissions';
import {AlertCircle,Check,CheckCircle2,ChevronDown,ChevronLeft,ChevronRight,ChevronUp,Layers3,Search,ShieldAlert,X} from 'lucide-react';
import './article-manager.css';

type Category={pt_id:number;name:string;article_count:number};
type StoredPart={id:string;pt_id:number|null;name:string;quantity:number;archived:boolean;article_number?:string;article_brand?:string};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};
type StockIndex={byType:Map<number,StoredPart>;byName:Map<string,StoredPart>};
type Props={vehicleId:string;ktype:number;categories:Category[];stockIndex:StockIndex;
 localizedName:(name:string)=>string;onSaved:()=>Promise<void>;disabled:boolean;translatedNames:Record<string,string>};
type Listed={category:Category;stock:StoredPart;label:string};
type Receipt={pt_id:number;status:'received'|'unavailable'|'uncertain';article_count:number;received_at:string|null;last_checked_at:string};
const norm=(s:string)=>s.trim().toLocaleLowerCase('uk-UA').replace(/\s+/g,' ');
const PAGE_SIZE=12;
const ARTICLE_CACHE_LIMIT=1200000;

export default function ArticleManager({vehicleId,ktype,categories,stockIndex,localizedName,onSaved,disabled,translatedNames}:Props){
 const identity=useContext(TeamIdentity);
 const sharedKey='plan-parts-batch-v1:'+String(identity?.id||'')+':'+vehicleId+':'+ktype+':temporary-articles';
 const [opened,setOpened]=useState(true);
 const [batchOpen,setBatchOpen]=useState(false);
 const [tab,setTab]=useState<'all'|'missing'|'saved'|'available'>('all');
 const [query,setQuery]=useState('');
 const [page,setPage]=useState(0);
 const [selected,setSelected]=useState<number[]>([]);
 const [offers,setOffers]=useState<Record<number,Article[]>>({});
 const [history,setHistory]=useState<Record<number,Receipt>>({});
 const [validated,setValidated]=useState<number[]>([]);
 const [active,setActive]=useState<number|null>(null);
 const [offerQuery,setOfferQuery]=useState('');
 const [chosen,setChosen]=useState<number|null>(null);
 const [chargeConfirm,setChargeConfirm]=useState(false);
 const [saveConfirm,setSaveConfirm]=useState(false);
 const [loading,setLoading]=useState(false);
 const [saving,setSaving]=useState(false);
 const [notice,setNotice]=useState('');
 const [autoQueue,setAutoQueue]=useState<{ptId:number;offer:Article;partId:string}[]|null>(null);
 const [processed,setProcessed]=useState(0);
 const lock=useRef(false);
 const stockRows=useMemo<Listed[]>(()=>categories.flatMap(c=>{
  const stock=stockIndex.byType.get(c.pt_id)||stockIndex.byName.get(norm(localizedName(c.name)));
  return stock&&!stock.archived?[{category:c,stock,label:localizedName(c.name)}]:[];
 }),[categories,stockIndex,localizedName]);
 const byType=useMemo(()=>new Map(stockRows.map(r=>[r.category.pt_id,r])),[stockRows]);
 const selectedSet=useMemo(()=>new Set(selected),[selected]);
 const validatedSet=useMemo(()=>new Set(validated),[validated]);
 const savedCount=stockRows.filter(r=>Boolean(r.stock.article_number?.trim())).length;
 const missingCount=stockRows.length-savedCount;
 const availableCount=stockRows.filter(r=>!r.stock.article_number?.trim()&&(Boolean(offers[r.category.pt_id]?.length)||Boolean(history[r.category.pt_id]?.received_at))).length;
 const rows=useMemo(()=>stockRows.filter(r=>{
  const hasNumber=Boolean(r.stock.article_number?.trim());
  const hasOptions=Boolean(offers[r.category.pt_id]?.length)||Boolean(history[r.category.pt_id]?.received_at);
  return (tab==='all'||(tab==='missing'&&!hasNumber)||(tab==='saved'&&hasNumber)||(tab==='available'&&!hasNumber&&hasOptions))
   &&(!query||norm(r.label).includes(norm(query))||norm(r.stock.article_number||'').includes(norm(query)));
 }),[stockRows,tab,query,offers,history]);
 const pages=Math.max(1,Math.ceil(rows.length/PAGE_SIZE));
 const visible=rows.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
 const selectedMissing=selected.filter(id=>byType.has(id)&&!byType.get(id)?.stock.article_number?.trim());
 const batchCategories=categories.filter(c=>selectedMissing.includes(c.pt_id));
 const activeRow=active===null?null:byType.get(active)||null;
 const activeOffers=active===null?[]:offers[active]||[];
 const matchingOffers=useMemo(()=>activeOffers.filter(a=>!offerQuery||norm(a.article_nr).includes(norm(offerQuery))||norm(a.brand).includes(norm(offerQuery))||norm(a.part_name).includes(norm(offerQuery))),[activeOffers,offerQuery]);
 const chosenOffer=activeOffers.find(a=>a.art_id===chosen)||null;
 const isVerified=active!==null&&validatedSet.has(active);

 useEffect(()=>{setPage(0)},[tab,query]);
 useEffect(()=>{setOffers({});setValidated([]);setSelected([]);setActive(null);setNotice('');setBatchOpen(false);setHistory({});
  void api<{receipts:Receipt[]}>('/plan-parts/articles/history?vehicle_id='+encodeURIComponent(vehicleId)+'&ktype='+ktype)
   .then(result=>setHistory(Object.fromEntries(result.receipts.map(r=>[r.pt_id,r]))))
   .catch(()=>{/* Do not infer unpaid status if history cannot load */});
  try{
   const raw=JSON.parse(sessionStorage.getItem(sharedKey)||'null') as {until?:number;data?:Record<string,Article[]>}|null;
   if(raw?.until&&raw.until>Date.now()&&raw.data){
    const restored:Record<number,Article[]>={};
    for(const [id,records] of Object.entries(raw.data)){
     if(Array.isArray(records)&&records.length)restored[Number(id)]=records;
    }
    setOffers(restored);
   }
  }catch{/* Session cache optional */}
 },[sharedKey]);
 useEffect(()=>{
  if(active===null)return;
  const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!saving){setActive(null);setChargeConfirm(false);setSaveConfirm(false)}};
  window.addEventListener('keydown',onKey);
  return ()=>window.removeEventListener('keydown',onKey);
 },[active,saving]);
 function remember(ptId:number,records:Article[]){
  // Reuse the existing short-lived browser session cache; never claim permanent supplier storage.
  try{
   const old=JSON.parse(sessionStorage.getItem(sharedKey)||'null') as {until?:number;data?:Record<string,Article[]>}|null;
   const data=old?.until&&old.until>Date.now()&&old.data?{...old.data}:{};
   data[String(ptId)]=records;
   const payload=JSON.stringify({until:Date.now()+30*60*1000,data});
   if(payload.length<=ARTICLE_CACHE_LIMIT)sessionStorage.setItem(sharedKey,payload);
  }catch{/* Optional */}
 }
 const dismiss=()=>{if(saving)return;setActive(null);setChosen(null);setChargeConfirm(false);setSaveConfirm(false);setNotice('')};
 const loadFromCache=useCallback(async(ptId:number)=>{
  const result=await api<{articles:Article[]}>('/plan-parts/articles/recover?vehicle_id='+encodeURIComponent(vehicleId)+'&ktype='+ktype+'&pt_id='+ptId,'POST');
  return result.articles;
 },[vehicleId,ktype]);
 async function showDrawer(ptId:number){
  if(saving||loading)return;
  setActive(ptId);setChosen(null);setOfferQuery('');setSaveConfirm(false);setChargeConfirm(false);setNotice('');
  setLoading(true);
  try{
   const records=await loadFromCache(ptId);
   setOffers(prev=>({...prev,[ptId]:records}));
   setHistory(prev=>({...prev,[ptId]:{pt_id:ptId,status:'received',article_count:records.length,received_at:prev[ptId]?.received_at||new Date().toISOString(),last_checked_at:new Date().toISOString()}}));
   setValidated(prev=>[...new Set([...prev,ptId])]);
   remember(ptId,records);
  }catch(e){
   setValidated(prev=>prev.filter(id=>id!==ptId));
   if(history[ptId]?.received_at){setHistory(prev=>({...prev,[ptId]:{...prev[ptId],status:'unavailable'}}));}
   if(offers[ptId]?.length){
    setNotice('Раніше отримані варіанти є в браузері, але серверний кеш недоступний. Повторну оплату не виконуємо автоматично.');
   }else{
    setNotice(history[ptId]?.received_at?'Отримано раніше — дані потребують відновлення. Повторної оплати не було.':'Варіанти недоступні. Перевірте з’єднання; новий платний запит тільки після підтвердження.');
   }
  }finally{setLoading(false)}
 }
 async function requestPaid(){
  if(active===null||disabled||lock.current||saving)return;
  lock.current=true;setLoading(true);setChargeConfirm(false);
  try{
   const result=await api<{articles:Article[]}>('/plan-parts/articles/lookup?vehicle_id='+encodeURIComponent(vehicleId)+'&ktype='+ktype+'&pt_id='+active,'POST');
   setOffers(prev=>({...prev,[active]:result.articles}));
   setHistory(prev=>({...prev,[active]:{pt_id:active,status:'received',article_count:result.articles.length,received_at:new Date().toISOString(),last_checked_at:new Date().toISOString()}}));
   setValidated(prev=>[...new Set([...prev,active])]);
   remember(active,result.articles);
   setNotice('Отримано '+result.articles.length+' варіантів. Оберіть перевірений номер для картки.');
  }catch(e){setNotice('Запит не підтверджено: '+(e as Error).message+'. Не повторюйте платний запит без перевірки кешу.')}
  finally{setLoading(false);lock.current=false}
 }
 async function saveArticle(ptId:number,offer:Article,partId:string){
  return api<{article_number:string}>('/plan-parts/donor-parts/article/select?vehicle_id='+encodeURIComponent(vehicleId),'POST',{
   ktype,pt_id:ptId,art_id:offer.art_id,part_id:partId
  });
 }
 async function assign(){
  if(!activeRow||!chosenOffer||!isVerified||lock.current||saving)return;
  lock.current=true;setSaving(true);setSaveConfirm(false);
  try{
   const result=await saveArticle(activeRow.category.pt_id,chosenOffer,activeRow.stock.id);
   await onSaved();
   setNotice('Артикул '+result.article_number+' записано у картку товару.');
  }catch(e){setNotice('Не вдалося записати артикул: '+(e as Error).message)}
  finally{lock.current=false;setSaving(false)}
 }
 function prepareAuto(){
  const queue=stockRows.filter(r=>selectedSet.has(r.category.pt_id)&&!r.stock.article_number?.trim()&&validatedSet.has(r.category.pt_id))
   .flatMap(r=>{const a=offers[r.category.pt_id]?.find(x=>x.article_nr.trim());return a?[{ptId:r.category.pt_id,offer:a,partId:r.stock.id}]:[]});
  if(!queue.length){setNotice('Немає вибраних запчастин із перевіреними варіантами. Спочатку відкрийте варіанти — нових платних запитів не буде.');return}
  setAutoQueue(queue);setProcessed(0);
 }
 async function confirmAuto(){
  if(!autoQueue||lock.current)return;
  lock.current=true;setSaving(true);let done=0;
  try{
   for(const item of autoQueue){
    await saveArticle(item.ptId,item.offer,item.partId);
    done++;setProcessed(done);
   }
   await onSaved();setNotice('Записано '+done+' артикулів. Перевірте сумісність фізичних деталей.');
  }catch(e){await onSaved().catch(()=>{});setNotice('Збережено '+done+' із '+autoQueue.length+'. '+(e as Error).message+'. Перевірте картки перед повтором.')}
  finally{setAutoQueue(null);setSaving(false);lock.current=false}
 }
 return <section className="cp-am" aria-label="Менеджер артикулів">
  <button type="button" className="cp-am-toggle" aria-expanded={opened} onClick={()=>setOpened(v=>!v)}>
   <Layers3 size={20}/><strong>Менеджер артикулів</strong><span>Вибір і запис номера в картку запчастини</span>{opened?<ChevronUp size={19}/>:<ChevronDown size={19}/>}
  </button>
  {opened&&<div className="cp-am-content">
   <div className="cp-am-stats">
    <div><small>Запчастин на складі</small><strong>{stockRows.length}</strong></div>
    <div><small>Артикул призначено</small><strong>{savedCount}</strong></div>
    <div><small>Без артикула</small><strong>{missingCount}</strong></div>
    <div><small>Варіанти в сесії</small><strong>{availableCount}</strong></div>
   </div>
   <div className="cp-am-status-tabs" role="group" aria-label="Фільтр артикулів">
    {([{id:'all',label:'Усі'},{id:'missing',label:'Без артикула'},{id:'saved',label:'Є артикул'},{id:'available',label:'Отримані варіанти'}] as const).map(t=><button type="button" key={t.id} className={tab===t.id?'selected':'secondary'} aria-pressed={tab===t.id} onClick={()=>setTab(t.id)}>{t.label} ({t.id==='all'?stockRows.length:t.id==='missing'?missingCount:t.id==='saved'?savedCount:availableCount})</button>)}
   </div>
   <div className="cp-am-toolbar">
    <button type="button" className="secondary" onClick={()=>setSelected(rows.filter(r=>!r.stock.article_number?.trim()).map(r=>r.category.pt_id))}>Вибрати без артикула</button>
    <button type="button" className="secondary" onClick={()=>setSelected([])}>Зняти вибір</button>
    <button type="button" className="secondary" disabled={!selectedMissing.length||saving} aria-expanded={batchOpen} onClick={()=>setBatchOpen(v=>!v)}>{batchOpen?'Згорнути пакетне отримання':'Отримати вибрані · до '+selectedMissing.length*2+' токенів'}</button>
    <button type="button" className="secondary" disabled={!selectedMissing.length||saving} onClick={prepareAuto}>Автовибір з отриманих</button>
    <input aria-label="Пошук у менеджері" placeholder="Назва або артикул…" value={query} onChange={e=>setQuery(e.target.value)}/>
   </div>
   {batchOpen&&<div className="cp-am-batch-workspace"><div className="cp-am-batch-head"><div><strong>Пакетне отримання артикулів</strong><small>Вибрано {batchCategories.length} типів. Нові запити виконуються тільки після підтвердження бюджету токенів.</small></div><button type="button" className="secondary" onClick={()=>setBatchOpen(false)}>Згорнути</button></div><PlanPartsBatch vehicleId={vehicleId} ktype={ktype} selected={batchCategories} disabled={disabled||saving} translatedNames={translatedNames} onArticles={(ptId,records)=>{setHistory(prev=>({...prev,[ptId]:{pt_id:ptId,status:'received',article_count:records.length,received_at:new Date().toISOString(),last_checked_at:new Date().toISOString()}}));setOffers(prev=>({...prev,[ptId]:records}));setValidated(prev=>[...new Set([...prev,ptId])]);remember(ptId,records);}}/></div>}
   {notice&&<p role="status" className="cp-am-message">{notice}</p>}
   {autoQueue&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження автопризначення"><strong>Призначити по одному артикулу для {autoQueue.length} позицій?</strong><p>Це перша доступна aftermarket-пропозиція, а не підтверджений OEM. Перевірте сумісність. Жодного нового платного запиту не буде.</p>{saving&&<progress value={processed} max={autoQueue.length}/>}<button type="button" disabled={saving} onClick={()=>void confirmAuto()}>Підтвердити</button><button type="button" className="secondary" disabled={saving} onClick={()=>setAutoQueue(null)}>Скасувати</button></div>}
   <div className="cp-am-table-wrap"><table className="cp-am-table"><thead><tr><th><span className="cp-am-visually-hidden">Вибір</span></th><th>Запчастина</th><th>Статус</th><th>Артикул</th><th>Дії</th></tr></thead><tbody>
    {visible.map(r=>{const id=r.category.pt_id;const assigned=Boolean(r.stock.article_number?.trim());const available=Boolean(offers[id]?.length);const previously=Boolean(history[id]?.received_at);return <tr key={id} className={active===id?'cp-am-row-active':undefined}>
     <td><input type="checkbox" aria-label={'Вибрати '+r.label} checked={selectedSet.has(id)} onChange={e=>setSelected(prev=>e.target.checked?[...new Set([...prev,id])]:prev.filter(x=>x!==id))}/></td>
     <td><strong>{r.label}</strong><small>{r.category.name!==r.label?r.category.name:'Тип '+id}</small></td>
     <td>{assigned?<span className="cp-am-status yes"><CheckCircle2 size={14}/> Артикул додано</span>:available?<span className="cp-am-status available"><Layers3 size={14}/> Варіанти ({offers[id].length})</span>:previously?<span className="cp-am-status previously"><Layers3 size={14}/> Отримано раніше · відновити</span>:<span className="cp-am-status no"><AlertCircle size={14}/> Не отримано</span>}</td>
     <td><strong>{r.stock.article_number||'—'}</strong></td>
     <td><button type="button" className="secondary" onClick={()=>void showDrawer(id)} disabled={saving||loading}>{assigned?'Переглянути / змінити':available?'Обрати артикул':previously?'Спробувати відновити':'Отримати · до 2 токенів'}</button></td>
    </tr>})}
    {!visible.length&&<tr><td colSpan={5}>Запчастин за цими фільтрами немає.</td></tr>}
   </tbody></table></div>
   <div className="cp-am-footer"><span>Показано {Math.min((page+1)*PAGE_SIZE,rows.length)} із {rows.length}</span><button type="button" className="secondary" disabled={page===0} onClick={()=>setPage(v=>v-1)}><ChevronLeft size={15}/> Назад</button><span>{page+1}/{pages}</span><button type="button" className="secondary" disabled={page+1>=pages} onClick={()=>setPage(v=>v+1)}>Далі <ChevronRight size={15}/></button></div>
  </div>}
  {activeRow&&createPortal(<div className="cp-am-drawer-root" role="presentation">
    <button type="button" className="cp-am-backdrop" aria-label="Закрити вибір артикула" onClick={dismiss}/>
    <aside className="cp-am-drawer" role="dialog" aria-modal="true" aria-label={'Артикули: '+activeRow.label}>
     <header className="cp-am-drawer-head"><div><small>CarPot Warehouse · Артикули</small><h3>{activeRow.label}</h3><p>Тип #{activeRow.category.pt_id} · K-Type {ktype}</p></div><button type="button" className="secondary" aria-label="Закрити" disabled={saving} onClick={dismiss}><X size={19}/></button></header>
     <div className="cp-am-drawer-scroll">
      <div className="cp-am-current"><small>Поточний артикул</small>{activeRow.stock.article_number?.trim()?<strong><CheckCircle2 size={17}/> {activeRow.stock.article_number}</strong>:<strong>Артикул не призначено</strong>}<span>Після призначення номер збережеться в картці товару.</span></div>
      <div className="cp-am-drawer-summary"><Layers3 size={20}/><div><strong>{loading?'Перевіряємо отримані варіанти…':activeOffers.length?'Отримано '+activeOffers.length+' варіантів':active!==null&&history[active]?.received_at?'Отримано раніше — потрібне відновлення':'Варіантів поки немає'}</strong><small>{isVerified?'Серверний кеш підтверджений · запис доступний':activeOffers.length?'Варіанти збережені в сесії · потрібна перевірка сервера':'Запит до Plan.Parts лише після підтвердження'}</small></div></div>
      {notice&&<p role="status" className="cp-am-message">{notice}</p>}
      {!isVerified&&!loading&&<div className="cp-am-warning"><ShieldAlert size={18}/><span>Для запису нового номера потрібні перевірені варіанти в серверному кеші. Повторний платний запит не запускається автоматично.</span></div>}
      {chargeConfirm&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження оплати"><strong>Отримати нові варіанти · до 2 токенів?</strong><p>Plan.Parts може списати токени. Вибір артикула після отримання залишається безкоштовним.</p><button type="button" disabled={disabled||loading||saving} onClick={()=>void requestPaid()}>Підтвердити запит</button><button type="button" className="secondary" onClick={()=>setChargeConfirm(false)}>Скасувати</button></div>}
      <div className="cp-am-drawer-list-head"><h4>Варіанти артикулів</h4><span>{matchingOffers.length} результатів</span></div>
      <label className="cp-am-search"><Search size={17}/><input value={offerQuery} onChange={e=>setOfferQuery(e.target.value)} placeholder="Пошук за артикулом або виробником…" aria-label="Пошук артикулів"/></label>
      <div className="cp-am-drawer-offers">
       {matchingOffers.slice(0,100).map(a=><label className={'cp-am-offer'+(chosen===a.art_id?' chosen':'')} key={a.art_id}>
        <input type="radio" name="cp-am-offer" checked={chosen===a.art_id} onChange={()=>setChosen(a.art_id)}/>
        <span><strong>{a.article_nr}</strong><small>{a.brand} · {a.part_name}</small></span>
        {activeRow.stock.article_number===a.article_nr&&<span className="cp-am-already"><Check size={13}/> Збережено</span>}
       </label>)}
       {matchingOffers.length>100&&<p>Показано перші 100 із {matchingOffers.length}. Уточніть пошук за номером або виробником.</p>}
       {!matchingOffers.length&&<p>{loading?'Завантаження…':'За запитом варіантів немає.'}</p>}
      </div>
      {saveConfirm&&chosenOffer&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження запису"><strong>Призначити {chosenOffer.article_nr}?</strong><p>Виробник: {chosenOffer.brand}. Це aftermarket-номер, сумісність із фізичною деталлю та VIN не підтверджена.</p><button type="button" disabled={saving} onClick={()=>void assign()}>{saving?'Записуємо…':'Записати у картку'}</button><button type="button" className="secondary" onClick={()=>setSaveConfirm(false)}>Скасувати</button></div>}
     </div>
     <footer className="cp-am-drawer-footer"><p><AlertCircle size={15}/> Артикул потрібно звірити з реальною запчастиною.</p><div><button type="button" className="secondary" disabled={loading||saving||disabled} onClick={()=>setChargeConfirm(true)}>Отримати нові · до 2 токенів</button><button type="button" disabled={!chosenOffer||!isVerified||saving||loading} onClick={()=>setSaveConfirm(true)}>Призначити в картку</button></div></footer>
    </aside>
   </div>,document.body)}
 </section>;
}
