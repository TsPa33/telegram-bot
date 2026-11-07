import DismantlingBoard from './DismantlingBoard';
import {useContext,useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {api,all,ApiError,labels,type Row} from './api';
import {useCan,TeamIdentity} from './permissions';
import {Modal} from './components';
import {PartDetail} from './pages/Inventory';
import {useMarketPrices,SellerPriceEditor,PartsValuation} from './MarketPricing';
import BulkPricing from './BulkPricing';
import PowertrainEditor from './PowertrainEditor';
import PlanPartsDonorAnalysis from './PlanPartsDonorAnalysis';
import './managed-dismantling.css';
import {CompactParts,PartsFilters,PriceStatistics} from './CompactParts';
import {matchesPart} from './partsPresentation';
import './warehouse-ux1.css';
import './plan-parts-workspace.css';
export default function VirtualDismantling({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const can=useCan(),identity=useContext(TeamIdentity),path=`/vehicles/${vehicle.id}/virtual-dismantling`;
 const key='warehouse.virtual.1:'+JSON.stringify([identity?.id,identity?.workspace_account_id||identity?.id,vehicle.id]);
 const [plan,setPlan]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[pending,setPending]=useState<Row|null>(null),[outcome,setOutcome]=useState<Row|null>(null);
 const [translationKick,setTranslationKick]=useState(0);
 const translationKickSource=useRef('base');
 const [formation,setFormation]=useState<'create'|'update'|null>(null);
 const [source,setSource]=useState<'base'|'professional'>('base');
 const [provider,setProvider]=useState<Row|null>(null),[begun,setBegun]=useState(false);
 const manualSource=useRef(false);
 function chooseSource(value:'base'|'professional'){setTranslationKick(0);manualSource.current=true;setSource(value);try{sessionStorage.setItem(key+':source',value)}catch{}}
 const [coverage,setCoverage]=useState<Row|null>(null),[coverageLoading,setCoverageLoading]=useState(false);
 const [q,setQ]=useState(''),[category,setCategory]=useState(''),[sub,setSub]=useState(''),[selected,setSelected]=useState<string[]>([]),[limit,setLimit]=useState(60),[powertrain,setPowertrain]=useState('');
 const [priceFilter,setPriceFilter]=useState(''),[stateFilter,setStateFilter]=useState(''),[stockRows,setStockRows]=useState<Record<string,Row>>({}),[stockError,setStockError]=useState('');
 const [detail,setDetail]=useState<Row|null>(null),[quantity,setQuantity]=useState('1'),[location,setLocation]=useState(''),[condition,setCondition]=useState('unknown');
 const running=useRef(false),coverageRequest=useRef(false),epoch=useRef(0);
 const editable=can('dismantling.manage')&&can('inventory.edit')&&!vehicle.archived;
 const activate=can('dismantling.manage')&&!vehicle.archived&&can('inventory.activate_virtual')&&can('inventory.create');
 async function load(){const e=epoch.current;const r=await api(path);if(e===epoch.current)setPlan(r);return r;}
 useEffect(()=>{manualSource.current=false;setTranslationKick(0);setBegun(false);setProvider(null);},[key]);
 useEffect(()=>{const e=++epoch.current;setPlan(null);setSelected([]);setPending(null);setError('');Promise.all([api(path),identity?.role==='DIRECTOR'?api('/plan-parts/workspace?vehicle_id='+encodeURIComponent(vehicle.id)).catch(()=>null):Promise.resolve(null)]).then(([r,saved])=>{if(epoch.current!==e)return;setPlan(r);setProvider(saved);if(!manualSource.current){let preferred='';try{preferred=sessionStorage.getItem(key+':source')||''}catch{};setSource(preferred==='professional'&&saved?.categories?.length?'professional':preferred==='base'&&(r.virtual_mode||r.items?.length)?'base':r.virtual_mode||r.items?.length?'base':saved?.categories?.length?'professional':'base');}}).catch(e=>{if(epoch.current===e)setError(e.message)});try{const p=JSON.parse(sessionStorage.getItem(key)||'null');if(p&&p.scope===key&&['activate','availability'].includes(p.kind)&&p.payload&&/^[a-f0-9-]{36}$/.test(p.payload.request_key))setPending(p);}catch{setError('Не вдалося відновити локальний стан. Оновіть сторінку.');}return()=>{epoch.current++;};},[path,key,vehicle.ktype,vehicle.engine,vehicle.fuel_type,vehicle.transmission,vehicle.vin]);
 async function work(fn:()=>Promise<void>){if(running.current)return;running.current=true;setBusy(true);setError('');try{await fn();}catch(e){setError(e instanceof TypeError?'З’єднання перервано. Збережений запит можна безпечно повторити.':(e as Error).message);}finally{running.current=false;setBusy(false);}}
 async function command(kind:string,payload:Row,existing?:Row){const generation=epoch.current;const request=existing||{scope:key,kind,payload:{...payload,request_key:crypto.randomUUID()}};setPending(request);try{sessionStorage.setItem(key,JSON.stringify(request));}catch{setPending(null);throw Error('Не вдалося зберегти захищений запит у браузері. Звільніть сховище або скористайтесь іншим браузером; дані не змінено.');}try{const r=await api(path+'/'+request.kind,'POST',request.payload);sessionStorage.removeItem(key);if(generation!==epoch.current)return;setOutcome(r);setPending(null);await load();if(request.kind==='activate'){translationKickSource.current='base';setTranslationKick(n=>n+1);}if(request.kind==='activate'&&generation===epoch.current)onSaved(await api('/vehicles/'+vehicle.id));}catch(e){if(e instanceof ApiError&&e.status<500){sessionStorage.removeItem(key);if(generation===epoch.current){setPending(null);await load();}}throw e;}}
 async function analyzeCoverage(){
  if(!plan||running.current||coverageRequest.current||coverage)return;
  coverageRequest.current=true;
  setCoverageLoading(true);setError('');
  let initial:Row={etag:plan.etag,local_candidates:(plan.items||[]).length,local_categories:new Set((plan.items||[]).map((i:Row)=>i.category).filter(Boolean)).size,pending:plan.pending_count||0};
  try{
   const prospective=await api<Row>('/vehicles/'+encodeURIComponent(String(vehicle.id))+'/virtual-dismantling/coverage-preview','POST');
   initial={...initial,etag:prospective.etag,local_candidates:prospective.candidates,local_categories:prospective.categories,pending:prospective.review,prospective};
  }catch(e){
   setError('Не вдалося перевірити майбутній список деталей: '+(e as Error).message);coverageRequest.current=false;setCoverageLoading(false);return;
  }
  // Basic dismantling uses only CarPot and never spends supplier tokens.
  setCoverage(initial);
  coverageRequest.current=false;
  setCoverageLoading(false);
 }
 function confirmCoverage(){
  if(!plan||!coverage||coverage.etag!==plan.etag||locked)return;
  setCoverage(null);
  setFormation(plan.virtual_mode?'update':'create');
  void work(async()=>{try{await command('activate',{facts:plan.virtual_mode&&powertrain?[{field:'powertrain',value:powertrain,kind:'manual',reference:'Уточнення власника автомобіля',confidence:'reported'}]:[],etag:plan.etag,confirm:true});}finally{setFormation(null);}});
 }
 useEffect(()=>{setCoverage(null);},[vehicle.id,vehicle.ktype,vehicle.year,vehicle.engine,vehicle.fuel_type,vehicle.transmission,vehicle.vin]);
 const items:Row[]=(plan?.items||[]).map((i:Row)=>({...i,stock:i.stock?{...i.stock,oem_number:stockRows[i.part_id]?.oem_number,article_number:stockRows[i.part_id]?.article_number}:null}));
 const market=useMarketPrices([]);
 const shown=items.filter(i=>matchesPart(i,{q,category,sub,state:stateFilter,price:priceFilter},market.rows[i.part_id]));
 useEffect(()=>{let current=true;setStockRows({});setStockError('');if(plan&&can('inventory.view'))Promise.all([all('/parts?vehicle_id='+vehicle.id),plan.items.some((i:Row)=>i.stock?.archived)?all('/parts?vehicle_id='+vehicle.id+'&archived=true'):Promise.resolve([])]).then(groups=>{if(current)setStockRows(Object.fromEntries(groups.flat().map(r=>[r.id,r])));}).catch(()=>{if(current)setStockError('Не вдалося завантажити OEM та артикули. Пошук за назвою доступний.');});return()=>{current=false;};},[vehicle.id,plan?.etag]);
 useEffect(()=>{const refresh=()=>{load().catch(e=>setError(e.message));};window.addEventListener('warehouse:prices-changed',refresh);return()=>window.removeEventListener('warehouse:prices-changed',refresh);},[path]);
 const available=(rows:Row[])=>rows.filter(i=>i.selectable).map(i=>i.id),selectedSet=new Set(selected),locked=busy||!!pending;
 function choose(ids:string[],checked:boolean){setSelected(old=>checked?[...new Set([...old,...ids])]:old.filter(id=>!ids.includes(id)));}
 async function toggle(ids:string[],enabled:boolean){await work(async()=>{let current=plan!;for(let n=0;n<ids.length;n+=1000){await command('availability',{ids:ids.slice(n,n+1000),enabled,etag:current.etag});current=await load();}setSelected([]);});}
 async function openPart(id:string){await work(async()=>{const p=await api('/parts/'+id);setDetail(p);setQuantity(String(p.quantity));setLocation(p.location||'');setCondition(p.condition);});}
 async function updateDetail(fn:()=>Promise<unknown>){await work(async()=>{await fn();setDetail(await api('/parts/'+detail!.id));await load();window.dispatchEvent(new Event('warehouse:inventory-changed'));});}
 const sourceSelector=(<div className="cp-mode-panel">
   <div className="cp-mode-options" role="group" aria-label="Джерело запчастин">
    <button type="button" aria-pressed={source==='base'} className={'cp-mode-option '+(source==='base'?'is-selected':'')} onClick={()=>chooseSource('base')}>
     <span className="cp-mode-symbol">▣</span><span><strong>Базовий CarPot</strong><small>Основні запчастини · без токенів</small></span><span className="cp-radio" aria-hidden="true"/>
    </button>
    {identity?.role==='DIRECTOR'&&<button type="button" aria-pressed={source==='professional'} className={'cp-mode-option '+(source==='professional'?'is-selected':'')} onClick={()=>chooseSource('professional')}>
     <span className="cp-mode-symbol">▤</span><span><strong>Професійний каталог plan.parts</strong><small>Детальний вибір за модифікацією</small></span><span className="cp-radio" aria-hidden="true"/>
    </button>}
   </div>
   <small className="cp-source-help">{source==='base'?'Безкоштовний базовий розбір; сумісність деталей потребує перевірки.':'Використовуємо збережені дані каталогу. Артикули отримуються лише за окремим запитом.'}</small>
  </div>);
 const hasBasePlan=Boolean(plan?.virtual_mode||plan?.items?.length),hasProviderPlan=Boolean(provider?.categories?.length);
 if(!plan)return <section aria-label="Віртуальний розбір" className="catalogue-formation" role="status"><span className="catalogue-formation-spinner" aria-hidden="true"/><p>{error||'Завантажуємо перелік запчастин…'}</p></section>;
 if(!hasBasePlan&&!hasProviderPlan&&!begun)return <section className="catalogue-formation" aria-label="Початок розбору"><div><h2>Розбір автомобіля на запчастини</h2><p>{vehicle.manufacturer} {vehicle.model} · {vehicle.year}</p><p>Створіть і збережіть список деталей. Фізичне надходження на склад — окрема дія.</p>{error&&<p role="alert">{error}</p>}<button className="primary" disabled={!activate} onClick={()=>setBegun(true)}>Розібрати на запчастини</button>{!activate&&<p>Створення плану доступне працівнику з правом керування розбором.</p>}</div></section>;
 return <section className="managed-v3 virtual-dismantling ux1-dismantling" aria-label="Віртуальний розбір">

  {error&&!detail&&<p role="alert" className="error">{error}</p>}
  {!hasBasePlan&&source==='base'&&sourceSelector}
  {source==='professional'&&identity?.role==='DIRECTOR'&&(hasProviderPlan?<DismantlingBoard vehicle={vehicle} source="professional" revision={plan.etag} translationKick={translationKickSource.current==='professional'?translationKick:0} onTranslationConsumed={()=>setTranslationKick(0)} onOpenPart={openPart} controls={<PlanPartsDonorAnalysis setupOnly vehicle={vehicle} onSaved={onSaved} sourceSelector={sourceSelector} onLoaded={row=>setProvider(row)} onCatalogueReady={()=>{translationKickSource.current='professional';setTranslationKick(n=>n+1)}}/>}/>:<PlanPartsDonorAnalysis key={String(vehicle.id)} vehicle={vehicle} onSaved={onSaved} sourceSelector={sourceSelector} onLoaded={row=>{setProvider(row);setBegun(true)}} onCatalogueReady={()=>{translationKickSource.current='professional';setTranslationKick(n=>n+1)}}/>)}
  {source==='base'&&<>
  {pending&&<div role="status"><p>Результат попереднього запиту потребує перевірки. Повторення не створить дублікатів.</p><button disabled={busy} onClick={()=>work(()=>command(pending.kind,pending.payload,pending))}>Перевірити збережений запит</button></div>}
  {!hasBasePlan&&!coverage&&!formation&&<><p>{plan.virtual_mode?'Оновлення списку почнеться з перевірки кількості можливих деталей.':'Спочатку перевіримо кількість кандидатів у каталозі. Позиції з’являться лише після окремого підтвердження.'}</p>
  {items.length>0&&<p>Наявні ціни, продажі, резерви та виключення збережуться.</p>}
  <button disabled={locked||coverageLoading||!activate} onClick={()=>void analyzeCoverage()}>{coverageLoading?'Аналізуємо…':plan.virtual_mode?'Перевірити оновлення деталей':'Сформувати базовий список'}</button></>}
  {coverageLoading&&<div className="catalogue-formation" role="status" aria-live="polite"><span className="catalogue-formation-spinner" aria-hidden="true"/><div><strong>Аналізуємо кількість запчастин</strong><p>Складські позиції не створюються.</p></div></div>}
  {coverage&&<section className="catalogue-formation" aria-label="Попередній аналіз запчастин" role="status">
   <div style={{width:'100%'}}>
    <h3>Базовий розбір CarPot</h3>
    <p>Категорій у майбутньому плані: <strong>{coverage.local_categories}</strong> · Потенційних позицій: <strong>{coverage.local_candidates}</strong> · Потребують перевірки: <strong>{coverage.pending}</strong>.</p>
    {coverage.prospective?.limited&&<p role="status">Оцінка базується на неповному конструктивному довіднику. Це не повний OEM-каталог конкретного VIN.</p>}
    <p>Це базовий конструктивний перелік можливих деталей. Перед обліком перевіряйте фізичну наявність.</p>
    {coverage.etag!==plan.etag&&<p role="alert">Дані автомобіля змінилися. Повторіть аналіз перед підтвердженням.</p>}
    <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
     <button disabled={locked||!activate||coverage.etag!==plan.etag} onClick={confirmCoverage}>{plan.virtual_mode?'Підтвердити оновлення':'Підтвердити створення списку'}</button>
     <button className="secondary" disabled={locked} onClick={()=>setCoverage(null)}>Скасувати</button>
    </div>
    <small>Тестовий режим. Оплати, внутрішні бали й списання з користувачів вимкнені.</small>
   </div>
  </section>}
  {formation&&<div className="catalogue-formation" role="status" aria-live="polite"><span className="catalogue-formation-spinner" aria-hidden="true"/><div><strong>{formation==='create'?'Формуємо запчастини автомобіля':'Оновлюємо перелік запчастин'}</strong><p>Обробляємо дані каталогу. Кількість позицій з’явиться після відповіді сервера.</p></div></div>}
  {(plan.configuration_stale||plan.catalogue_changed)&&plan.virtual_mode&&<p role="status">Характеристики або каталог оновлено. Натисніть «Оновити список», щоб перевірити нові позиції; попередні рішення збережуться.</p>}
  {outcome&&<p role="status">{outcome.activated!==undefined?`Список збережено: нових позицій ${outcome.activated}, повторно використано ${outcome.reused_parts}, потребують перевірки ${outcome.pending}. Фізичні надходження не створювалися.`:`Доступність змінено: ${outcome.updated}.`}</p>}
  {hasBasePlan&&<DismantlingBoard vehicle={vehicle} source="base" revision={plan.etag} translationKick={translationKickSource.current==='base'?translationKick:0} onTranslationConsumed={()=>setTranslationKick(0)} onUpdate={analyzeCoverage} onOpenPart={openPart} controls={<>{sourceSelector}<PowertrainEditor vehicle={vehicle} onSaved={onSaved} compact/></>}/>}

 </>}
   {detail&&<Modal className="r1-part-dialog" title={detail.name} onClose={()=>setDetail(null)}>{error&&<p role="alert" className="error">{error}</p>}<PartDetail part={detail} onSaved={row=>{setDetail(row);load();window.dispatchEvent(new Event('warehouse:inventory-changed'));}} onChanged={()=>{api('/parts/'+detail.id).then(setDetail);load();window.dispatchEvent(new Event('warehouse:inventory-changed'));}}/><details className="r1-secondary"><summary>Стан та складські операції</summary>{can('parts.inspect')&&<form onSubmit={e=>{e.preventDefault();updateDetail(()=>api('/parts/'+detail.id+'/inspection','PATCH',{condition}));}}><label>Фізичний стан деталі<select aria-label="Фізичний стан деталі" value={condition} onChange={e=>setCondition(e.target.value)}>{['unknown','used','new','damaged','refurbished'].map(v=><option value={v} key={v}>{labels[v]}</option>)}</select></label><button disabled={busy}>Зберегти стан</button></form>}{can('inventory.adjust_quantity')&&<form onSubmit={e=>{e.preventDefault();updateDetail(()=>api('/parts/'+detail.id+'/operations','POST',{type:'correction',quantity:Number(quantity),reason:'Явне уточнення облікової кількості власником',request_key:crypto.randomUUID()}));}}><label>Облікова кількість<input type="number" min={detail.reserved_quantity} step="1" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label><button disabled={busy}>Уточнити кількість</button></form>}{can('inventory.transfer')&&<form onSubmit={e=>{e.preventDefault();updateDetail(()=>api('/parts/'+detail.id+'/operations','POST',{type:'transfer',quantity:0,location,physical_location_kind:'on_shelf',reason:'Переміщення всього лота на полицю без зміни залишку',request_key:crypto.randomUUID()}));}}><label>Місце на полиці<input value={location} required maxLength={120} onChange={e=>setLocation(e.target.value)}/></label><button disabled={busy}>Перемістити на полицю</button></form>}</details></Modal>}
 </section>;
}
