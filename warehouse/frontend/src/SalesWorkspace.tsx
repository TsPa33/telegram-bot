import InventorySelectionEditor from "./InventorySelectionEditor";
import {corporateCategoryGroups} from "./catalogueLabels";
import "./inventory-compact.css";
import CategoryRepair from './CategoryRepair';
import PartActionMenu from './PartActionMenu';
import {useCan,TeamIdentity} from './permissions';
import {useContext,useEffect,useRef,useState} from 'react';
import {all,api,ApiError,labels,money,type Page,type Row} from './api';
import {Modal,Pager,RecordForm,Empty} from './components';
import {Confirm,State,useLoad,type Notify} from './shared';
import {partFields,PartDetail} from './pages/Inventory';
import {useSearchParams} from 'react-router-dom';
import StockHistory from './StockHistory';
import {NotesDialog,InspectionDialog,WorkshopGate} from './WorkshopDialogs';
import {useMarketPrices,SellerPriceEditor} from './MarketPricing';
import BulkPricing from './BulkPricing';
import './workshop.css';
import './smart-search.css';
import {isSmartReady} from './smartSearch';
import {OrderComposer} from './Orders';
import {useNavigate} from 'react-router-dom';

import InventoryFilters from './InventoryFilters';
import {InventoryPartRow,InventoryTableHead} from './InventoryPartsList';
import InventoryInsights,{InventorySummary} from './InventoryInsights';
import {Layers,MapPin,ClipboardCheck,LayoutList,Plus,Boxes} from 'lucide-react';
import './inventory-r115.css';
import StockBulkDialog from './StockBulkDialog';
import {inventoryMatches,activeInventoryIds} from './inventoryPresentation';
import {SelectionCheck} from './DismantlingBulk';
import './inventory-ui3.css';
import {partsSearchQuery} from './partsSearchQuery';
import PartsSearchControls from './PartsSearchControls';
import PartsQuickCategories from './PartsQuickCategories';
import SearchPartPreview from './SearchPartPreview';
import SearchPartPhoto from './SearchPartPhoto';
import './parts-search-ui4.css';
import './search-r11.css';
type Action={part:Row;type:string;key:string};
const actionLabels:Record<string,string>={sale:'Продати',write_off:'Списати',transfer:'Перемістити',reserve:'Зарезервувати',release:'Зняти резерв',receipt:'Додати кількість',correction:'Змінити кількість'};
type WorkspaceProps={quick?:boolean;notify:Notify;accountId:string;grouped?:boolean;inventoryVehicles?:Row[]|null;onHistory?:()=>void};
export default function SalesWorkspace(props:WorkspaceProps) {
 return <WorkshopGate><SalesWorkspaceContent {...props}/></WorkshopGate>;
}
function SalesWorkspaceContent({quick=false,notify,accountId,grouped=false,inventoryVehicles,onHistory}:{quick?:boolean;notify:Notify;accountId:string;grouped?:boolean;inventoryVehicles?:Row[]|null;onHistory?:()=>void}) {
 const can=useCan(),pricingIdentity=useContext(TeamIdentity);const canBulkPrice=pricingIdentity?.role==='DIRECTOR'&&can('parts.change_price');
 const navigate=useNavigate(),[orderPart,setOrderPart]=useState<Row|null>(null);
 const [params,setParams]=useSearchParams(),vehicle=params.get('vehicle_id')||'';
 const [smart,setSmart]=useState(false);
 const smartReadiness=useLoad(async()=>{
  if(!quick)return null;
  const result=await api('/smart-search/readiness','GET',undefined,200);
  if(!isSmartReady(result))throw Error('Розумний пошук тимчасово недоступний.');
  return result;
 },[quick]);
 const smartReady=!smartReadiness.loading&&!smartReadiness.error&&isSmartReady(smartReadiness.data);
 const [brand,setBrand]=useState(''),[model,setModel]=useState(''),[q,setQ]=useState(''),[term,setTerm]=useState(''),[page,setPage]=useState(0),[showZero,setShowZero]=useState(false);
 const [category,setCategory]=useState(''),[sub,setSub]=useState(''),[condition,setCondition]=useState(''),[ownPrice,setOwnPrice]=useState(''),[inventoryState,setInventoryState]=useState('stock'),[stockBulk,setStockBulk]=useState(false);
 const [previewId,setPreviewId]=useState('');
 const [quickActionsOpen,setQuickActionsOpen]=useState(()=>!matchMedia('(max-width:600px)').matches);
 useEffect(()=>{if(quick)return;const media=matchMedia('(max-width:600px)'),change=()=>setQuickActionsOpen(!media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[quick]);
 const [pageSize,setPageSize]=useState(25),[selectionEdit,setSelectionEdit]=useState(''),[exportBusy,setExportBusy]=useState(false),[exportError,setExportError]=useState('');
 const [inventorySection,setInventorySection]=useState<'parts'|'groups'|'categories'|'locations'|'inspection'>('parts');
 const [locationFilter,setLocationFilter]=useState('');
 const [tablePage,setTablePage]=useState(0),[tableSort,setTableSort]=useState('name'),[descending,setDescending]=useState(false);
 const [photoRevisions,setPhotoRevisions]=useState<Record<string,number>>({});
 const [detail,setDetail]=useState<Row|null>(null),[detailEdit,setDetailEdit]=useState<'oem'|'color'|undefined>(),[detailEditVersion,setDetailEditVersion]=useState(0),[edit,setEdit]=useState<Row|null>(null),[price,setPrice]=useState<Row|null>(null),[action,setAction]=useState<Action|null>(null),[archive,setArchive]=useState<Row|null>(null),[history,setHistory]=useState<Row|null>(null);
 const [notes,setNotes]=useState<Row|null>(null),[inspection,setInspection]=useState<Row|null>(null);
 const [overrides,setOverrides]=useState<Record<string,Row>>({});
 const [pendingRequests,setPendingRequests]=useState<{partId:string;type:string;body:Row}[]>([]),[pendingError,setPendingError]=useState('');
 useEffect(()=>{const scan=()=>{try{const prefix='warehouse-stock-pending:'+accountId+':';setPendingRequests(Object.keys(sessionStorage).filter(k=>k.startsWith(prefix)).map(k=>{const [partId,type]=k.slice(prefix.length).split(':');return {partId,type,body:JSON.parse(sessionStorage.getItem(k)!)};}));}catch{setPendingError('Не вдалося прочитати непідтверджені операції.');}};scan();window.addEventListener('warehouse:stock-pending',scan);return()=>window.removeEventListener('warehouse:stock-pending',scan);},[accountId]);
 const [focused,setFocused]=useState(false),[suggestion,setSuggestion]=useState(-1);
 const lookups=useLoad(()=>Promise.all([inventoryVehicles!==undefined?Promise.resolve([]):can('vehicles.view')?all('/vehicles'):Promise.resolve([]),inventoryVehicles!==undefined?Promise.resolve([]):can('vehicles.view')?all('/vehicles?archived=true'):Promise.resolve([]),can('catalog.view')?all('/categories'):Promise.resolve([])]),[]),vehicles=inventoryVehicles!==undefined?(inventoryVehicles||[]):[...(lookups.data?.[0]||[]),...(lookups.data?.[1]||[])],categories=lookups.data?.[2]||[];
 useEffect(()=>{const timer=setTimeout(()=>{setTerm(q);setPage(0);setSuggestion(-1);},300);return()=>clearTimeout(timer);},[q]);
 const query=quick?partsSearchQuery({smart,q:term,vehicle,brand,model,condition,category,stock:!showZero,page}):new URLSearchParams({q:term,in_stock:String(!showZero),limit:String(pageSize),offset:String(page*pageSize)});
 if(!quick){if(condition)query.set('condition',condition);if(category)query.set('category_id',category);if(condition)query.set('condition',condition);if(vehicle)query.set('vehicle_id',vehicle);if(brand)query.set('manufacturer',brand);if(model)query.set('model',model);}
 const searchKey=(smart?'smart:':'standard:')+query.toString();
 const {data,error,loading,reload}=useLoad(()=>(smart&&!smartReady?Promise.resolve({items:[],total:0}):api<Page>((smart?'/smart-search/parts?':'/parts?')+query)).then(result=>({...result,query_key:searchKey})),[searchKey,grouped,smart&&smartReady]);
 useEffect(()=>{const changed=()=>{reload();lookups.reload();};window.addEventListener('warehouse:inventory-changed',changed);return()=>window.removeEventListener('warehouse:inventory-changed',changed);},[]);
 useEffect(()=>{if(!quick&&data?.query_key===searchKey&&data.total>0&&page*pageSize>=data.total)setPage(Math.floor((data.total-1)/pageSize));},[data,searchKey,page,pageSize,quick]);
 const current=!error&&!loading&&(!smart||smartReady)&&data?.query_key===searchKey&&q===term;
 const waiting=loading||q!==term||(!current&&!error&&(!smart||smartReady));
 const unlocatedRows=current?data!.items.map(p=>overrides[p.id]||p).filter(p=>!p.archived&&(showZero||(smart?p.available_quantity>0:p.quantity>0))):[];
 const rows=!quick&&locationFilter?unlocatedRows.filter(p=>locationFilter==='__none__'?!String(p.location||'').trim():String(p.location||'').trim()===locationFilter):unlocatedRows;
 const suggestions=rows.slice(0,5),optionsOpen=quick&&focused&&!!q&&!waiting&&!error;
 useEffect(()=>{setSuggestion(-1);setOverrides({});},[data]);
 const sortedInventoryRows=!quick?[...rows].sort((a,b)=>{
  let result=0;
  if(tableSort==='quantity')result=Number(a.quantity||0)-Number(b.quantity||0);
  else if(tableSort==='price')result=Number(a.selling_price||0)-Number(b.selling_price||0);
  else if(tableSort==='location')result=String(a.location||'').localeCompare(String(b.location||''),'uk');
  else result=String(a.name||'').localeCompare(String(b.name||''),'uk');
  return descending?-result:result;
 }):[];
 const inventoryPageRows=sortedInventoryRows.slice(tablePage*50,(tablePage+1)*50);
 const inspectionRows=sortedInventoryRows.filter(p=>p.quantity_basis==='assumed'||p.availability==='unchecked');
 const inspectionPageRows=inspectionRows.slice(tablePage*50,(tablePage+1)*50);
 function sortInventory(key:string){if(tableSort===key)setDescending(v=>!v);else{setTableSort(key);setDescending(false);}setTablePage(0);}
 const brands=[...new Set(vehicles.map(v=>v.manufacturer))].sort((a,b)=>a.localeCompare(b,'uk'));
 const models=[...new Set(vehicles.filter(v=>!brand||v.manufacturer===brand).map(v=>v.model))].sort((a,b)=>a.localeCompare(b,'uk'));
 const previewPart=quick?(rows.find(p=>p.id===previewId)||rows[0]||null):null;
 const previewVehicle=previewPart?vehicles.find(v=>v.id===previewPart.vehicle_id)||previewPart.donor:undefined;
 const previewIndex=previewPart?rows.findIndex(p=>p.id===previewPart.id):-1;
 function selectPreview(id:string,scroll=false){setPreviewId(id);if(scroll&&window.matchMedia('(max-width: 1430px)').matches)requestAnimationFrame(()=>document.getElementById('search-part-preview')?.scrollIntoView({behavior:'smooth',block:'start'}));}
 function updated(row:Row){setOverrides(values=>({...values,[row.id]:row}));setDetail(current=>current?.id===row.id?row:current);window.dispatchEvent(new Event('warehouse:inventory-changed'));}
 function openDetail(row:Row,edit?:'oem'|'color'){setDetailEdit(edit);setDetailEditVersion(v=>v+1);setDetail(row);}
 function openAction(part:Row,type:string){setDetail(null);setAction({part,type,key:crypto.randomUUID()});}
 const [pricingSelected,setPricingSelected]=useState<string[]>([]);
 useEffect(()=>{setPricingSelected([]);setSelectionEdit('');},[pricingIdentity?.workspace_account_id,accountId]);
 const market=useMarketPrices(quick?rows.map(p=>p.id):[]);
 const priceLabel=(p:Row)=>p.selling_price==null?'Вказати ціну':money(p.selling_price,p.currency||'UAH');
 const canSelect=canBulkPrice||can('inventory.adjust_quantity')||can('inventory.edit')||can('inventory.archive');
 const select=(ids:string[],checked:boolean)=>setPricingSelected(old=>checked?[...new Set([...old,...ids])]:old.filter(id=>!ids.includes(id)));
 const actions=(p:Row)=><PartActionMenu part={p} onSale={()=>openAction(p,'sale')} onPrice={()=>{setDetail(null);setPrice(p);}} onNotes={()=>{setDetail(null);setNotes(p);}} onInspection={()=>{setDetail(null);setInspection(p);}} onAction={type=>openAction(p,type)} onDetail={()=>openDetail(p)} onOem={()=>openDetail(p,'oem')} onColor={()=>openDetail(p,'color')} onEdit={()=>{setDetail(null);setEdit(p);}} onArchive={()=>{setDetail(null);setArchive(p);}} onHistory={()=>{setDetail(null);setHistory(p);}} compact={!quick}/>;
 useEffect(()=>{const refresh=()=>lookups.reload();window.addEventListener('warehouse:categories-changed',refresh);return()=>window.removeEventListener('warehouse:categories-changed',refresh);},[]);
 const renderInventoryPart=(p:Row,inspect=false)=><InventoryPartRow dashboard part={p} categories={categories} vehicle={vehicles.find(v=>v.id===p.vehicle_id)} market={market.rows[p.id]} marketError={market.error} selected={pricingSelected.includes(p.id)} canSelect={canSelect} onSelect={checked=>select([p.id],checked)} onOpen={()=>openDetail(p)} onSaved={updated} actions={<>{inspect&&can('parts.inspect')&&<button type="button" className="r115-inspect-button" onClick={()=>setInspection(p)}>Перевірити</button>}{actions(p)}</>} photo={<SearchPartPhoto id={p.id} name={p.name} revision={photoRevisions[p.id]||0}/>}/>;
 const categoryCounts=new Map<string,number>(),locationCounts=new Map<string,number>();
 for(const p of rows){const categoryId=String(p.category_id||'');categoryCounts.set(categoryId,(categoryCounts.get(categoryId)||0)+1);const loc=String(p.location||'').trim();locationCounts.set(loc,(locationCounts.get(loc)||0)+1);}
 const categorySummary=[...categoryCounts].sort((a,b)=>b[1]-a[1]);
 const locationSummary=[...locationCounts].sort((a,b)=>b[1]-a[1]);
 const content=<>
  {!quick&&<header className="r115-heading"><div><h1>Склад</h1><p>{waiting?'Завантаження…':error?'Не вдалося завантажити склад':`Усі запчастини на складі · ${data?.total||0} позицій`}</p></div><div className="r115-top-actions">{can('inventory.create')&&<button className="primary" onClick={()=>setEdit({condition:'used',currency:'UAH',vehicle_id:vehicle})}><Plus size={16}/> Додати запчастину</button>}<button disabled={exportBusy||waiting||!!error} onClick={async()=>{setExportBusy(true);setExportError('');try{const exportQuery=new URLSearchParams(query);exportQuery.delete('offset');exportQuery.delete('limit');const items=await all('/parts?'+exportQuery);const cell=(v:unknown)=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';const csv=[['Запчастина','Донор','Залишок','Резерв','OEM','Артикул','Виробник','Моя ціна','Валюта'],...items.map(p=>[p.name,vehicles.find(v=>v.id===p.vehicle_id)?.number||'',p.quantity,p.reserved_quantity,p.oem_number,p.article_number,p.article_brand,p.selling_price,p.currency])].map(r=>r.map(cell).join(';')).join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='carpot-stock.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){setExportError((e as Error).message);}finally{setExportBusy(false);}}}>{exportBusy?'Експортуємо…':'Експорт'}</button></div></header>}
  {!quick&&exportError&&<p role="alert">{exportError}</p>}

  {!!pendingRequests.length&&<div className="notice" role="status">Є операції без підтвердженого результату. {pendingRequests.map(p=><button key={p.partId+p.type} onClick={async()=>{try{setAction({part:await api('/parts/'+p.partId),type:p.type,key:p.body.request_key});}catch(e){setPendingError((e as Error).message);}}}>Перевірити: {actionLabels[p.type]||'операцію'}</button>)}</div>}
  {pendingError&&<p role="alert" className="error">{pendingError}</p>}
  {!quick&&<section className="stock-compact-filters" aria-label="Фільтри складу"><input type="search" aria-label="Пошук запчастин" placeholder="Назва, OEM або артикул…" value={q} onChange={e=>setQ(e.target.value)}/><select aria-label="Категорія складу" value={category} onChange={e=>{setCategory(e.target.value);setPage(0);}}><option value="">Усі категорії</option>{corporateCategoryGroups(categories).map(g=><option key={g.label} value={g.members.map(c=>c.id).join(',')}>{g.label}</option>)}<option value="__review__">Потребує уточнення</option></select><select aria-label="Стан запчастини" value={condition} onChange={e=>{setCondition(e.target.value);setPage(0);}}><option value="">Стан: усі</option>{['unknown','used','new','damaged','refurbished'].map(v=><option key={v} value={v}>{labels[v]}</option>)}</select><label className="check-inline"><input type="checkbox" checked={!showZero} onChange={e=>{setShowZero(!e.target.checked);setPage(0);}}/>Тільки в наявності</label><details><summary>Ще фільтри</summary><label>Автомобіль-донор<select aria-label="Автомобіль пошуку" value={vehicle} onChange={e=>{setParams(e.target.value?{vehicle_id:e.target.value}:{});setPage(0);}}><option value="">Усі автомобілі</option>{vehicles.map(v=><option key={v.id} value={v.id}>{v.manufacturer} {v.model} · {v.year} · №{v.number}</option>)}</select></label></details></section>}

  {quick&&<PartsSearchControls smart={smart} ready={smartReady} brand={brand} model={model} vehicle={vehicle} condition={condition} stock={!showZero} vehicles={vehicles} brands={brands} models={models} onMode={value=>{setSmart(value);if(value)setCategory('');setPage(0);setSuggestion(-1);}} onSearch={()=>{setTerm(q);setPage(0);setFocused(false);setSuggestion(-1);}} onChange={(key,value)=>{setPage(0);if(key==='brand'){setBrand(value);setModel('');setParams({});}if(key==='model'){setModel(value);setParams({});}if(key==='vehicle'){const donor=vehicles.find(v=>v.id===value);if(donor){setBrand(donor.manufacturer);setModel(donor.model);}setParams(value?{vehicle_id:value}:{});}if(key==='condition')setCondition(value);if(key==='stock')setShowZero(value!=='true');if(key==='reset'){setBrand('');setModel('');setCondition('');setCategory('');setShowZero(false);setParams({});}}}>
   <div className="seller-autocomplete"><label>Назва, OEM або артикул<input type={quick&&smart?'search':undefined} maxLength={smart?160:undefined} role={quick?'combobox':'searchbox'} aria-label="Пошук запчастин" aria-expanded={quick?optionsOpen:undefined} aria-autocomplete={quick?'list':undefined} aria-controls={quick?'part-suggestions':undefined} aria-activedescendant={suggestion>=0?`suggestion-${suggestion}`:undefined} placeholder="Назва, OEM або артикул" value={q} onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)} onChange={e=>setQ(e.target.value)} onKeyDown={e=>{
    if(e.key==='Escape'){setFocused(false);setSuggestion(-1);}if(e.key==='ArrowDown'&&suggestions.length){e.preventDefault();setFocused(true);setSuggestion(i=>(i+1)%suggestions.length);}if(e.key==='ArrowUp'&&suggestions.length){e.preventDefault();setSuggestion(i=>(i+suggestions.length-1)%suggestions.length);}if(e.key==='Enter'&&optionsOpen&&suggestion>=0){e.preventDefault();openDetail(suggestions[suggestion]);setFocused(false);}
   }}/></label>
   {optionsOpen&&<ul role="listbox" id="part-suggestions" aria-label="Підказки запчастин">{suggestions.map((p,i)=><li key={p.id}><button type="button" role="option" id={`suggestion-${i}`} aria-selected={suggestion===i} onPointerDown={e=>e.preventDefault()} onMouseDown={e=>e.preventDefault()} onClick={()=>{openDetail(p);setFocused(false);}}>{p.name}<small>{p.available_quantity} вільних · {priceLabel(p)}</small></button></li>)}{!suggestions.length&&<li>Нічого не знайдено</li>}</ul>}
   </div>
  </PartsSearchControls>}
  {quick&&<PartsQuickCategories categories={categories} selected={category} smart={smart} onSelect={id=>{setSmart(false);setCategory(id);setPage(0);setPreviewId('');setSuggestion(-1);}}/>}
  {quick&&!smartReady&&!smartReadiness.loading&&<p role="status" className="ui4-unavailable">Розумний пошук тимчасово недоступний. Звичайний пошук доступний. <button onClick={smartReadiness.reload}>Перевірити пошук</button></p>}
  <State error={error||lookups.error} loading={waiting||lookups.loading}/>
  {error&&!quick&&<button className="secondary" onClick={reload}>Повторити завантаження</button>}
  {error&&quick&&<button type="button" className="secondary" onClick={reload}>Повторити пошук</button>}
  {current&&(data as Row)?.clarification&&<p role="status">{(data as Row).clarification}</p>}
  {!quick&&<><details className="stock-quick-actions" open={quickActionsOpen} onToggle={e=>setQuickActionsOpen(e.currentTarget.open)}><summary>Швидкі дії · Вибрано: {pricingSelected.length}</summary><div><button disabled={!current||!rows.length} onClick={()=>select(rows.map(p=>p.id),true)}>Вибрати сторінку</button><button disabled={!pricingSelected.length} onClick={()=>setPricingSelected([])}>Зняти вибір</button>{[['quantity','Змінити кількість','inventory.adjust_quantity'],['price','Оновити ціну','parts.change_price'],['numbers','Призначити OEM / артикул','inventory.edit'],['category','Змінити категорію','inventory.edit']].filter(([, ,permission])=>can(permission)).map(([mode,label])=><button key={mode} disabled={!pricingSelected.length||mode==='category'&&!can('catalog.view')} onClick={()=>setSelectionEdit(mode)}>{label}</button>)}{can('inventory.archive')&&<button disabled={!pricingSelected.length||pricingSelected.length>100} onClick={()=>setStockBulk(true)}>Архівувати</button>}</div></details><section className="r115-inventory-table stock-compact-table" aria-label="Таблиця складських запчастин"><InventoryTableHead dashboard/>{rows.map(p=><div className="stock-row-wrap" key={p.id}>{renderInventoryPart(p)}</div>)}{!waiting&&!error&&!rows.length&&<Empty title="Нічого не знайдено">Змініть фільтри або автомобіль.</Empty>}<footer className="stock-pagination"><label>На сторінці<select aria-label="Позицій на сторінці" value={pageSize} onChange={e=>{setPageSize(Number(e.target.value));setPage(0);}}>{[25,50,100].map(n=><option key={n}>{n}</option>)}</select></label><span role="status">{current&&data?.total?`${page*pageSize+1}–${Math.min((page+1)*pageSize,data.total)} із ${data.total}`:'0 позицій'}</span><button disabled={!current||page===0} onClick={()=>setPage(n=>n-1)}>Попередня</button><button disabled={!current||(page+1)*pageSize>=(data?.total||0)} onClick={()=>setPage(n=>n+1)}>Наступна</button></footer></section></>}

  {quick&&<section className="ui4-results" aria-label="Результати пошуку">
   <p className="ui4-count" role="status">{waiting?'Пошук…':error?'Результати недоступні':`Знайдено ${data?.total||0} результатів`}</p>
   {!!rows.length&&<div className="ui11-results-layout">
    <SearchPartPreview part={previewPart} vehicle={previewVehicle}
      category={categories.find(c=>c.id===previewPart?.category_id)}
      subcategory={categories.find(c=>c.id===previewPart?.subcategory_id)}
      canSell={can('sales.create')} open={!!previewId} onClose={()=>setPreviewId('')}
      position={previewIndex+1} total={rows.length}
      onPrevious={()=>{if(previewIndex>0)selectPreview(rows[previewIndex-1].id);}}
      onNext={()=>{if(previewIndex>=0&&previewIndex<rows.length-1)selectPreview(rows[previewIndex+1].id);}}
      onOpen={()=>{if(previewPart)openDetail(previewPart);}}
      onEdit={()=>{if(previewPart){setDetail(null);setEdit(previewPart);}}}
      onSaved={updated}
      photoRevision={photoRevisions[previewPart?.id||'']||0}
      onPhotoSaved={id=>setPhotoRevisions(old=>({...old,[id]:(old[id]||0)+1}))}
      onSell={()=>{if(previewPart)openAction(previewPart,'sale');}}/>
    <div className="ui11-results-list"><InventoryTableHead/>{rows.map(p=><div key={p.id} className={'ui11-result-wrap'+(previewPart?.id===p.id?' selected':'')}>
     <InventoryPartRow part={p} categories={categories} vehicle={vehicles.find(v=>v.id===p.vehicle_id)||p.donor} market={market.rows[p.id]} marketError={market.error} selected={false} canSelect={false} onSelect={()=>{}} onOpen={()=>selectPreview(p.id,true)} onSaved={updated} actions={actions(p)} photo={<SearchPartPhoto id={p.id} name={p.name} revision={photoRevisions[p.id]||0}/>} extra={<>
      {(p.oem_number||p.article_number)&&<small className="ui11-codes">{p.oem_number&&`OEM: ${p.oem_number}`}{p.oem_number&&p.article_number?' · ':''}{p.article_number&&`Артикул: ${p.article_number}`}{p.article_number&&p.article_brand&&` · ${p.article_brand}`}</small>}
      <small>{labels[p.condition]||'Стан не уточнено'}</small>
      {smart&&p.match_explanation&&<small className="smart-match">{p.match_explanation}</small>}
      <button type="button" className="ui11-quick-view" aria-pressed={previewPart?.id===p.id} onClick={()=>selectPreview(p.id,true)}>Швидкий перегляд</button>
     </>}/></div>)}
     <Pager total={data?.total||0} page={page} setPage={setPage}/>
    </div>

   </div>}
   {!waiting&&!error&&(!smart||smartReady)&&!(data as Row)?.clarification&&!rows.length&&<Empty title="Нічого не знайдено">Змініть назву або автомобіль.</Empty>}
  </section>}
  {selectionEdit&&<InventorySelectionEditor ids={pricingSelected} mode={selectionEdit} categories={categories} vehicles={vehicles} onClose={()=>setSelectionEdit('')} onSaved={()=>window.dispatchEvent(new Event('warehouse:inventory-changed'))}/>}
  {stockBulk&&<StockBulkDialog archiveOnly={!quick} ids={pricingSelected} onClose={()=>setStockBulk(false)} onSaved={()=>{setStockBulk(false);setPricingSelected([]);window.dispatchEvent(new Event('warehouse:inventory-changed'));notify('Масову операцію проведено');}}/>}
  {orderPart&&<OrderComposer accountId={accountId} initialPart={orderPart} onClose={()=>setOrderPart(null)} onCreated={order=>{setOrderPart(null);setDetail(null);notify(order.reservation_warning||'Замовлення збережено');navigate('/orders/'+order.id);}}/>}
  {notes&&<NotesDialog part={notes} onClose={()=>setNotes(null)} onSaved={row=>{updated(row);setNotes(null);notify('Нотатку збережено');}}/>}
  {inspection&&<InspectionDialog part={inspection} onClose={()=>setInspection(null)} onSaved={row=>{updated(row);setInspection(null);notify('Стан збережено');}}/>}
  {price&&<PriceDialog part={price} onClose={()=>setPrice(null)} onSaved={row=>{updated(row);setPrice(null);notify('Ціну збережено');}}/>}
  {action&&<OperationDialog action={action} onClose={()=>setAction(null)} onSaved={row=>{updated(row);setAction(null);notify('Операцію проведено');}}/>}
  {edit&&<Modal title={edit.id?'Картка запчастини':'Нова запчастина'} onClose={()=>setEdit(null)}><RecordForm fields={partFields(vehicles,categories).filter(f=>quick||f.key!=='location').filter(f=>!({unit_cost:'parts.view_cost',selling_price:'parts.change_price',currency:'parts.change_price',internal_notes:'parts.notes',condition:'parts.inspect',availability:'parts.inspect',location:'inventory.transfer',vehicle_id:'vehicles.view',category_id:'catalog.view',subcategory_id:'catalog.view'} as Record<string,string>)[f.key]||can(({unit_cost:'parts.view_cost',selling_price:'parts.change_price',currency:'parts.change_price',internal_notes:'parts.notes',condition:'parts.inspect',availability:'parts.inspect',location:'inventory.transfer',vehicle_id:'vehicles.view',category_id:'catalog.view',subcategory_id:'catalog.view'} as Record<string,string>)[f.key]))} initial={edit} onSave={async body=>{if(!quick&&edit.id)body.location=(await api('/parts/'+edit.id)).location||'';const row=await api('/parts'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',body);updated(row);setEdit(null);setDetail(row);notify('Картку збережено');}}/></Modal>}
  {detail&&<Modal className="stock-part-dialog r1-part-dialog" title={detail.name} onClose={()=>setDetail(null)}><PartDetail part={detail} initialEdit={detailEdit} editVersion={detailEditVersion} onSaved={updated} onChanged={async()=>updated(await api('/parts/'+detail.id))} actions={<>{actions(detail)}{can('orders.create')&&can('orders.view')&&<button onClick={()=>{setDetail(null);setOrderPart({...detail,donor_snapshot:vehicles.find(v=>v.id===detail.vehicle_id)});}}>Оформити замовлення</button>}</>}/></Modal>}
  {history&&<Modal title={`Історія: ${history.name}`} onClose={()=>setHistory(null)}><StockHistory partId={history.id}/></Modal>}
  {archive&&<Confirm destructive title="Архівувати запчастину?" text="Архівування — не продаж. Історія й залишки зберігаються; позиція буде доступна в архіві." onClose={()=>setArchive(null)} onConfirm={async()=>{await api('/archive/parts/'+archive.id,'POST');if(detail?.id===archive.id)setDetail(null);setArchive(null);window.dispatchEvent(new Event('warehouse:inventory-changed'));}}/>}
 </>;
 return quick?<div className="ui4-search-page">{content}</div>:<div className="ui3-inventory">{content}</div>;
}
function PriceDialog({part,onClose,onSaved}:{part:Row;onClose:()=>void;onSaved:(row:Row)=>void}){return <Modal title="Ціна запчастини" onClose={onClose}><SellerPriceEditor part={part} initialOpen onSaved={onSaved}/></Modal>;}
function OperationDialog({action,onClose,onSaved}:{action:Action;onClose:()=>void;onSaved:(row:Row)=>void}){
 const {part,type}=action,[quantity,setQuantity]=useState('1'),[location,setLocation]=useState(part.location||''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 // Persist unresolved requests across modal/page reload. Retries must keep the
 // exact body/key; after a completed operation a new deliberate action gets a new key.
 const [salePrice,setSalePrice]=useState(part.selling_price??''),[saleCurrency,setSaleCurrency]=useState(part.currency||'UAH');
 const pendingKey='warehouse-stock-pending:'+part.account_id+':'+part.id+':'+type;
 const pending=useRef<Row|null>(null),submitting=useRef(false);
 const [storageBlocked,setStorageBlocked]=useState(false);
 useEffect(()=>{try{const saved=sessionStorage.getItem(pendingKey);if(saved){pending.current=JSON.parse(saved);setQuantity(String(pending.current!.quantity??1));setLocation(pending.current!.location??part.location??'');setReason(pending.current!.reason||'');setSalePrice(pending.current!.sale_price??'');setSaleCurrency(pending.current!.sale_currency||'UAH');setError('Є непідтверджений запит. Повторіть, щоб перевірити його результат.');}}catch{setStorageBlocked(true);setError('Не вдалося прочитати попередній запит. Новий продаж заблоковано, щоб не повторити непідтверджену операцію.');}},[]);
 return <Modal title={`${actionLabels[type]}: ${part.name}`} onClose={onClose}><form onSubmit={async e=>{e.preventDefault();if(submitting.current||storageBlocked)return;submitting.current=true;setBusy(true);setError('');try{
   const normalized=String(salePrice).replace(',','.');if(type==='sale'&&!pending.current&&!/^\d{1,12}(\.\d{1,2})?$/.test(normalized))throw Error('Вкажіть фактичну ціну продажу');
   const body=pending.current||{type,...(type==='sale'?{sale_price:normalized,sale_currency:saleCurrency}:{}),quantity:type==='transfer'?0:Number(quantity),...(type==='transfer'?{location}:{}),reason:reason||(type==='sale'?'Продаж':type==='write_off'?'':actionLabels[type]),request_key:action.key};
   pending.current=body;sessionStorage.setItem(pendingKey,JSON.stringify(body));window.dispatchEvent(new Event('warehouse:stock-pending'));
   await api('/parts/'+part.id+'/operations','POST',body);const row=await api('/parts/'+part.id);sessionStorage.removeItem(pendingKey);window.dispatchEvent(new Event('warehouse:stock-pending'));onSaved(row);
  }catch(e){if(e instanceof ApiError&&[409,422].includes(e.status)){sessionStorage.removeItem(pendingKey);pending.current=null;window.dispatchEvent(new Event('warehouse:stock-pending'));}setError((e as Error).message);}finally{submitting.current=false;setBusy(false);}}}>
  <p>У наявності: {part.available_quantity}</p>
  {type==='sale'&&<><label>Фактична ціна продажу за одиницю<input aria-label="Фактична ціна продажу" required inputMode="decimal" disabled={!!pending.current} value={salePrice} onChange={e=>setSalePrice(e.target.value)}/></label><label>Валюта продажу<select aria-label="Валюта продажу" disabled={!!pending.current} value={saleCurrency} onChange={e=>setSaleCurrency(e.target.value)}><option>UAH</option><option>USD</option></select></label>{pending.current&&!('sale_price' in pending.current)&&<p role="status">Попередній запит не містив фактичної ціни. Перевірка повторить саме його.</p>}</>}

  {type==='transfer'?<label>Нове місце<input aria-label="Нове місце" required maxLength={120} disabled={!!pending.current} value={location} onChange={e=>setLocation(e.target.value)}/></label>:<label>Кількість<input aria-label="Кількість" type="number" min={type==='correction'?0:1} max={pending.current?1000000:type==='sale'||type==='write_off'||type==='reserve'?part.available_quantity:1000000} step={1} required disabled={!!pending.current} value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>}
  <label>{type==='write_off'?'Причина списання':'Примітка (необов’язково)'}<input aria-label={type==='write_off'?'Причина списання':'Примітка (необов’язково)'} required={type==='write_off'} minLength={type==='write_off'?3:undefined} maxLength={2000} disabled={!!pending.current} value={reason} onChange={e=>setReason(e.target.value)}/></label>
  {error&&<p role="alert" className="error">{error}</p>}<div className="modal-actions"><button type="submit" className="primary" disabled={busy||storageBlocked}>Підтвердити</button></div>
 </form></Modal>;
}

function StockTree({rows,categories,render,searching,compact=false,tableHead,groupActions}:{searching:boolean;rows:Row[];categories:Row[];render:(row:Row)=>import('react').ReactNode;compact?:boolean;tableHead?:import('react').ReactNode;groupActions?:(rows:Row[],label:string)=>import('react').ReactNode}) {
 const [expanded,setExpanded]=useState<Record<string,boolean>>({}),[limits,setLimits]=useState<Record<string,number>>({}),[expandedSubs,setExpandedSubs]=useState<Record<string,boolean>>({});
 const names=new Map(categories.map(c=>[c.id,c.name]));
 const groups=new Map<string,Map<string,Row[]>>();
 for(const row of rows){const category=row.category_id||'',sub=row.subcategory_id||'';if(!groups.has(category))groups.set(category,new Map());const subs=groups.get(category)!;if(!subs.has(sub))subs.set(sub,[]);subs.get(sub)!.push(row);}
 return <div className={compact?"donor-stock-tree ui3-tree":"donor-stock-tree"}>{[...groups].map(([id,subs])=><details key={id} open={searching||!!expanded[id]}>
  <summary onClick={e=>{e.preventDefault();if(searching)return;setExpanded(old=>({...old,[id]:!old[id]}));}}>{groupActions?.([...subs.values()].flat(),names.get(id)||'Без категорії')}<strong>{names.get(id)||'Без категорії'}</strong><small>{[...subs.values()].reduce((n,items)=>n+items.length,0)}</small></summary>
  {(searching||expanded[id])&&tableHead}
  {(searching||expanded[id])&&[...subs].map(([sub,items])=>{const key=id+':'+sub;return <details className="donor-stock-subcategory" key={sub} open={searching||!!expandedSubs[key]}><summary onClick={e=>{e.preventDefault();if(searching)return;setExpandedSubs(old=>({...old,[key]:!old[key]}));}}>{groupActions?.(items,names.get(sub)||'Інші деталі')}<h3>{names.get(sub)||'Інші деталі'}</h3><small>{items.length}</small></summary>{(searching||expandedSubs[key])&&items.slice(0,limits[key]||50).map(row=><div key={row.id}>{render(row)}</div>)}{(searching||expandedSubs[key])&&items.length>(limits[key]||50)&&<button onClick={()=>setLimits(old=>({...old,[key]:(old[key]||50)+50}))}>Ще 50 деталей</button>}</details>;})}
 </details>)}</div>;
}
