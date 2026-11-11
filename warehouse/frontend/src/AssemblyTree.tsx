import {Link} from 'react-router-dom';
import {useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {api,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';
import {Box,Check,ChevronDown,ChevronRight,Layers,Minus,Plus,Search,Settings2,TriangleAlert,X,MoreHorizontal,List,Network,DoorOpen,Cog,Zap,Armchair,Wind,ShieldCheck,Lightbulb,Disc,Settings} from 'lucide-react';
import {usePlanBulk,BulkStatus,BulkActionBar,GuidedReceipt,SelectionCheck} from './DismantlingBulk';
import './assembly-tree.css';

/** Optional inline view over existing donor placements, never a stock generator. */
export default function AssemblyTree({vehicle,onReady,revision=0}:{vehicle:Row;onReady?:(enabled:boolean)=>void;revision?:number}) {
 const can=useCan(),who=useContext(TeamIdentity);
 const scope=JSON.stringify([who?.id,who?.workspace_account_id,vehicle.id]);
 const [assemblyEnabled,setAssemblyEnabled]=useState(false),[enabled,setEnabled]=useState(false),[data,setData]=useState<Row|null>(null),[open,setOpen]=useState<Set<string>>(new Set()),[q,setQ]=useState(''),[limit,setLimit]=useState(50);
 const [selected,setSelected]=useState<Row|null>(null),[preview,setPreview]=useState<Row|null>(null),[error,setError]=useState(''),[commandBusy,setBusy]=useState(false),[physical,setPhysical]=useState(false),[child,setChild]=useState(''),[legacyPart,setLegacyPart]=useState('');
 const [price,setPrice]=useState(''),[currency,setCurrency]=useState('UAH'),[description,setDescription]=useState(''),[remainder,setRemainder]=useState(false),[confirmSale,setConfirmSale]=useState(false),[confirmReturn,setConfirmReturn]=useState(false);
 const [photo,setPhoto]=useState('');
 useEffect(()=>{let active=true;setPhoto('');if(selected?.part_id)api(`/parts/${selected.part_id}/photos`).then(rows=>{if(active)setPhoto(rows[0]?.url||'')}).catch(()=>{});return()=>{active=false}},[selected?.part_id]);
 const [category,setCategory]=useState(''),[status,setStatus]=useState('all'),[mode,setMode]=useState('tree'),[note,setNote]=useState('');
 const inspectorRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(selected&&preview&&window.innerWidth<=650){inspectorRef.current?.focus({preventScroll:true});inspectorRef.current?.scrollIntoView({block:'start',behavior:'instant'});}},[selected?.id,preview?.token]);
 const previewEpoch=useRef(0);
 const epoch=useRef(0),pending=useRef<{fingerprint:string;key:string}|null>(null),writing=useRef(false);
 const [bulkPlan,setBulkPlan]=useState<Row|null>(null),[checkedIds,setCheckedIds]=useState<string[]>([]),[receiptOpen,setReceiptOpen]=useState(false),[toolbarHeight,setToolbarHeight]=useState(0);
 const planPath=`/vehicles/${vehicle.id}/dismantling-v3`;
 const bulk=usePlanBulk({path:planPath,scope:{actor:String(who?.id||''),workspace:String(who?.workspace_account_id||who?.id||''),vehicle:String(vehicle.id)},onLoad:()=>load(),onSelection:setCheckedIds,onComplete:()=>{setReceiptOpen(false);window.dispatchEvent(new Event('warehouse:inventory-changed'));}});
 const busy=commandBusy||bulk.busy||!!bulk.intent;
 const editable=can('dismantling.manage')&&can('inventory.edit')&&can('inventory.adjust_quantity');
 async function load(ticket=epoch.current) {
  const result=await api(`/vehicles/${vehicle.id}/assemblies`);
  const managed=can('catalog.view')?await api(planPath):null;
  if(ticket===epoch.current){setData(result);setBulkPlan(managed);setCheckedIds(ids=>ids.filter(id=>managed?.items.some((n:Row)=>n.id===id&&n.selectable)));}return managed||result;
 }
 useEffect(()=>{
  const ticket=++epoch.current;setData(null);setBulkPlan(null);setCheckedIds([]);setReceiptOpen(false);setEnabled(false);setCategory('');setStatus('all');setMode('tree');setSelected(null);setPreview(null);setError('');setOpen(new Set());setQ('');setLimit(50);pending.current=null;writing.current=false;setBusy(false);
  api(`/vehicles/${vehicle.id}/assemblies/readiness`).then(async r=>{if(ticket!==epoch.current)return;setAssemblyEnabled(r.enabled);const ready=r.workspace_enabled??r.enabled;setEnabled(ready);onReady?.(ready&&can('inventory.view'));if(ready&&can('inventory.view'))await load(ticket)}).catch(e=>{if(ticket===epoch.current){setError(e.message)}});
  return()=>{epoch.current++};
 },[scope,revision]);
 async function select(node:Row) {
  const request=++previewEpoch.current;const ticket=epoch.current;setSelected(node);setNote(node.note||'');setPreview(null);setPhysical(false);setConfirmSale(false);setConfirmReturn(false);setDescription('');setChild('');setError('');
  try{const value=await api(`/vehicles/${vehicle.id}/assemblies/${node.id}/preview`);if(ticket===epoch.current&&request===previewEpoch.current){
    setPreview(value);
    const root=value.items.find((i:Row)=>i.item_id===node.id);
    if(root){const completeness=value.incomplete&&(root.completeness!=null||value.items.length>1)?'incomplete':root.completeness;
     setSelected(old=>old?.id===node.id?{...old,completeness}:old);
     setData(old=>old?{...old,items:old.items.map((i:Row)=>i.id===node.id?{...i,completeness}:i)}:old);
    }
   }}catch(e){if(ticket===epoch.current)setError((e as Error).message)}
 }
 async function send(action:string,body:Row,part?:string) {
  if(writing.current||bulk.busy||bulk.intent)return;writing.current=true;setBusy(true);setError('');const ticket=epoch.current;
  const fingerprint=JSON.stringify([scope,action,body,part]);
  if(pending.current?.fingerprint!==fingerprint)pending.current={fingerprint,key:crypto.randomUUID()};
  try{
   await api(part?`/parts/${part}/operations`:`/vehicles/${vehicle.id}/assemblies`,'POST',{...body,request_key:pending.current.key,...(!part?{action}: {})});
   if(ticket!==epoch.current)return;
   pending.current=null;const fresh=await load(ticket);if(action==='inspect'){const node=fresh.items.find((n:Row)=>n.id===body.item_id);if(node)await select(node);}else{setPreview(null);setSelected(null);}window.dispatchEvent(new Event('warehouse:inventory-changed'));
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}finally{if(ticket===epoch.current){writing.current=false;setBusy(false)}}
 }
 if(!enabled||!can('inventory.view'))return error?<p role="alert">{error}</p>:null;
 if(!data)return <p role={error?'alert':'status'}>{error||'Завантажуємо фізичний склад…'}</p>;
 const items:Row[]=data.items||[],byId=new Map(items.map(n=>[n.id,n])),children=new Map<string,Row[]>();
 items.forEach(n=>{if(n.parent_id)children.set(n.parent_id,[...(children.get(n.parent_id)||[]),n])});
 children.forEach(rows=>rows.sort((a,b)=>String(a.name).localeCompare(String(b.name),'uk',{numeric:true})));
 const categories=[...new Set(items.map(n=>String(n.category||'Інші деталі')))];
 function icon(name:string){const Icon=/двер/i.test(name)?DoorOpen:/двиг|трансм/i.test(name)?Cog:/електр/i.test(name)?Zap:/салон|інтер/i.test(name)?Armchair:/клімат/i.test(name)?Wind:/безпек/i.test(name)?ShieldCheck:/освіт/i.test(name)?Lightbulb:/гальм/i.test(name)?Disc:/кермов|підвіск/i.test(name)?Settings:Box;return <Icon size={20} strokeWidth={1.6}/>;}
 const checked=items.filter(n=>['present','damaged'].includes(n.presence)).length,attention=items.filter(n=>['unchecked','damaged','absent'].includes(n.presence)||n.completeness==='incomplete'||n.category==='Потребує уточнення').length,stocked=items.filter(n=>n.part_id&&!n.parent_id&&!n.consumed_operation_id&&!n.archived&&n.quantity>0).length;
 function stockLabel(n:Row){return n.consumed_operation_id||n.consumed_type==='sale'||n.consumed_type==='write_off'?(n.consumed_type==='sale'?(n.parent_id?'Продано у складі вузла':'Продано'):'Списано'):n.parent_id?'У складі вузла':n.part_id&&n.quantity>0?'На складі':n.part_id?'Немає залишку':'Ще не на складі'}
 function presenceLabel(n:Row){return ({present:'Є в автомобілі',damaged:'Пошкоджена',absent:'Відсутня'} as Record<string,string>)[n.presence]||'Перевірити наявність'}
 async function inspect(n:Row,presence:string,quantity:number,noteValue:string){
  const ticket=epoch.current;try{const current=selected?.id===n.id&&preview?preview:await api(`/vehicles/${vehicle.id}/assemblies/${n.id}/preview`);if(ticket!==epoch.current)return;const root=current.items.find((i:Row)=>i.item_id===n.id);if(!root||root.quantity!==(n.part_id?n.quantity:null)||root.planned_quantity!==n.planned_quantity||root.note!==(n.note||''))throw Error('Дані змінилися. Оновіть список перед редагуванням.');await send('inspect',{item_id:n.id,token:current.token,presence,quantity,note:noteValue});}catch(e){setError((e as Error).message)}
 }
 async function receive(n:Row){const ticket=epoch.current;try{const current=selected?.id===n.id&&preview?preview:await api(`/vehicles/${vehicle.id}/assemblies/${n.id}/preview`);if(ticket!==epoch.current)return;const root=current.items.find((i:Row)=>i.item_id===n.id);if(!root||root.planned_quantity!==n.planned_quantity)throw Error('Кількість змінилася. Відкрийте деталь ще раз.');await send('receipt',{item_id:n.id,token:current.token,confirm_physical:true});}catch(e){setError((e as Error).message)}}
 const matches=items.filter(n=>(!category||n.category===category)&&(!q.trim()||String(n.name).toLocaleLowerCase('uk').includes(q.trim().toLocaleLowerCase('uk')))&&(status==='all'||status==='confirmed'&&['present','damaged'].includes(n.presence)||status===n.presence||status==='stock'&&stockLabel(n)==='На складі'||status==='sold'&&n.consumed_type==='sale'));
 const managedById=new Map<string,Row>((bulkPlan?.items||[]).map((n:Row)=>[n.id,n]));
 const selectable=matches.filter(n=>managedById.get(n.id)?.selectable).map(n=>String(n.id));
 const chosen=checkedIds.map(id=>managedById.get(id)).filter((n):n is Row=>!!n);
 const matching=new Set<string>();matches.forEach(n=>{let cursor:Row|undefined=n;while(cursor&&!matching.has(cursor.id)){matching.add(cursor.id);cursor=byId.get(cursor.parent_id)}});
 const roots=(mode==='list'?matches:items.filter(n=>!n.parent_id&&matching.has(n.id))).sort((a,b)=>Number(!!b.completeness)-Number(!!a.completeness)||String(a.name).localeCompare(String(b.name),'uk',{numeric:true}));
 function render(node:Row):ReactNode {
  const kids=(children.get(node.id)||[]).filter(n=>matching.has(n.id)),expanded=open.has(node.id)||!!q||status!=='all';
  const amount=node.parent_id?node.planned_quantity:node.part_id?node.quantity:node.planned_quantity;
  const individual=!!node.parent_id||!!node.completeness||!!children.get(node.id)?.length||node.individually_tracked;
  const locked=busy||!editable||individual||!!node.consumed_type||!!node.consumed_operation_id||!!node.reserved||node.archived;
  return <li key={node.id}>
   <div className={`assembly-node ${selected?.id===node.id?'is-selected':''}`} onClick={e=>{if(!(e.target as HTMLElement).closest('button,input,a,select'))void select(node)}}>
    <span className="assembly-select-expand">{editable&&managedById.get(node.id)?.selectable&&<SelectionCheck label={`Вибрати: ${node.name}`} ids={[node.id]} selected={new Set(checkedIds)} disabled={busy||receiptOpen} onToggle={value=>setCheckedIds(ids=>value?[...new Set([...ids,node.id])]:ids.filter(id=>id!==node.id))}/>}<button className="assembly-expand" aria-label={`${expanded?'Згорнути':'Розгорнути'} ${node.name}`} aria-expanded={kids.length?expanded:undefined} disabled={!kids.length||mode==='list'} onClick={()=>setOpen(old=>{const next=new Set(old);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next})}>{kids.length?(expanded?<ChevronDown size={16}/>:<ChevronRight size={16}/>):<span/>}</button></span>
    <button className="assembly-name" id={'assembly-node-'+node.id} aria-label={node.name} onClick={()=>void select(node)}>{icon(node.name+' '+node.category)}<span><strong>{node.name}</strong>{node.completeness&&<small>{node.completeness==='complete'?'Комплектний вузол':node.completeness==='incomplete'?'Неповний комплект':'Перевірте склад вузла'}</small>}</span></button>
    <span className="assembly-row-category" title={node.category}>{node.category==='Потребує уточнення'?'Без категорії':node.category}</span>
    <button className={`assembly-status is-${node.presence}`} onClick={()=>void select(node)}>{node.presence==='present'?<Check size={14}/>:node.presence==='damaged'?<TriangleAlert size={14}/>:node.presence==='absent'?<X size={14}/>:<Search size={14}/>} {presenceLabel(node)}</button>
    <div className="assembly-counter" role="group" aria-label={`Кількість: ${node.name}`} title={individual?'Одна фізична позиція; дублювання кількості заборонене':node.part_id?'Фактичний залишок складу':'Кількість у плані, не складський залишок'}><button aria-label={`Зменшити кількість: ${node.name}`} disabled={locked||amount<=(node.part_id?0:1)} onClick={()=>void inspect(node,node.presence,amount-1,node.note)}><Minus size={14}/></button><output>{amount}</output><button aria-label={`Збільшити кількість: ${node.name}`} disabled={locked} onClick={()=>void inspect(node,node.presence,amount+1,node.note)}><Plus size={14}/></button></div>
    {!node.part_id&&!node.parent_id&&!node.consumed_operation_id&&editable&&can('inventory.create')&&['present','damaged'].includes(node.presence)?<button className="assembly-receipt" disabled={busy} onClick={()=>void receive(node)}><Box size={14}/>Додати на склад</button>:<span className="assembly-row-stock">{stockLabel(node)}</span>}
    {!node.part_id&&!['present','damaged'].includes(node.presence)&&!node.parent_id&&<button className="assembly-row-action" onClick={()=>void select(node)}>Підтвердити</button>}
    {node.part_id&&<button className="assembly-row-action" onClick={()=>void select(node)}>Переглянути</button>}
    <button className="assembly-more" aria-label={`Дії: ${node.name}`} onClick={()=>void select(node)}><MoreHorizontal size={18}/></button>
   </div>{expanded&&kids.length>0&&mode==='tree'&&<ul>{kids.map(render)}</ul>}
  </li>;
 }
 return <section className="assembly-tree" aria-label="Фізичний склад вузлів" style={{paddingBottom:toolbarHeight?toolbarHeight+16:undefined}}>
  <div className="assembly-plan-ready"><Check size={20}/><strong>{items.length?'План розбору сформовано':'Сформуйте список запчастин для автомобіля'}</strong></div>
  <header className="assembly-overview"><div className="assembly-metrics" role="region" aria-label="Показники розбору">{[['У плані',items.length],['Підтверджено',checked],['На складі',stocked],['Потребує уваги',attention]].map(([label,value])=><div key={label}><span>{label==='На складі'?<Box size={22}/>:label==='Потребує уваги'?<TriangleAlert size={22}/>:<Check size={22}/>}</span><div><small>{label}</small><strong>{value}</strong></div></div>)}</div><div className="assembly-top-actions"><button className="primary" disabled={busy||!editable||!can('inventory.create')||!(checkedIds.length||selectable.length)} onClick={()=>{if(!checkedIds.length)setCheckedIds(selectable);setReceiptOpen(true);}}><Box size={18}/>{checkedIds.length?'Додати вибрані на склад':'Додати доступні на склад'}</button><details><summary><Settings2 size={16}/>Швидкі дії</summary><button disabled={busy} onClick={()=>void load().catch(e=>setError(e.message))}>Оновити список</button><button onClick={()=>{setQ('');setCategory('');setStatus('unchecked')}}>Знайти непідтверджені</button><button onClick={()=>{setQ('');setCategory('');setStatus('damaged')}}>Переглянути пошкодження</button></details></div></header>
  {error&&<p role="alert">{error}</p>}
  <BulkStatus bulk={bulk}/>
  {receiptOpen&&<GuidedReceipt path={planPath} ids={checkedIds} bulk={bulk} onBack={()=>setReceiptOpen(false)}/>}
  {editable&&bulkPlan&&<div className="assembly-selection" role="group" aria-label="Вибір деталей для масових дій"><label><SelectionCheck ids={selectable} selected={new Set(checkedIds)} disabled={busy||receiptOpen} label="Вибрати всі за поточними фільтрами" onToggle={value=>setCheckedIds(ids=>value?[...new Set([...ids,...selectable])]:ids.filter(id=>!selectable.includes(id)))}/>Вибрати всі за поточними фільтрами ({selectable.length})</label><button disabled={busy||receiptOpen||!checkedIds.length} onClick={()=>setCheckedIds([])}>Зняти вибір ({checkedIds.length})</button><p>Вибір не змінює залишки. Спочатку підтвердьте фізичну наявність і демонтаж, потім перевірте надходження.</p></div>}
  {editable&&chosen.length>0&&!receiptOpen&&<BulkActionBar items={chosen} disabled={busy} onAction={(action,reason)=>void bulk.start(action,checkedIds,bulkPlan!.etag,reason)} onReceipt={()=>{bulk.resetFeedback();setReceiptOpen(true);}} onClear={()=>setCheckedIds([])} onHeight={setToolbarHeight}/>}
  <div className={`assembly-workspace ${selected?'has-inspector':''}`}>
   <nav className="assembly-categories" aria-label="Категорії запчастин"><h3>Категорії запчастин</h3><button aria-pressed={!category} onClick={()=>{setCategory('');setLimit(50)}}><Layers size={20}/><span>Усі категорії</span><b>{items.length}</b></button>{categories.map(c=><button key={c} aria-pressed={category===c} onClick={()=>{setCategory(c);setLimit(50)}}>{icon(c)}<span>{c==='Потребує уточнення'?'Без категорії':c}</span><b>{items.filter(n=>(n.category||'Інші деталі')===c).length}</b></button>)}</nav>
   <div className="assembly-center"><div className="assembly-toolbar"><label><Search size={18}/><input aria-label="Пошук у дереві" placeholder="Пошук запчастини…" value={q} onChange={e=>{setQ(e.target.value);setLimit(50)}}/></label><select aria-label="Статус деталей" value={status} onChange={e=>{setStatus(e.target.value);setLimit(50)}}>{[['all','Усі статуси'],['unchecked','Перевірити наявність'],['present','Є в автомобілі'],['confirmed','Наявність підтверджено'],['damaged','Пошкоджена'],['absent','Відсутня'],['stock','На складі'],['sold','Продано']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select><div className="assembly-view"><button aria-pressed={mode==='tree'} onClick={()=>setMode('tree')}><Network size={16}/>Дерево</button><button aria-pressed={mode==='list'} onClick={()=>setMode('list')}><List size={16}/>Список</button></div></div>
    <div className="assembly-filter-tabs" role="group" aria-label="Швидкі фільтри">{[['all','Усі'],['unchecked','Потрібно підтвердити'],['confirmed','Підтверджено'],['stock','На складі']].map(([value,label])=><button key={value} aria-pressed={status===value} onClick={()=>{setStatus(value);setLimit(50)}}>{label}</button>)}</div>
    <div className="assembly-column-head" aria-hidden="true"><span>Запчастина</span><span>Категорія</span><span>Кількість</span><span>Статус</span><span>Дія</span></div>
    {!matches.length&&<p className="assembly-empty">Деталей за цими умовами немає.</p>}<ul className="assembly-roots">{roots.slice(0,limit).map(render)}</ul>
    {roots.length>limit&&<button onClick={()=>setLimit(n=>n+50)}>Показати ще 50 позицій</button>}
   </div>
  {selected&&<div ref={inspectorRef} tabIndex={-1} role="region" className="assembly-inspector" aria-label="Картка запчастини"><div className="assembly-heading"><h4>{selected.name}</h4><button onClick={()=>{previewEpoch.current++;document.getElementById('assembly-node-'+selected.id)?.focus();setSelected(null);setPreview(null)}}>Закрити картку</button></div>
   {!preview?<p role="status">{error?'Не вдалося перевірити склад.':'Перевіряємо склад…'}</p>:<>

    <p className="assembly-breadcrumb">{selected.category} › {selected.subcategory}</p>
    <div className="assembly-photo">{photo?<img src={photo} alt={selected.name} onError={()=>setPhoto('')}/>:<><Box size={44}/><span>Фото ще немає</span></>}</div>
    <h5>Наявність на автомобілі</h5>
    <div className="assembly-presence" role="group" aria-label="Наявність на автомобілі">{(['present','damaged','absent'] as const).map(value=><button key={value} aria-pressed={selected.presence===value} disabled={busy||!editable||!!selected.consumed_type||!!selected.consumed_operation_id||!!selected.archived||preview.conflicts.length>0} onClick={()=>void inspect(selected,value,selected.part_id?selected.quantity:selected.planned_quantity,note)}>{value==='present'?<Check size={16}/>:value==='damaged'?<TriangleAlert size={16}/>:<X size={16}/>}{{present:'Підтвердити наявність',damaged:'Позначити пошкодження',absent:'Позначити відсутність'}[value]}</button>)}</div>
    <p className="assembly-stock-label">{stockLabel(selected)} · Кількість: {selected.parent_id?selected.planned_quantity:selected.part_id?selected.quantity:selected.planned_quantity}</p>
    <label>Примітка<textarea maxLength={2000} value={note} disabled={!editable||busy||!!selected.consumed_type||!!selected.consumed_operation_id} onChange={e=>setNote(e.target.value)} placeholder="Стан, особливості, пошкодження…"/></label>
    <button className="secondary" disabled={busy||!editable||!!selected.consumed_type||!!selected.consumed_operation_id||note===(selected.note||'')} onClick={()=>void inspect(selected,selected.presence,selected.part_id?selected.quantity:selected.planned_quantity,note)}>Зберегти примітку</button>
    {editable&&!selected.part_id&&!selected.parent_id&&!selected.consumed_operation_id&&can('inventory.create')&&<button className="primary" disabled={busy||!['present','damaged'].includes(selected.presence)} onClick={()=>void receive(selected)}><Box size={18}/>Додати на склад</button>}
    {selected.part_id&&<Link className="assembly-part-link" to={'/inventory?vehicle_id='+vehicle.id}>Перейти до складу автомобіля</Link>}
    {!!preview.issues?.length&&<p role="alert">Комплектність потребує перевірки: {preview.issues.map((i:Row)=>`${i.name} — ${{absent:'відсутня',damaged:'пошкоджена',archived:'архівована'}[i.reason as 'absent'|'damaged'|'archived']}`).join('; ')}</p>}
    <details className="assembly-composition" open={!!selected.completeness}><summary>Фактичний склад</summary><ul>{preview.items.map((n:Row)=><li key={n.item_id}>{n.name}{n.condition==='damaged'?' · Пошкоджено':''}{n.presence==='absent'?' · Відсутня':''}</li>)}</ul></details>
    {preview.conflicts.length>0&&<p role="alert">Є резерви. Зніміть їх через відповідне замовлення.</p>}{preview.reservation_orders?.map((r:Row)=><p key={r.order_id+r.part_id}><Link to={'/orders/'+r.order_id}>Відкрити замовлення №{r.order_number}</Link></p>)}
    {!selected.consumed_operation_id&&!selected.consumed_type&&<>
     {editable&&assemblyEnabled&&<details><summary><Settings2 size={16}/>Керування складом вузла</summary><label><input type="checkbox" checked={physical} onChange={e=>setPhysical(e.target.checked)}/>Підтверджую фактичну наявність і склад</label>

     <div className="assembly-actions">
      <label>Компонент для включення<select value={child} onChange={e=>setChild(e.target.value)}><option value="">Оберіть фізичну позицію</option>{items.filter(n=>n.id!==selected.id&&!n.parent_id&&!n.consumed_operation_id).map(n=><option key={n.id} value={n.id}>{n.name}</option>)}</select></label>
      <button disabled={busy||!physical||!child} onClick={()=>void send('attach',{item_id:child,parent_id:selected.id,confirm_physical:true})}>Включити до вузла</button>
      {selected.parent_id?<button disabled={busy||!physical} onClick={()=>void send('detach',{item_id:selected.id,confirm_physical:true})}>Відокремити компонент</button>:<button disabled={busy||!physical||!!preview.issues?.length} onClick={()=>void send('confirm',{item_id:selected.id,token:preview.token,confirm_physical:true})}>Підтвердити поточний склад</button>}
     </div></details>}
     {selected.part_id&&!selected.parent_id&&can('sales.create')&&<details className="assembly-sale"><summary>Продаж за одним чеком</summary>
      <label>Фактична ціна<input type="number" min="0" step="0.01" value={price} onChange={e=>setPrice(e.target.value)}/></label>
      <label>Валюта<select value={currency} onChange={e=>setCurrency(e.target.value)}><option>UAH</option><option>USD</option></select></label>
      <label>Опис продажу<input maxLength={200} value={description} onChange={e=>setDescription(e.target.value)}/></label>
      <label><input type="checkbox" checked={remainder} onChange={e=>setRemainder(e.target.checked)}/>Продати решту вузла за вказаним описом</label>
      <label><input type="checkbox" checked={confirmSale} onChange={e=>setConfirmSale(e.target.checked)}/>Підтверджую передачу всього наведеного складу за одну ціну</label>
      <button disabled={busy||!confirmSale||price===''||Number(price)<0||preview.conflicts.length>0||(preview.incomplete&&!remainder)||!!preview.issues?.some((i:Row)=>i.reason==='absent'||i.reason==='archived')} onClick={()=>void send('sale',{type:'sale',quantity:1,sale_price:price,sale_currency:currency,assembly_token:preview.token,assembly_description:description,assembly_remainder:remainder},selected.part_id)}>{remainder?'Продати решту вузла':selected.completeness?'Продати вузол у зборі':'Продати деталь'}</button>
     </details>}
    </>}
    {editable&&assemblyEnabled&&selected.consumed_type==='sale'&&!selected.parent_id&&<>
     <p>Повертається майно за складом продажу. Гроші автоматично не повертаються.</p>
     <label><input type="checkbox" checked={confirmReturn} onChange={e=>setConfirmReturn(e.target.checked)}/>Підтверджую повне повернення фактичного складу без грошової операції</label>
     <button disabled={busy||!confirmReturn} onClick={()=>void send('return',{sale_operation_id:selected.consumed_operation_id,confirm_inventory_return_only:true})}>Повернути вузол на склад</button>
    </>}
   </>}
  </div>}
  </div>
  {editable&&assemblyEnabled&&!!data.unlinked_parts?.length&&<details className="assembly-legacy"><summary>Пов’язати наявну складську позицію</summary><p>Залишок не зміниться.</p><label>Наявна фізична позиція<select value={legacyPart} onChange={e=>setLegacyPart(e.target.value)}><option value="">Оберіть позицію</option>{data.unlinked_parts.map((p:Row)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button disabled={busy||!legacyPart} onClick={()=>void send('link_part',{part_id:legacyPart,confirm_physical:true})}>Пов’язати з деревом</button></details>}
 </section>;
}
