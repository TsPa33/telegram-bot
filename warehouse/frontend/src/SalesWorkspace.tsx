import {useEffect,useId,useRef,useState} from 'react';
import {all,api,ApiError,labels,money,type Page,type Row} from './api';
import {Modal,Pager,RecordForm,Empty} from './components';
import {Confirm,Heading,State,useLoad,type Notify} from './shared';
import {partFields,PartDetail} from './pages/Inventory';
import {useSearchParams} from 'react-router-dom';
import StockHistory from './StockHistory';

type Action={part:Row;type:string;key:string};
const actionLabels:Record<string,string>={sale:'Продати',write_off:'Списати',transfer:'Перемістити',reserve:'Зарезервувати',release:'Зняти резерв',receipt:'Додати кількість',correction:'Змінити кількість'};
export default function SalesWorkspace({quick=false,notify,accountId,grouped=false}:{quick?:boolean;notify:Notify;accountId:string;grouped?:boolean}) {
 const [params,setParams]=useSearchParams(),vehicle=params.get('vehicle_id')||'';
 const [brand,setBrand]=useState(''),[model,setModel]=useState(''),[q,setQ]=useState(''),[term,setTerm]=useState(''),[page,setPage]=useState(0),[showZero,setShowZero]=useState(false);
 const [detail,setDetail]=useState<Row|null>(null),[edit,setEdit]=useState<Row|null>(null),[price,setPrice]=useState<Row|null>(null),[action,setAction]=useState<Action|null>(null),[archive,setArchive]=useState<Row|null>(null),[history,setHistory]=useState<Row|null>(null);
 const [overrides,setOverrides]=useState<Record<string,Row>>({});
 const [pendingRequests,setPendingRequests]=useState<{partId:string;type:string;body:Row}[]>([]),[pendingError,setPendingError]=useState('');
 useEffect(()=>{const scan=()=>{try{const prefix='warehouse-stock-pending:'+accountId+':';setPendingRequests(Object.keys(sessionStorage).filter(k=>k.startsWith(prefix)).map(k=>{const [partId,type]=k.slice(prefix.length).split(':');return {partId,type,body:JSON.parse(sessionStorage.getItem(k)!)};}));}catch{setPendingError('Не вдалося прочитати непідтверджені операції.');}};scan();window.addEventListener('warehouse:stock-pending',scan);return()=>window.removeEventListener('warehouse:stock-pending',scan);},[accountId]);
 const [focused,setFocused]=useState(false),[suggestion,setSuggestion]=useState(-1);
 const lookups=useLoad(()=>Promise.all([all('/vehicles'),all('/vehicles?archived=true'),all('/categories')]),[]),vehicles=[...(lookups.data?.[0]||[]),...(lookups.data?.[1]||[])],categories=lookups.data?.[2]||[];
 useEffect(()=>{const timer=setTimeout(()=>{setTerm(q);setPage(0);setSuggestion(-1);},200);return()=>clearTimeout(timer);},[q]);
 const query=new URLSearchParams({q:term,in_stock:String(quick||!showZero),limit:'50',offset:String(page*50)});
 if(vehicle)query.set('vehicle_id',vehicle);if(brand)query.set('manufacturer',brand);if(model)query.set('model',model);
 const {data,error,loading,reload}=useLoad(()=>(grouped?all('/parts?'+new URLSearchParams([...query.entries()].filter(([k])=>k!=='limit'&&k!=='offset'))).then(items=>({items,total:items.length,offset:0,limit:items.length})):api<Page>('/parts?'+query)).then(result=>({...result,query_key:query.toString()})),[query.toString(),grouped]);
 useEffect(()=>{const changed=()=>{reload();lookups.reload();};window.addEventListener('warehouse:inventory-changed',changed);return()=>window.removeEventListener('warehouse:inventory-changed',changed);},[]);
 const current=data?.query_key===query.toString()&&q===term;
 const waiting=loading||q!==term||!current;
 const rows=current?data!.items.map(p=>overrides[p.id]||p).filter(p=>!p.archived&&(!(quick||!showZero)||p.quantity>0)):[],suggestions=rows.slice(0,5),optionsOpen=quick&&focused&&!!q&&!waiting&&!error;
 useEffect(()=>{setSuggestion(-1);setOverrides({});},[data]);
 const brands=[...new Set(vehicles.map(v=>v.manufacturer))].sort((a,b)=>a.localeCompare(b,'uk'));
 const models=[...new Set(vehicles.filter(v=>!brand||v.manufacturer===brand).map(v=>v.model))].sort((a,b)=>a.localeCompare(b,'uk'));
 const vehicleLabel=(id:string)=>{const v=vehicles.find(v=>v.id===id);return v?`${v.manufacturer} ${v.model} · ${v.year} · №${v.number}${v.archived?' · архів':''}`:'Без автомобіля';};
 function updated(row:Row){setOverrides(values=>({...values,[row.id]:row}));setDetail(current=>current?.id===row.id?row:current);window.dispatchEvent(new Event('warehouse:inventory-changed'));}
 function openAction(part:Row,type:string){setAction({part,type,key:crypto.randomUUID()});}
 const priceLabel=(p:Row)=>p.selling_price==null?'Вказати ціну':money(p.selling_price,p.currency||'UAH');
 const actions=(p:Row)=><PartActions part={p} onSale={()=>openAction(p,'sale')} onAction={type=>openAction(p,type)} onDetail={()=>setDetail(p)} onEdit={()=>setEdit(p)} onArchive={()=>setArchive(p)} onHistory={()=>setHistory(p)}/>;
 return <>
  {!grouped&&<Heading eyebrow={quick?'ШВИДКИЙ ПОШУК':'СКЛАД'} title={quick?'Пошук запчастин':'Запчастини та залишки'} description={quick?'Виберіть автомобіль і введіть назву, OEM або артикул.':'Наявні запчастини, ціни та швидкий продаж.'}>
   {!quick&&<button onClick={()=>setEdit({condition:'used',currency:'UAH',vehicle_id:vehicle})}>Додати запчастину</button>}
  </Heading>}
  {grouped&&<div className="donor-stock-heading"><h2>Запчастини на складі</h2><button onClick={()=>setEdit({condition:'used',currency:'UAH',vehicle_id:vehicle})}>Додати запчастину</button></div>}
  {!!pendingRequests.length&&<div className="notice" role="status">Є операції без підтвердженого результату. {pendingRequests.map(p=><button key={p.partId+p.type} onClick={async()=>{try{setAction({part:await api('/parts/'+p.partId),type:p.type,key:p.body.request_key});}catch(e){setPendingError((e as Error).message);}}}>Перевірити: {actionLabels[p.type]||'операцію'}</button>)}</div>}
  {pendingError&&<p role="alert" className="error">{pendingError}</p>}
  <section className="seller-search panel padded">
   <div className={`seller-filters ${grouped?'donor-scoped-filters':''}`}><label>Марка<select aria-label="Марка пошуку" value={brand} onChange={e=>{setBrand(e.target.value);setModel('');setParams({});setPage(0);}}><option value="">Усі марки</option>{brands.map(b=><option key={b}>{b}</option>)}</select></label>
    <label>Модель<select aria-label="Модель пошуку" value={model} onChange={e=>{setModel(e.target.value);setParams({});setPage(0);}}><option value="">Усі моделі</option>{models.map(m=><option key={m}>{m}</option>)}</select></label>
    <label>Автомобіль<select aria-label="Автомобіль пошуку" value={vehicle} onChange={e=>{setParams(e.target.value?{vehicle_id:e.target.value}:{});setPage(0);}}><option value="">Усі автомобілі</option>{vehicles.filter(v=>(!brand||v.manufacturer===brand)&&(!model||v.model===model)).map(v=><option key={v.id} value={v.id}>{vehicleLabel(v.id)}</option>)}</select></label>
   </div>
   <div className="seller-autocomplete"><label>Назва, OEM або артикул<input role={quick?'combobox':'searchbox'} aria-label="Пошук запчастин" aria-expanded={quick?optionsOpen:undefined} aria-autocomplete={quick?'list':undefined} aria-controls={quick?'part-suggestions':undefined} aria-activedescendant={suggestion>=0?`suggestion-${suggestion}`:undefined} placeholder="Наприклад, ка або OEM" value={q} onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)} onChange={e=>setQ(e.target.value)} onKeyDown={e=>{
    if(e.key==='Escape'){setFocused(false);setSuggestion(-1);}if(e.key==='ArrowDown'&&suggestions.length){e.preventDefault();setFocused(true);setSuggestion(i=>(i+1)%suggestions.length);}if(e.key==='ArrowUp'&&suggestions.length){e.preventDefault();setSuggestion(i=>(i+suggestions.length-1)%suggestions.length);}if(e.key==='Enter'&&optionsOpen&&suggestion>=0){e.preventDefault();setDetail(suggestions[suggestion]);setFocused(false);}
   }}/></label>
   {optionsOpen&&<ul role="listbox" id="part-suggestions" aria-label="Підказки запчастин">{suggestions.map((p,i)=><li key={p.id}><button role="option" id={`suggestion-${i}`} aria-selected={suggestion===i} onPointerDown={e=>e.preventDefault()} onMouseDown={e=>e.preventDefault()} onClick={()=>{setDetail(p);setFocused(false);}}>{p.name}<small>{p.available_quantity} вільних · {priceLabel(p)}</small></button></li>)}{!suggestions.length&&<li>Нічого не знайдено</li>}</ul>}
   </div>
   {!quick&&<label className="check-inline stock-zero-toggle"><input type="checkbox" role="switch" aria-label="Показати без залишку" checked={showZero} onChange={e=>{setShowZero(e.target.checked);setPage(0);}}/>Показати без залишку</label>}
  </section>
  <State error={error||lookups.error} loading={waiting||lookups.loading}/>
  <section className="panel seller-results" aria-label="Результати пошуку">
   {grouped&&<StockTree rows={rows} categories={categories} render={p=><article className="donor-part-row"><button className="text-button strong" onClick={()=>setDetail(p)}>{p.name}</button><small>{labels[p.condition]} · У наявності: {p.available_quantity} · {p.location||'Місце не вказано'}</small><button className="seller-price" aria-label={`Ціна ${p.name}`} onClick={()=>setPrice(p)}>{priceLabel(p)}</button>{actions(p)}</article>}/>}
   {!!rows.length&&!grouped&&<><table className="desktop-table"><thead><tr><th>Запчастина</th><th>Автомобіль</th><th>У наявності</th><th>Ціна / валюта</th><th>Дія</th></tr></thead><tbody>{rows.map(p=><tr key={p.id}><td><button className="text-button strong" onClick={()=>setDetail(p)}>{p.name}</button><small>{labels[p.condition]}{p.location?` · ${p.location}`:''}</small></td><td>{vehicleLabel(p.vehicle_id)}</td><td><b>{p.available_quantity}</b>{p.available_quantity===0&&p.quantity>0&&<small>У резерві</small>}</td><td><button className="seller-price" aria-label={`Ціна ${p.name}`} onClick={()=>setPrice(p)}>{priceLabel(p)}</button></td><td>{actions(p)}</td></tr>)}</tbody></table>
    <div className="mobile-cards">{rows.map(p=><article className="inventory-card seller-card" key={p.id}><button className="text-button strong" onClick={()=>setDetail(p)}>{p.name}</button><small>{vehicleLabel(p.vehicle_id)}</small><div className="seller-card-line"><b>У наявності: {p.available_quantity}</b><button className="seller-price" aria-label={`Ціна ${p.name}`} onClick={()=>setPrice(p)}>{priceLabel(p)}</button></div><p>{labels[p.condition]} · {p.location||'Місце не вказано'}</p>{actions(p)}</article>)}</div><Pager total={data?.total||0} page={page} setPage={setPage}/></>}
   {!waiting&&!rows.length&&<Empty title="Нічого не знайдено">Змініть назву або автомобіль.</Empty>}
  </section>
  {price&&<PriceDialog part={price} onClose={()=>setPrice(null)} onSaved={row=>{updated(row);setPrice(null);notify('Ціну збережено');}}/>}
  {action&&<OperationDialog action={action} onClose={()=>setAction(null)} onSaved={row=>{updated(row);setAction(null);notify('Операцію проведено');}}/>}
  {edit&&<Modal title={edit.id?'Картка запчастини':'Нова запчастина'} onClose={()=>setEdit(null)}><RecordForm fields={partFields(vehicles,categories)} initial={edit} onSave={async body=>{const row=await api('/parts'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',body);updated(row);setEdit(null);setDetail(row);notify('Картку збережено');}}/></Modal>}
  {detail&&<Modal title={detail.name} onClose={()=>setDetail(null)}><div className="seller-detail-top"><p>{vehicleLabel(detail.vehicle_id)}</p>{detail.oem_number&&<span>OEM: {detail.oem_number}</span>}{detail.article_number&&<span>Артикул: {detail.article_number}</span>}<strong>У наявності: {detail.available_quantity}</strong><button className="seller-price" aria-label={`Ціна ${detail.name}`} onClick={()=>setPrice(detail)}>{priceLabel(detail)}</button><p>{labels[detail.condition]} · {detail.location||'Місце не вказано'}</p></div>{detail.description&&<p className="stock-part-notes">{detail.description}</p>}{detail.internal_notes&&<p className="stock-part-notes">Примітки: {detail.internal_notes}</p>}<div className="stock-detail-actions"><button className="primary" disabled={detail.available_quantity<1} onClick={()=>openAction(detail,'sale')}>Продати</button><button onClick={()=>setEdit(detail)}>Редагувати</button><button onClick={()=>openAction(detail,'reserve')}>Зарезервувати</button><button onClick={()=>openAction(detail,'transfer')}>Перемістити</button><button onClick={()=>openAction(detail,'write_off')}>Списати</button><button onClick={()=>setHistory(detail)}>Історія</button></div><details className="seller-extra"><summary>Докладніше</summary><PartDetail part={detail} onChanged={async()=>{const row=await api('/parts/'+detail.id);updated(row);}}/><button onClick={()=>setEdit(detail)}>Редагувати дані</button></details></Modal>}
  {history&&<Modal title={`Історія: ${history.name}`} onClose={()=>setHistory(null)}><StockHistory partId={history.id}/></Modal>}
  {archive&&<Confirm title="Архівувати запчастину?" text="Історія й залишки зберігаються. Позиція зникне з пошуку." onClose={()=>setArchive(null)} onConfirm={async()=>{await api('/archive/parts/'+archive.id,'POST');if(detail?.id===archive.id)setDetail(null);setArchive(null);window.dispatchEvent(new Event('warehouse:inventory-changed'));}}/>}
 </>;
}
function PriceDialog({part,onClose,onSaved}:{part:Row;onClose:()=>void;onSaved:(row:Row)=>void}){
 const [amount,setAmount]=useState(part.selling_price??''),[currency,setCurrency]=useState(part.currency||'UAH'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 return <Modal title="Ціна запчастини" onClose={onClose}><form onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{const normalized=String(amount).replace(',','.');if(normalized&&!/^\d{1,12}(\.\d{1,2})?$/.test(normalized))throw Error('Вкажіть суму з точністю до двох знаків');onSaved(await api('/parts/'+part.id+'/price','PATCH',{selling_price:normalized||null,currency}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
  <label>Сума<input aria-label="Сума" inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Валюта<select aria-label="Валюта" value={currency} onChange={e=>setCurrency(e.target.value)}><option>UAH</option><option>USD</option></select></label>{error&&<p role="alert" className="error">{error}</p>}<div className="modal-actions"><button type="submit" className="primary" disabled={busy}>Зберегти</button></div></form></Modal>;
}
function OperationDialog({action,onClose,onSaved}:{action:Action;onClose:()=>void;onSaved:(row:Row)=>void}){
 const {part,type}=action,[quantity,setQuantity]=useState('1'),[location,setLocation]=useState(part.location||''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 // Persist unresolved requests across modal/page reload. Retries must keep the
 // exact body/key; after a completed operation a new deliberate action gets a new key.
 const pendingKey='warehouse-stock-pending:'+part.account_id+':'+part.id+':'+type;
 const pending=useRef<Row|null>(null),submitting=useRef(false);
 useEffect(()=>{try{const saved=sessionStorage.getItem(pendingKey);if(saved){pending.current=JSON.parse(saved);setQuantity(String(pending.current!.quantity??1));setLocation(pending.current!.location??part.location??'');setReason(pending.current!.reason||'');setError('Є непідтверджений запит. Повторіть, щоб перевірити його результат.');}}catch{setError('Не вдалося прочитати попередній запит.');}},[]);
 return <Modal title={`${actionLabels[type]}: ${part.name}`} onClose={onClose}><form onSubmit={async e=>{e.preventDefault();if(submitting.current)return;submitting.current=true;setBusy(true);setError('');try{
   const body=pending.current||{type,quantity:type==='transfer'?0:Number(quantity),...(type==='transfer'?{location}:{}),reason:reason||(type==='sale'?'Продаж':type==='write_off'?'':actionLabels[type]),request_key:action.key};
   pending.current=body;sessionStorage.setItem(pendingKey,JSON.stringify(body));window.dispatchEvent(new Event('warehouse:stock-pending'));
   await api('/parts/'+part.id+'/operations','POST',body);const row=await api('/parts/'+part.id);sessionStorage.removeItem(pendingKey);window.dispatchEvent(new Event('warehouse:stock-pending'));onSaved(row);
  }catch(e){if(e instanceof ApiError&&[409,422].includes(e.status)){sessionStorage.removeItem(pendingKey);pending.current=null;window.dispatchEvent(new Event('warehouse:stock-pending'));}setError((e as Error).message);}finally{submitting.current=false;setBusy(false);}}}>
  <p>У наявності: {part.available_quantity}</p>
  {type==='transfer'?<label>Нове місце<input aria-label="Нове місце" required maxLength={120} disabled={!!pending.current} value={location} onChange={e=>setLocation(e.target.value)}/></label>:<label>Кількість<input aria-label="Кількість" type="number" min={type==='correction'?0:1} max={type==='sale'||type==='write_off'||type==='reserve'?part.available_quantity:1000000} step={1} required disabled={!!pending.current} value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>}
  <label>{type==='write_off'?'Причина списання':'Примітка (необов’язково)'}<input aria-label={type==='write_off'?'Причина списання':'Примітка (необов’язково)'} required={type==='write_off'} minLength={type==='write_off'?3:undefined} maxLength={2000} disabled={!!pending.current} value={reason} onChange={e=>setReason(e.target.value)}/></label>
  {error&&<p role="alert" className="error">{error}</p>}<div className="modal-actions"><button type="submit" className="primary" disabled={busy}>Підтвердити</button></div>
 </form></Modal>;
}

function StockTree({rows,categories,render}:{rows:Row[];categories:Row[];render:(row:Row)=>import('react').ReactNode}) {
 const [expanded,setExpanded]=useState<Record<string,boolean>>({}),[limits,setLimits]=useState<Record<string,number>>({});
 const names=new Map(categories.map(c=>[c.id,c.name]));
 const groups=new Map<string,Map<string,Row[]>>();
 for(const row of rows){const category=row.category_id||'',sub=row.subcategory_id||'';if(!groups.has(category))groups.set(category,new Map());const subs=groups.get(category)!;if(!subs.has(sub))subs.set(sub,[]);subs.get(sub)!.push(row);}
 return <div className="donor-stock-tree">{[...groups].map(([id,subs])=><details key={id} open={!!expanded[id]} onToggle={e=>{const open=e.currentTarget.open;setExpanded(old=>({...old,[id]:open}));}}>
  <summary><strong>{names.get(id)||'Без категорії'}</strong><small>{[...subs.values()].reduce((n,items)=>n+items.length,0)}</small></summary>
  {expanded[id]&&[...subs].map(([sub,items])=>{const key=id+':'+sub;return <section className="donor-stock-subcategory" key={sub}><h3>{names.get(sub)||'Інші деталі'} <small>{items.length}</small></h3>{items.slice(0,limits[key]||50).map(row=><div key={row.id}>{render(row)}</div>)}{items.length>(limits[key]||50)&&<button onClick={()=>setLimits(old=>({...old,[key]:(old[key]||50)+50}))}>Ще 50 деталей</button>}</section>;})}
 </details>)}</div>;
}

function PartActions({part,onSale,onAction,onDetail,onEdit,onArchive,onHistory}:{part:Row;onSale:()=>void;onAction:(type:string)=>void;onDetail:()=>void;onEdit:()=>void;onArchive:()=>void;onHistory:()=>void}){
 const id=useId(),ref=useRef<HTMLDivElement>(null),button=useRef<HTMLButtonElement>(null);
 useEffect(()=>{const follow=(e:Event)=>{const menu=ref.current;if(!menu?.matches(':popover-open')||(e.target instanceof Node&&menu.contains(e.target)))return;const rect=button.current!.getBoundingClientRect();if(rect.bottom<0||rect.top>innerHeight)menu.hidePopover();else position();};window.addEventListener('scroll',follow,true);window.addEventListener('resize',follow);return()=>{window.removeEventListener('scroll',follow,true);window.removeEventListener('resize',follow);};},[]);
 function position(){const rect=button.current!.getBoundingClientRect(),menu=ref.current!;const width=Math.min(220,innerWidth-24);menu.style.width=width+'px';menu.style.left=Math.max(12,Math.min(rect.right-width,innerWidth-width-12))+'px';const below=innerHeight-rect.bottom-12,above=rect.top-12;menu.style.maxHeight=Math.max(80,Math.max(below,above))+'px';menu.style.top=below>=Math.min(360,above)?rect.bottom+4+'px':'auto';menu.style.bottom=below>=Math.min(360,above)?'auto':innerHeight-rect.top+4+'px';}
 const run=(action:()=>void)=>{ref.current?.hidePopover();action();};
 return <div className="seller-actions"><button className="primary" disabled={part.available_quantity<1} onClick={onSale}>Продати</button><button ref={button} popoverTarget={id} onClick={position} aria-label={`Дії ${part.name}`}>⋯</button><div ref={ref} id={id} popover="auto" className="stock-actions-menu">
  {['write_off','transfer','reserve','release','receipt','correction'].map(type=><button key={type} onClick={()=>run(()=>onAction(type))}>{actionLabels[type]}</button>)}<button onClick={()=>run(onDetail)}>Відкрити картку</button><button onClick={()=>run(onEdit)}>Редагувати дані</button><button onClick={()=>run(onHistory)}>Історія</button><button onClick={()=>run(onArchive)}>Архівувати</button>
 </div></div>;
}
