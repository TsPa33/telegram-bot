import {Modal} from './components';
import {OrderComposer} from './Orders';
import {Link} from 'react-router-dom';
import {useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {api,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';
import {Box,Check,ChevronDown,ChevronRight,Layers,Minus,Plus,Search,Settings2,TriangleAlert,X,MoreHorizontal,List,Network,DoorOpen,Cog,Zap,Armchair,Wind,ShieldCheck,Lightbulb,Disc,Settings} from 'lucide-react';
import {usePlanBulk,BulkStatus,BulkActionBar,GuidedReceipt,SelectionCheck} from './DismantlingBulk';
import {assemblyLabel,doorKey,doorOrder,isGenericDoor,isKnownDoorComponent,sameDoorInstallation,manuallyReviewableDoorComponent} from './assemblyPresentation';
import {assemblyUnitFor,assemblyReferenceLines} from './assemblyUnitCatalog';
import './assembly-tree.css';

/** Optional inline view over existing donor placements, never a stock generator. */
export default function AssemblyTree({vehicle,onReady,revision=0}:{vehicle:Row;onReady?:(enabled:boolean)=>void;revision?:number}) {
 const can=useCan(),who=useContext(TeamIdentity);
 const scope=JSON.stringify([who?.id,who?.workspace_account_id,vehicle.id]);
 const [assemblyEnabled,setAssemblyEnabled]=useState(false),[enabled,setEnabled]=useState(false),[data,setData]=useState<Row|null>(null),[open,setOpen]=useState<Set<string>>(new Set()),[q,setQ]=useState(''),[limit,setLimit]=useState(50);
 const [selected,setSelected]=useState<Row|null>(null),[preview,setPreview]=useState<Row|null>(null),[error,setError]=useState(''),[commandBusy,setBusy]=useState(false),[physical,setPhysical]=useState(false),[child,setChild]=useState(''),[legacyPart,setLegacyPart]=useState('');
 const [doorGroupOpen,setDoorGroupOpen]=useState(true),[manualComponents,setManualComponents]=useState(false),[assemblyToolsOpen,setAssemblyToolsOpen]=useState(false);
 const [splitSelected,setSplitSelected]=useState<number[]>([]),[splitConditions,setSplitConditions]=useState<Record<number,string>>({}),[splitConfirmed,setSplitConfirmed]=useState(false),[splitResult,setSplitResult]=useState<Row|null>(null);
 const splitPending=useRef<{fingerprint:string;key:string}|null>(null);
 const [price,setPrice]=useState(''),[currency,setCurrency]=useState('UAH'),[description,setDescription]=useState(''),[remainder,setRemainder]=useState(false),[confirmSale,setConfirmSale]=useState(false),[confirmReturn,setConfirmReturn]=useState(false);
 const [photo,setPhoto]=useState('');
 const [reference,setReference]=useState<string|null>(null);
 const [checkout,setCheckout]=useState<Row|null>(null);
 useEffect(()=>{let active=true;setPhoto('');if(selected?.part_id)api(`/parts/${selected.part_id}/photos`).then(rows=>{if(active)setPhoto(rows[0]?.url||'')}).catch(()=>{});return()=>{active=false}},[selected?.part_id]);
 const [subcategory,setSubcategory]=useState(''),[category,setCategory]=useState(''),[status,setStatus]=useState('all'),[mode,setMode]=useState('tree'),[note,setNote]=useState('');
 const inspectorRef=useRef<HTMLDivElement>(null);
 const [quantityDraft,setQuantityDraft]=useState<Record<string,number>>({});
 const selectedId=useRef<string|null>(null);
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
  if(ticket===epoch.current){setData(result);setBulkPlan(managed);const fresh=result.items.find((n:Row)=>n.id===selectedId.current);if(fresh){setSelected(fresh);if(fresh.part_id)api(`/vehicles/${vehicle.id}/assemblies/${fresh.id}/preview`).then(p=>{if(ticket===epoch.current&&selectedId.current===fresh.id)setPreview(p)}).catch(e=>setError(e.message));}setCheckedIds(ids=>ids.filter(id=>managed?.items.some((n:Row)=>n.id===id)));}return result;
 }
 useEffect(()=>{
  const ticket=++epoch.current;setData(null);setBulkPlan(null);setCheckedIds([]);setReceiptOpen(false);setEnabled(false);setCategory('');setStatus('all');setMode('tree');setSelected(null);selectedId.current=null;setPreview(null);setQuantityDraft({});setDoorGroupOpen(true);setManualComponents(false);setAssemblyToolsOpen(false);setError('');setOpen(new Set());setQ('');setLimit(50);pending.current=null;splitPending.current=null;setSplitSelected([]);setSplitConditions({});setSplitConfirmed(false);setSplitResult(null);writing.current=false;setBusy(false);
  api(`/vehicles/${vehicle.id}/assemblies/readiness`).then(async r=>{if(ticket!==epoch.current)return;setAssemblyEnabled(r.enabled);const ready=r.workspace_enabled??r.enabled;setEnabled(ready);onReady?.(ready&&can('inventory.view'));if(ready&&can('inventory.view'))await load(ticket)}).catch(e=>{if(ticket===epoch.current){setError(e.message)}});
  return()=>{epoch.current++};
 },[scope,revision]);
 async function select(node:Row) {
  const request=++previewEpoch.current;const ticket=epoch.current;selectedId.current=node.id;setSelected(node);setReference(null);if(assemblyUnitFor(node))setOpen(previous=>new Set([...previous,node.id]));setNote(node.note||'');setPreview(null);setPhysical(false);setConfirmSale(false);setConfirmReturn(false);setDescription('');setChild('');setManualComponents(false);setAssemblyToolsOpen(false);setSplitSelected([]);setSplitConditions({});setSplitConfirmed(false);setSplitResult(null);setError('');
  try{const value=await api(`/vehicles/${vehicle.id}/assemblies/${node.id}/preview`);if(ticket===epoch.current&&request===previewEpoch.current){
    setPreview(value);
    const root=value.items.find((i:Row)=>i.item_id===node.id);
    if(root){const completeness=value.incomplete&&(root.completeness!=null||value.items.length>1)?'incomplete':root.completeness;
     setSelected(old=>old?.id===node.id?{...old,completeness}:old);
     setData(old=>old?{...old,items:old.items.map((i:Row)=>i.id===node.id?{...i,completeness}:i)}:old);
    }
   }}catch(e){if(ticket===epoch.current)setError((e as Error).message)}
 }
 async function send(action:string,body:Row,part?:string):Promise<boolean> {
  if(writing.current||bulk.busy||bulk.intent)return false;writing.current=true;setBusy(true);setError('');const ticket=epoch.current;
  const fingerprint=JSON.stringify([scope,action,body,part]);
  if(pending.current?.fingerprint!==fingerprint)pending.current={fingerprint,key:crypto.randomUUID()};
  try{
   await api(part?`/parts/${part}/operations`:`/vehicles/${vehicle.id}/assemblies`,'POST',{...body,request_key:pending.current.key,...(!part?{action}: {})});
   if(ticket!==epoch.current)return false;
   pending.current=null;const fresh=await load(ticket);if(action==='inspect'){
    const node=fresh.items.find((n:Row)=>n.id===body.item_id);
    if(node&&selectedId.current===node.id){
      setSelected(node);
      try{const next=await api(`/vehicles/${vehicle.id}/assemblies/${node.id}/preview`);if(ticket===epoch.current&&selectedId.current===node.id)setPreview(next);}catch(e){setError((e as Error).message)}
    }
   }else{selectedId.current=null;setPreview(null);setSelected(null);}window.dispatchEvent(new Event('warehouse:inventory-changed'));return true;
  }catch(e){if(ticket===epoch.current)setError((e as Error).message);return false}finally{if(ticket===epoch.current){writing.current=false;setBusy(false)}}
 }
 if(!enabled||!can('inventory.view'))return error?<p role="alert">{error}</p>:null;
 if(!data)return <p role={error?'alert':'status'}>{error||'Завантажуємо фізичний склад…'}</p>;
 const items:Row[]=data.items||[],byId=new Map(items.map(n=>[n.id,n])),children=new Map<string,Row[]>(),planChildren=new Map<string,Row[]>();
 items.forEach(n=>{if(n.parent_id)children.set(n.parent_id,[...(children.get(n.parent_id)||[]),n]);else if(n.plan_parent_id&&byId.has(n.plan_parent_id))planChildren.set(n.plan_parent_id,[...(planChildren.get(n.plan_parent_id)||[]),n])});
 children.forEach(rows=>rows.sort((a,b)=>String(a.name).localeCompare(String(b.name),'uk',{numeric:true})));
 planChildren.forEach(rows=>rows.sort((a,b)=>String(a.name).localeCompare(String(b.name),'uk',{numeric:true})));
 const categories=[...new Set(items.map(n=>String(n.category||'Інші деталі')))];
 function icon(name:string){const Icon=/двер/i.test(name)?DoorOpen:/двиг|трансм/i.test(name)?Cog:/електр/i.test(name)?Zap:/салон|інтер/i.test(name)?Armchair:/клімат/i.test(name)?Wind:/безпек/i.test(name)?ShieldCheck:/освіт/i.test(name)?Lightbulb:/гальм/i.test(name)?Disc:/кермов|підвіск/i.test(name)?Settings:Box;return <Icon size={20} strokeWidth={1.6}/>;}
 const checked=items.filter(n=>['present','damaged'].includes(n.presence)).length,attention=items.filter(n=>['unchecked','damaged','absent'].includes(n.presence)||n.completeness==='incomplete'||n.category==='Потребує уточнення').length,stocked=items.filter(n=>n.part_id&&!n.parent_id&&!n.consumed_operation_id&&!n.archived&&n.quantity>0).length;
 // Never hide a recognized assembly's split workflow due to a permission or stock guard.
 // A visible, precise reason is preferable to silently removing the action.
 const splitBlockReason=!selected?''
  :!selected.part_id?'Спочатку оприбуткуйте вузол на склад.'
  :Number(selected.quantity)!==1?`Для розбору потрібен один фізичний вузол. Зараз у цій позиції: ${selected.quantity} шт. Спочатку звірте й виділіть конкретну фізичну одиницю без зміни загального залишку.`
  :selected.parent_id?'Цей компонент входить до іншого вузла. Спочатку відокремте його.'
  :selected.consumed_operation_id||selected.consumed_type?'Вузол уже продано або списано.'
  :selected.archived?'Вузол архівований. Спочатку відновіть його.'
  :selected.included===false?'Вузол виключено з плану розбору.'
  :selected.presence==='absent'?'Вузол позначено відсутнім.'
  :!assemblyEnabled?'Керування фізичним складом вимкнене для цього середовища.'
  :!editable||!can('inventory.create')?'Немає дозволів на розбір та оприбуткування. Зверніться до директора.'
  :preview?.conflicts?.length?'Вузол зарезервовано. Зніміть резерв у відповідному замовленні.'
  :!preview?(error?'Не вдалося перевірити склад. Оновіть перегляд вузла перед розбором.':'Перевіряємо склад вузла; до завершення перевірки розбір недоступний.')
  :'';
 function stockLabel(n:Row){return n.consumed_operation_id||n.consumed_type==='sale'||n.consumed_type==='write_off'?(n.consumed_type==='sale'?(n.parent_id?'Продано у складі вузла':'Продано'):'Списано'):n.parent_id?'У складі вузла':n.part_id&&n.quantity>0?'На складі':n.part_id?'Немає залишку':'Ще не на складі'}
 function presenceLabel(n:Row){return ({present:'Є в авто',damaged:'Пошкоджено',absent:'Немає'} as Record<string,string>)[n.presence]||'Перевірити'}
 async function inspect(n:Row,presence:string,quantity:number,noteValue:string){
  const ticket=epoch.current;try{const current=selected?.id===n.id&&preview?preview:await api(`/vehicles/${vehicle.id}/assemblies/${n.id}/preview`);if(ticket!==epoch.current)return;const root=current.items.find((i:Row)=>i.item_id===n.id);if(!root||root.quantity!==(n.part_id?n.quantity:null)||root.planned_quantity!==n.planned_quantity||root.note!==(n.note||''))throw Error('Дані змінилися. Оновіть список перед редагуванням.');return await send('inspect',{item_id:n.id,token:current.token,presence,quantity,note:noteValue});}catch(e){setError((e as Error).message);return false}
 }
 async function splitPhysicalUnit(root:Row) {
  const unit=assemblyUnitFor(root);
  if(!unit||!preview||!root.part_id||Number(root.quantity)!==1||!splitSelected.length||
     !splitConfirmed||busy||writing.current||!editable||!can('inventory.create')||splitBlockReason)return;
  const ticket=epoch.current,token=String(preview.token);
  const components=splitSelected.slice().sort((a,b)=>a-b).map(index=>({index,condition:splitConditions[index]||'used'}));
  const fingerprint=JSON.stringify([scope,'assembly:split',root.id,unit.id,token,components]);
  if(splitPending.current?.fingerprint!==fingerprint)
    splitPending.current={fingerprint,key:crypto.randomUUID()};
  writing.current=true;setBusy(true);setError('');
  try {
   const result=await api(`/vehicles/${vehicle.id}/assemblies/split`,'POST',{
     request_key:splitPending.current.key,root_item_id:root.id,unit_id:unit.id,
     token,components,confirm_physical:true
   });
   if(ticket!==epoch.current)return;
   splitPending.current=null;
   const fresh=await load(ticket);
   const updated=fresh.items.find((n:Row)=>n.id===root.id);
   if(updated&&selectedId.current===root.id){
    setSelected(updated);
    const next=await api(`/vehicles/${vehicle.id}/assemblies/${root.id}/preview`);
    if(ticket===epoch.current&&selectedId.current===root.id)setPreview(next);
   }
   setSplitResult(result);setSplitSelected([]);setSplitConfirmed(false);
   window.dispatchEvent(new Event('warehouse:inventory-changed'));
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}
  finally{if(ticket===epoch.current){writing.current=false;setBusy(false)}}
 }
 async function saveQuantity(n:Row){
  const next=quantityDraft[n.id];if(next==null||!Number.isInteger(next)||next<1)return;
  const ok=await inspect(n,n.presence,next,n.note);
  if(ok)setQuantityDraft(d=>{const copy={...d};delete copy[n.id];return copy});
 }
 async function receive(n:Row){const ticket=epoch.current;try{const current=selected?.id===n.id&&preview?preview:await api(`/vehicles/${vehicle.id}/assemblies/${n.id}/preview`);if(ticket!==epoch.current)return;const root=current.items.find((i:Row)=>i.item_id===n.id);if(!root||root.planned_quantity!==n.planned_quantity)throw Error('Кількість змінилася. Відкрийте деталь ще раз.');await send('receipt',{item_id:n.id,token:current.token,confirm_physical:true});}catch(e){setError((e as Error).message)}}
 const matches=items.filter(n=>(!subcategory||n.subcategory===subcategory)&&(!category||n.category===category)&&(!q.trim()||String(n.name).toLocaleLowerCase('uk').includes(q.trim().toLocaleLowerCase('uk')))&&(status==='all'||status==='confirmed'&&['present','damaged'].includes(n.presence)||status===n.presence||status==='stock'&&stockLabel(n)==='На складі'||status==='sold'&&n.consumed_type==='sale'));
 const managedById=new Map<string,Row>((bulkPlan?.items||[]).map((n:Row)=>[n.id,n]));
 const selectable=matches.filter(n=>managedById.has(n.id)).map(n=>String(n.id));
 const chosen=checkedIds.map(id=>managedById.get(id)).filter((n):n is Row=>!!n);
 const matching=new Set<string>();matches.forEach(n=>{let cursor:Row|undefined=n;while(cursor&&!matching.has(cursor.id)){matching.add(cursor.id);cursor=byId.get(cursor.parent_id||cursor.plan_parent_id)}});
 const roots=(mode==='list'?matches:items.filter(n=>!n.parent_id&&(!n.plan_parent_id||!byId.has(n.plan_parent_id))&&matching.has(n.id))).sort((a,b)=>Number(!!b.completeness)-Number(!!a.completeness)||String(a.name).localeCompare(String(b.name),'uk',{numeric:true}));
 const visibleRoots=roots.slice(0,limit);
 // This group is presentation-only. It has no Part ID or membership edge.
 const doorRoots=mode==='tree'?visibleRoots.filter(isGenericDoor).sort((a,b)=>doorOrder(a)-doorOrder(b)): [];
 const otherRoots=mode==='tree'&&doorRoots.length>1?visibleRoots.filter(n=>!isGenericDoor(n)):visibleRoots;
 const doorPositionCounts=new Map<string,number>();
 for(const node of items.filter(isGenericDoor)){const key=doorKey(node);if(key)doorPositionCounts.set(key,(doorPositionCounts.get(key)||0)+1)}
 const componentCandidates=selected&&isGenericDoor(selected)?
  items.filter(n=>n.id!==selected.id&&!n.parent_id&&!n.consumed_operation_id&&!n.archived&&isKnownDoorComponent(n)
   &&(sameDoorInstallation(selected,n)||manualComponents&&manuallyReviewableDoorComponent(selected,n))):
  items.filter(n=>n.id!==selected?.id&&!n.parent_id&&!n.consumed_operation_id);
 const preciseCandidates=selected&&isGenericDoor(selected)?
  items.filter(n=>n.id!==selected.id&&!n.parent_id&&!n.consumed_operation_id&&!n.archived&&isKnownDoorComponent(n)&&sameDoorInstallation(selected,n)).length:0;
 function render(node:Row):ReactNode {
  const kids=(children.get(node.id)||[]).filter(n=>matching.has(n.id)),expanded=open.has(node.id)||!!q||status!=='all';
  const savedAmount=node.parent_id?node.planned_quantity:node.part_id?node.quantity:node.planned_quantity;
  const amount=quantityDraft[node.id]??savedAmount;
  const quantityChanged=quantityDraft[node.id]!=null&&quantityDraft[node.id]!==savedAmount;
  const individual=!!node.parent_id||!!node.completeness||!!children.get(node.id)?.length||node.individually_tracked;
  const visibleName=assemblyLabel(node);
  const posKey=doorKey(node);
  const ambiguousDoor=!!posKey&&(doorPositionCounts.get(posKey)||0)>1;
  const unit=mode==='tree'?assemblyUnitFor(node):null;
  const planned=(planChildren.get(node.id)||[]).filter(n=>matching.has(n.id));
  const separated=planned.filter(n=>!!n.part_id);
  const waiting=planned.filter(n=>!n.part_id);
  const template=unit?assemblyReferenceLines(node,items,kids):[];
  const expandable=kids.length>0||planned.length>0||!!unit;
  const locked=busy||!editable||!!node.part_id||individual||!!node.consumed_type||!!node.consumed_operation_id||!!node.reserved||node.archived;
  return <li key={node.id}>
   <div className={`assembly-node ${selected?.id===node.id?'is-selected':''}`} onClick={e=>{if(!(e.target as HTMLElement).closest('button,input,a,select'))void select(node)}}>
    <span className="assembly-select-expand">{editable&&managedById.has(node.id)&&<SelectionCheck label={`Вибрати: ${node.name}`} ids={[node.id]} selected={new Set(checkedIds)} disabled={busy||receiptOpen} onToggle={value=>setCheckedIds(ids=>value?[...new Set([...ids,node.id])]:ids.filter(id=>id!==node.id))}/>}<button className="assembly-expand" aria-label={`${expanded?'Згорнути':'Розгорнути'} ${visibleName}`} aria-expanded={expandable?expanded:undefined} disabled={!expandable||mode==='list'} onClick={()=>setOpen(old=>{const next=new Set(old);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next})}>{expandable?(expanded?<ChevronDown size={16}/>:<ChevronRight size={16}/>):<span/>}</button></span>
    <button className="assembly-name" id={'assembly-node-'+node.id} aria-label={visibleName} onClick={()=>void select(node)}>{icon(node.name+' '+node.category)}<span><strong>{visibleName}</strong>{ambiguousDoor&&<small className="assembly-position-ambiguous">Збіг розташування — перевірити</small>}{node.completeness&&<small>{node.completeness==='complete'?'Комплектний вузол':node.completeness==='incomplete'?'Неповний комплект':'Перевірте склад вузла'}</small>}{node.position&&!isGenericDoor(node)&&<small>{node.position}</small>}{unit&&node.part_id&&<small>{Number(node.quantity)!==1?'Уточніть кількість фізичних вузлів':node.completeness==='complete'?'У зборі — склад підтверджено':'Вузол — уточніть комплектацію'}</small>}</span></button>
    <span className="assembly-row-category" title={node.category}>{node.category==='Потребує уточнення'?'Без категорії':node.category}</span>
    <button className={`assembly-status is-${node.presence}`} title={node.presence==='present'?'Наявність підтверджена':'Переглянути наявність та стан'} aria-label={`Статус: ${node.name}, ${presenceLabel(node)}`} onClick={()=>void select(node)}>{node.presence==='present'?<Check size={14}/>:node.presence==='damaged'?<TriangleAlert size={14}/>:node.presence==='absent'?<X size={14}/>:<Search size={14}/>} {presenceLabel(node)}</button>
    <div className="assembly-counter" role="group" aria-label={`Кількість: ${visibleName}`} title={individual?'Одна фізична позиція; дублювання кількості заборонене':node.part_id?'Залишок змінюється тільки у складі':'Кількість у плані; для запису натисніть зберегти'}><button aria-label={`Зменшити кількість: ${visibleName}`} disabled={locked||amount<=1} onClick={()=>setQuantityDraft(d=>({...d,[node.id]:amount-1}))}><Minus size={14}/></button><output>{amount}</output><button aria-label={`Збільшити кількість: ${visibleName}`} disabled={locked} onClick={()=>setQuantityDraft(d=>({...d,[node.id]:amount+1}))}><Plus size={14}/></button><button className="assembly-counter-save" aria-label={`Зберегти кількість: ${visibleName}`} title="Зберегти зміну кількості" disabled={locked||!quantityChanged} onClick={()=>void saveQuantity(node)}><Check size={14}/></button></div>
    {!node.part_id&&!node.parent_id&&!node.consumed_operation_id&&editable&&can('inventory.create')&&['present','damaged'].includes(node.presence)?<button className="assembly-receipt" disabled={busy} onClick={()=>void receive(node)}><Box size={14}/>Додати на склад</button>:<span className="assembly-row-stock">{stockLabel(node)}</span>}
    {!node.part_id&&!['present','damaged'].includes(node.presence)&&!node.parent_id&&<button className="assembly-row-action" onClick={()=>void select(node)}>Підтвердити</button>}
    {node.part_id&&<button className="assembly-row-action" onClick={()=>void select(node)}>Переглянути</button>}
    <button className="assembly-more" aria-label={`Дії: ${node.name}`} onClick={()=>void select(node)}><MoreHorizontal size={18}/></button>
   </div>{expanded&&mode==='tree'&&expandable&&<ul className="assembly-children">
     {kids.length>0&&<li className="assembly-connected-heading"><Check size={13}/>Фізично приєднані · {kids.length}</li>}
     {kids.map(render)}
     {separated.length>0&&<li className="assembly-door-component-wrapper"><details className="assembly-plan-items" open>
       <summary>Відокремлені складські позиції · {separated.length}</summary>
       <ul className="assembly-children">{separated.map(render)}</ul>
      </details></li>}
     {waiting.length>0&&<li className="assembly-door-component-wrapper"><details className="assembly-plan-items">
       <summary>Окремі записи плану · {waiting.length}</summary>
       <ul className="assembly-children">{waiting.map(render)}</ul>
      </details></li>}
     {unit&&<li className="assembly-door-component-wrapper">
       <details className="assembly-door-component-preview">
        <summary className="assembly-component-preview-heading"><strong>{unit.title}</strong><span>Довідковий склад · {template.length} типів</span></summary>
        <div className="assembly-component-preview-body">
         <p className="assembly-assembly-explanation">{node.part_id?(Number(node.quantity)===1?'Вузол обліковується як одна складська одиниця.':'Складський запис містить більше ніж один вузол; перед підтвердженням комплектності уточніть фізичні одиниці.'):'Це потенційний вузол у плані, не складський залишок.'} Складові наведені для перевірки, окремо додавати їх не потрібно.</p>
         <ul className="assembly-door-template-list">{template.filter(entry=>entry.kind!=='attached').map(entry=><li key={entry.key} className={'assembly-door-candidate '+(entry.kind==='existing_plan'?'has-source':'template-only')}>
           <Box size={15}/><button type="button" className="assembly-template-label" onClick={()=>{void select(node);setReference(entry.label);requestAnimationFrame(()=>inspectorRef.current?.focus());}}>{entry.label}</button>
           <small>{entry.kind==='existing_plan'?(entry.linkedId&&byId.get(entry.linkedId)?.part_id?'Відокремлена позиція':'Окремо у плані'):'Можлива складова'}</small>
          </li>)}</ul>
         <p className="assembly-component-hint">Конструктивна довідка не підтверджує комплектацію за VIN і не створює позицій, кількості чи можливості окремого продажу. Для продажу всього вузла підтвердьте його фактичну комплектність.</p>
        </div>
       </details>
      </li>}
    </ul>}
  </li>;
 }
 return <section className="assembly-tree" aria-label="Фізичний склад вузлів" style={{paddingBottom:toolbarHeight?toolbarHeight+16:undefined}}>
  {checkout&&<OrderComposer accountId={String(who?.workspace_account_id||who?.id||'')} initialPart={checkout} onClose={()=>setCheckout(null)} onCreated={()=>{setCheckout(null);void load();void select(selected!);window.dispatchEvent(new Event('warehouse:inventory-changed'));}}/>}
  <div className="assembly-plan-ready"><h2>Розбір автомобіля</h2><span>{items.length?'План сформовано':'Сформуйте список деталей'}</span></div>
  <header className="assembly-overview"><div className="assembly-metrics" role="region" aria-label="Показники розбору">{[['У плані',items.length],['Підтверджено',checked],['На складі',stocked],['Потребує уваги',attention]].map(([label,value])=><div key={label}><span>{label==='На складі'?<Box size={22}/>:label==='Потребує уваги'?<TriangleAlert size={22}/>:<Check size={22}/>}</span><div><small>{label}</small><strong>{value}</strong></div></div>)}</div><div className="assembly-top-actions">{checkedIds.length>0&&<button className="primary" disabled={busy||!editable||!can('inventory.create')} onClick={()=>setReceiptOpen(true)}><Box size={18}/>Додати вибрані на склад</button>}<details><summary><Settings2 size={16}/>Швидкі дії</summary><button disabled={busy} onClick={()=>void load().catch(e=>setError(e.message))}>Оновити список</button><button onClick={()=>{setQ('');setCategory('');setStatus('unchecked')}}>Знайти непідтверджені</button><button onClick={()=>{setQ('');setCategory('');setStatus('damaged')}}>Переглянути пошкодження</button></details></div></header>
  {error&&<p role="alert">{error}</p>}
  <BulkStatus bulk={bulk}/>
  {receiptOpen&&<Modal className="dv2-receipt-dialog" title="Підтвердження надходження" onClose={()=>{if(!busy)setReceiptOpen(false)}}><GuidedReceipt path={planPath} ids={checkedIds} bulk={bulk} onBack={()=>setReceiptOpen(false)}/></Modal>}
  {editable&&bulkPlan&&<div className="assembly-selection" role="group" aria-label="Вибір деталей для масових дій"><label><SelectionCheck ids={selectable} selected={new Set(checkedIds)} disabled={busy||receiptOpen} label="Вибрати всі за поточними фільтрами" onToggle={value=>setCheckedIds(ids=>value?[...new Set([...ids,...selectable])]:ids.filter(id=>!selectable.includes(id)))}/>Вибрати всі за поточними фільтрами ({selectable.length})</label><button disabled={busy||receiptOpen||!checkedIds.length} onClick={()=>setCheckedIds([])}>Зняти вибір ({checkedIds.length})</button></div>}
  {editable&&chosen.length>0&&!receiptOpen&&<BulkActionBar items={chosen} disabled={busy} onAction={(action,reason)=>void bulk.start(action,checkedIds,bulkPlan!.etag,reason)} onReceipt={()=>{bulk.resetFeedback();setReceiptOpen(true);}} onClear={()=>setCheckedIds([])} onHeight={setToolbarHeight}/>}
  <div className="assembly-workspace has-inspector">
   <nav className="assembly-categories" aria-label="Категорії запчастин"><h3>Категорії запчастин</h3><button aria-pressed={!category} onClick={()=>{setCategory('');setSubcategory('');setLimit(50)}}><Layers size={20}/><span>Усі категорії</span><b>{items.length}</b></button>{categories.map(c=><details key={c} open={category===c}><summary><button aria-pressed={category===c&&!subcategory} onClick={()=>{setCategory(c);setSubcategory('');setLimit(50)}}>{icon(c)}<span>{c==='Потребує уточнення'?'Без категорії':c}</span><b>{items.filter(n=>(n.category||'Інші деталі')===c).length}</b></button></summary>{[...new Set(items.filter(n=>(n.category||'Інші деталі')===c).map(n=>String(n.subcategory||'Без підкатегорії')))].map(sub=><button className="dv2-subcategory" key={sub} aria-pressed={category===c&&subcategory===sub} onClick={()=>{setCategory(c);setSubcategory(sub);setLimit(50)}}><span>{sub}</span><b>{items.filter(n=>n.category===c&&(n.subcategory||'Без підкатегорії')===sub).length}</b></button>)}</details>)}</nav>
   <div className="assembly-center"><div className="assembly-toolbar"><label><Search size={18}/><input aria-label="Пошук у дереві" placeholder="Пошук запчастини…" value={q} onChange={e=>{setQ(e.target.value);setLimit(50)}}/></label><select aria-label="Статус деталей" value={status} onChange={e=>{setStatus(e.target.value);setLimit(50)}}>{[['all','Усі статуси'],['unchecked','Перевірити наявність'],['present','Є в автомобілі'],['confirmed','Наявність підтверджено'],['damaged','Пошкоджена'],['absent','Відсутня'],['stock','На складі'],['sold','Продано']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select><div className="assembly-view"><button aria-pressed={mode==='tree'} onClick={()=>setMode('tree')}><Network size={16}/>Дерево</button><button aria-pressed={mode==='list'} onClick={()=>setMode('list')}><List size={16}/>Список</button></div></div>
    <div className="assembly-filter-tabs" role="group" aria-label="Швидкі фільтри">{[['all','Усі'],['unchecked','Потрібно підтвердити'],['confirmed','Підтверджено'],['stock','На складі']].map(([value,label])=><button key={value} aria-pressed={status===value} onClick={()=>{setStatus(value);setLimit(50)}}>{label}</button>)}</div>
    <div className="assembly-column-head" aria-hidden="true"><span>Запчастина</span><span>Категорія</span><span>Кількість</span><span>Статус</span><span>Дія</span></div>
    {!matches.length&&<p className="assembly-empty">Деталей за цими умовами немає.</p>}<ul className="assembly-roots">
     {doorRoots.length>1&&<li className="assembly-virtual-group">
       <button type="button" className="assembly-virtual-group-toggle" aria-expanded={doorGroupOpen} onClick={()=>setDoorGroupOpen(v=>!v)}>{doorGroupOpen?<ChevronDown size={18}/>:<ChevronRight size={18}/>}<DoorOpen size={18}/><span>Двері</span><small>Різні фізичні позиції</small><b>{doorRoots.length}</b></button>
       {doorGroupOpen&&<ul>{doorRoots.map(render)}</ul>}
      </li>}
     {otherRoots.map(render)}
    </ul>
    {roots.length>limit&&<button onClick={()=>setLimit(n=>n+50)}>Показати ще 50 позицій</button>}
   </div>
  {selected?<div ref={inspectorRef} tabIndex={-1} role="region" className="assembly-inspector" aria-label="Картка запчастини"><div className="assembly-heading"><h4>{assemblyLabel(selected)}</h4><button type="button" className="assembly-inspector-close" aria-label="Закрити картку" title="Закрити картку" onClick={()=>{previewEpoch.current++;document.getElementById('assembly-node-'+selected.id)?.focus();selectedId.current=null;setSelected(null);setPreview(null)}}><X size={17}/></button></div>
    {reference&&<section className="notice" aria-label="Довідкова складова"><strong>{reference}</strong><p>Можлива складова, не окремий товар. Перевірте фактичну наявність і стан. Для відокремлення позначте цю деталь нижче та підтвердьте демонтаж.</p></section>}
    {!!assemblyUnitFor(selected)&&
      <details className="assembly-physical-split" open={reference?true:undefined}>
       <summary><Layers size={16}/><span>Розібрати вузол на окремі запчастини</span>{splitBlockReason&&<small className="assembly-split-locked-label">Недоступно</small>}</summary>
       {splitBlockReason?<><p role="status" className="assembly-split-unavailable">{splitBlockReason}</p>{selected.part_id&&Number(selected.quantity)>1&&<div className="assembly-split-unit-steps"><ol><li>Звірте кількість і резерви партії та позначте конкретний фізичний вузол, який плануєте розібрати.</li><li>Потрібна контрольована операція виділення однієї одиниці: 1 окремо, решта {Number(selected.quantity)-1} у партії; загальний залишок {selected.quantity} і резерви мають зберегтися.</li><li>Після звірки відкрийте запис саме цієї одиниці з кількістю 1 та підтвердьте відокремлені компоненти.</li></ol><p>Цей екран не виконує виділення одиниці з партії. Не зменшуйте кількість вручну й не створюйте дублікати надходжень.</p><Link to={'/inventory?vehicle_id='+vehicle.id}>Переглянути партію на складі</Link></div>}</>:<>
       <p className="notice">Собівартість не розподіляється автоматично. Перед звітом прибутку відповідальний має звірити вартість залишку вузла й відокремлених деталей. Не враховуйте невизначену собівартість як нуль.</p>
       <p>Позначте лише деталі, які <strong>вже фізично відокремили</strong>. Після підтвердження вони стануть окремими складськими позиціями для продажу. Вузол залишиться неповним.</p>
       {assemblyReferenceLines(selected,items,children.get(selected.id)||[]).map((entry,index)=>{
        const actual=entry.linkedId?byId.get(entry.linkedId):null;
        const alreadySeparated=entry.kind==='existing_plan'&&!!actual?.part_id;
        const checked=splitSelected.includes(index);
        return <div className="assembly-split-row" key={entry.key}>
         <label><input type="checkbox" checked={checked} disabled={busy||alreadySeparated||!!preview?.conflicts?.length||!!splitBlockReason}
           onChange={event=>{const on=event.target.checked;setSplitSelected(old=>on?[...old,index]:old.filter(i=>i!==index));setSplitConfirmed(false);setSplitResult(null)}}/>
          <span>{entry.label}{reference===entry.label&&<small> · Вибрано для перевірки</small>}</span></label>
         {alreadySeparated?<small>Вже окремо на складі</small>:entry.kind==='attached'?<small>У вузлі</small>:<small>Можлива складова</small>}
         {checked&&<select value={splitConditions[index]||'used'} disabled={busy} aria-label={'Стан: '+entry.label}
          onChange={event=>{setSplitConditions(old=>({...old,[index]:event.target.value}));setSplitConfirmed(false)}}>
           <option value="used">Вживана</option><option value="damaged">Пошкоджена</option>
           <option value="new">Нова</option><option value="refurbished">Відновлена</option>
          </select>}
        </div>;
       })}
       <p className="assembly-split-note">Складські залишки з'являться лише для підтверджених відокремлених деталей. Кількість вихідного вузла залишиться 1 — це залишок без вилучених компонентів. Його продаж «у зборі» буде заблоковано, поки склад фізично не відновлено.</p>
       <label className="assembly-split-confirm"><input type="checkbox" checked={splitConfirmed} disabled={busy||!splitSelected.length}
         onChange={e=>setSplitConfirmed(e.target.checked)}/> Підтверджую демонтаж {splitSelected.length} деталей і зміну комплектності вузла</label>
       <button type="button" className="primary" disabled={busy||!splitConfirmed||!splitSelected.length||!!preview?.conflicts?.length||!!splitBlockReason}
         onClick={()=>void splitPhysicalUnit(selected)}><Box size={16}/>Відокремити та оприбуткувати {splitSelected.length}</button>
       {splitResult&&<div className="assembly-split-success" role="status">
         <strong>Оприбутковано {splitResult.count} компонентів</strong>
         <p>Вузол тепер неповний. Собівартість автоматично не розподілялася.</p>
         <Link to={'/inventory?vehicle_id='+vehicle.id}>Відкрити склад і оформити продаж</Link>
        </div>}
       </>}
      </details>}

   {!preview?<p role="status">{error?'Не вдалося перевірити склад.':'Перевіряємо склад…'}</p>:<>

    <p className="assembly-breadcrumb">{selected.category} › {selected.subcategory}{selected.position?` · ${selected.position}`:''} </p>
    <div className="assembly-photo">{photo?<img src={photo} alt={selected.name} onError={()=>setPhoto('')}/>:<><Box size={44}/><span>Фото ще немає</span></>}</div>
    {assemblyUnitFor(selected)&&selected.part_id&&Number(selected.quantity)!==1&&<p className="assembly-unit-warning" role="status">Кількість цього складського запису відрізняється від однієї фізичної одиниці. Продаж як підтвердженого комплектного вузла потребує уточнення.</p>}
    <h5>Наявність на автомобілі</h5>
    <div className="assembly-presence" role="group" aria-label="Наявність на автомобілі">{(['present','damaged','absent'] as const).map(value=><button key={value} aria-label={{present:'Підтвердити наявність',damaged:'Позначити пошкодження',absent:'Позначити відсутність'}[value]} aria-pressed={selected.presence===value} disabled={busy||!editable||!!selected.consumed_type||!!selected.consumed_operation_id||!!selected.archived||preview.conflicts.length>0} onClick={()=>void inspect(selected,value,selected.part_id?selected.quantity:selected.planned_quantity,note)}>{value==='present'?<Check size={16}/>:value==='damaged'?<TriangleAlert size={16}/>:<X size={16}/>}{{present:'Є',damaged:'Пошкоджено',absent:'Відсутня'}[value]}</button>)}</div>
    <p className="assembly-stock-label">{stockLabel(selected)} · Кількість: {selected.parent_id?selected.planned_quantity:selected.part_id?selected.quantity:selected.planned_quantity}</p>
    <label>Примітка<textarea maxLength={2000} value={note} disabled={!editable||busy||!!selected.consumed_type||!!selected.consumed_operation_id} onChange={e=>setNote(e.target.value)} placeholder="Стан, особливості, пошкодження…"/></label>
    <button className="secondary" disabled={busy||!editable||!!selected.consumed_type||!!selected.consumed_operation_id||note===(selected.note||'')} onClick={()=>void inspect(selected,selected.presence,selected.part_id?selected.quantity:selected.planned_quantity,note)}>Зберегти примітку</button>
    {editable&&!selected.part_id&&!selected.parent_id&&!selected.consumed_operation_id&&can('inventory.create')&&<button className="primary" disabled={busy||!['present','damaged'].includes(selected.presence)} onClick={()=>void receive(selected)}><Box size={18}/>Додати на склад</button>}
    {selected.part_id&&<Link className="assembly-part-link" to={'/inventory?vehicle_id='+vehicle.id}>Перейти до складу автомобіля</Link>}
    {editable&&assemblyEnabled&&!!assemblyUnitFor(selected)&&selected.part_id&&Number(selected.quantity)===1&&!selected.parent_id&&!selected.consumed_operation_id&&!selected.consumed_type&&<button type="button" className="secondary assembly-manage-shortcut" onClick={()=>setAssemblyToolsOpen(open=>!open)}>
      <Layers size={17}/>{preview.memberships?.length?'Керувати складом вузла':'Підтвердити вузол у зборі'}
    </button>}
    {!!preview.issues?.length&&<p role="alert">Комплектність потребує перевірки: {preview.issues.map((i:Row)=>`${i.name} — ${{absent:'відсутня',damaged:'пошкоджена',archived:'архівована'}[i.reason as 'absent'|'damaged'|'archived']}`).join('; ')}</p>}
    <details className="assembly-composition" open={!!selected.completeness}><summary>Фактичний склад</summary><ul>{preview.items.map((n:Row)=><li key={n.item_id}>{n.name}{n.condition==='damaged'?' · Пошкоджено':''}{n.presence==='absent'?' · Відсутня':''}</li>)}</ul></details>
    {preview.conflicts.length>0&&<p role="alert">Є резерви. Зніміть їх через відповідне замовлення.</p>}{preview.reservation_orders?.map((r:Row)=><p key={r.order_id+r.part_id}><Link to={'/orders/'+r.order_id}>Відкрити замовлення №{r.order_number}</Link></p>)}
    {!selected.consumed_operation_id&&!selected.consumed_type&&<>
     {editable&&assemblyEnabled&&<details className="assembly-management" open={assemblyToolsOpen} onToggle={e=>setAssemblyToolsOpen(e.currentTarget.open)}><summary><Settings2 size={16}/>Керування фізичним складом</summary><label><input type="checkbox" checked={physical} onChange={e=>setPhysical(e.target.checked)}/>Підтверджую фактичну наявність і склад</label>

     <div className="assembly-actions">
      {isGenericDoor(selected)&&<div className="assembly-door-guidance" role="status">
       <strong>Склад дверей</strong>
       <p>Реальні компоненти можна включити лише після перевірки їхнього розташування та фізичного складу. Пропозиції не створюють залишків.</p>
       <p>Зіставлено за точною позицією: {preciseCandidates}. {preciseCandidates===0?'За наявними даними підтверджених компонентів не знайдено.':''}</p>
       <button type="button" className="secondary" onClick={()=>{setManualComponents(v=>!v);setChild('');}}>{manualComponents?'Приховати незвірені':'Показати компоненти для ручної перевірки'}</button>
      </div>}
      <label>Компонент для включення<select value={child} onChange={e=>setChild(e.target.value)}><option value="">Оберіть фізичну позицію</option>{componentCandidates.map(n=><option key={n.id} value={n.id}>{assemblyLabel(n)}{n.position?` · ${n.position}`:''}</option>)}</select></label>
      <button disabled={busy||!physical||!child} onClick={()=>void send('attach',{item_id:child,parent_id:selected.id,confirm_physical:true})}>Включити до вузла</button>
      {selected.parent_id?<button disabled={busy||!physical} onClick={()=>void send('detach',{item_id:selected.id,confirm_physical:true})}>Відокремити компонент</button>:<button disabled={busy||!physical||!!preview.issues?.length} onClick={()=>void send('confirm',{item_id:selected.id,token:preview.token,confirm_physical:true})}>Підтвердити комплектність вузла</button>}
     </div></details>}
     {selected.part_id&&!selected.parent_id&&can('orders.create')&&<details className="assembly-sale"><summary>Оформити замовлення</summary>
      <label>Фактична ціна<input type="number" min="0" step="0.01" value={price} onChange={e=>setPrice(e.target.value)}/></label>
      <label>Валюта<select value={currency} onChange={e=>setCurrency(e.target.value)}><option>UAH</option><option>USD</option></select></label>
      <label>Опис продажу<input maxLength={200} value={description} onChange={e=>setDescription(e.target.value)}/></label>
      <label><input type="checkbox" checked={remainder} onChange={e=>setRemainder(e.target.checked)}/>Продати решту вузла за вказаним описом</label>
      <label><input type="checkbox" checked={confirmSale} onChange={e=>setConfirmSale(e.target.checked)}/>Підтверджую передачу всього наведеного складу за одну ціну</label>
      <button disabled={busy||!confirmSale||price===''||Number(price)<0||preview.conflicts.length>0||(preview.incomplete&&!remainder)||!!preview.issues?.some((i:Row)=>i.reason==='absent'||i.reason==='archived')} onClick={()=>setCheckout({id:selected.part_id,name:selected.name,quantity:1,unit_price:price,currency,assembly_token:preview.token,assembly_description:description,assembly_remainder:remainder,donor_snapshot:vehicle})}>Оформити замовлення</button>
     </details>}
    </>}
    {editable&&assemblyEnabled&&selected.consumed_type==='sale'&&!selected.parent_id&&<>
     <p>Повертається майно за складом продажу. Гроші автоматично не повертаються.</p>
     <label><input type="checkbox" checked={confirmReturn} onChange={e=>setConfirmReturn(e.target.checked)}/>Підтверджую повне повернення фактичного складу без грошової операції</label>
     <button disabled={busy||!confirmReturn} onClick={()=>void send('return',{sale_operation_id:selected.consumed_operation_id,confirm_inventory_return_only:true})}>Повернути вузол на склад</button>
    </>}
   </>}
  </div>:<aside className="assembly-inspector assembly-inspector-empty" aria-label="Картка запчастини" role="region"><Box size={32}/><strong>Картка запчастини</strong><p>Оберіть деталь у списку, щоб переглянути стан, кількість і складські дії.</p></aside>}
  </div>
  {editable&&assemblyEnabled&&!!data.unlinked_parts?.length&&<details className="assembly-legacy"><summary>Пов’язати наявну складську позицію</summary><p>Залишок не зміниться.</p><label>Наявна фізична позиція<select value={legacyPart} onChange={e=>setLegacyPart(e.target.value)}><option value="">Оберіть позицію</option>{data.unlinked_parts.map((p:Row)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button disabled={busy||!legacyPart} onClick={()=>void send('link_part',{part_id:legacyPart,confirm_physical:true})}>Пов’язати з деревом</button></details>}
 </section>;
}
