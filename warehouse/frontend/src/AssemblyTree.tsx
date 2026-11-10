import {Link} from 'react-router-dom';
import {useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {api,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';
import './assembly-tree.css';

/** Optional inline view over existing donor placements, never a stock generator. */
export default function AssemblyTree({vehicle}:{vehicle:Row}) {
 const can=useCan(),who=useContext(TeamIdentity);
 const scope=JSON.stringify([who?.id,who?.workspace_account_id,vehicle.id]);
 const [enabled,setEnabled]=useState(false),[data,setData]=useState<Row|null>(null),[open,setOpen]=useState<Set<string>>(new Set()),[q,setQ]=useState(''),[limit,setLimit]=useState(50);
 const [selected,setSelected]=useState<Row|null>(null),[preview,setPreview]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[physical,setPhysical]=useState(false),[child,setChild]=useState(''),[legacyPart,setLegacyPart]=useState('');
 const [price,setPrice]=useState(''),[currency,setCurrency]=useState('UAH'),[description,setDescription]=useState(''),[remainder,setRemainder]=useState(false),[confirmSale,setConfirmSale]=useState(false),[confirmReturn,setConfirmReturn]=useState(false);
 const previewEpoch=useRef(0);
 const epoch=useRef(0),pending=useRef<{fingerprint:string;key:string}|null>(null),writing=useRef(false);
 const editable=can('dismantling.manage')&&can('inventory.edit')&&can('inventory.adjust_quantity');
 async function load(ticket=epoch.current) {
  const result=await api(`/vehicles/${vehicle.id}/assemblies`);
  if(ticket===epoch.current)setData(result);
 }
 useEffect(()=>{
  const ticket=++epoch.current;setData(null);setEnabled(false);setSelected(null);setPreview(null);setError('');setOpen(new Set());setQ('');setLimit(50);pending.current=null;writing.current=false;setBusy(false);
  api(`/vehicles/${vehicle.id}/assemblies/readiness`).then(async r=>{if(ticket!==epoch.current)return;setEnabled(r.enabled);if(r.enabled&&can('inventory.view'))await load(ticket)}).catch(e=>{if(ticket===epoch.current)setError(e.message)});
  return()=>{epoch.current++};
 },[scope]);
 async function select(node:Row) {
  const request=++previewEpoch.current;const ticket=epoch.current;setSelected(node);setPreview(null);setPhysical(false);setConfirmSale(false);setConfirmReturn(false);setDescription('');setChild('');setError('');
  try{const value=await api(`/vehicles/${vehicle.id}/assemblies/${node.id}/preview`);if(ticket===epoch.current&&request===previewEpoch.current)setPreview(value)}catch(e){if(ticket===epoch.current)setError((e as Error).message)}
 }
 async function send(action:string,body:Row,part?:string) {
  if(writing.current)return;writing.current=true;setBusy(true);setError('');const ticket=epoch.current;
  const fingerprint=JSON.stringify([scope,action,body,part]);
  if(pending.current?.fingerprint!==fingerprint)pending.current={fingerprint,key:crypto.randomUUID()};
  try{
   await api(part?`/parts/${part}/operations`:`/vehicles/${vehicle.id}/assemblies`,'POST',{...body,request_key:pending.current.key,...(!part?{action}: {})});
   if(ticket!==epoch.current)return;
   pending.current=null;setPreview(null);setSelected(null);await load(ticket);window.dispatchEvent(new Event('warehouse:inventory-changed'));
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}finally{if(ticket===epoch.current){writing.current=false;setBusy(false)}}
 }
 if(!enabled||!can('inventory.view'))return null;
 if(!data)return <p role={error?'alert':'status'}>{error||'Завантажуємо фізичний склад…'}</p>;
 const items:Row[]=data?.items||[],byId=new Map(items.map(n=>[n.id,n])),children=new Map<string,Row[]>();
 items.forEach(n=>{if(n.parent_id)children.set(n.parent_id,[...(children.get(n.parent_id)||[]),n])});
 const matching=new Set<string>();
 if(q.trim())items.filter(n=>String(n.name).toLocaleLowerCase('uk').includes(q.toLocaleLowerCase('uk'))).forEach(n=>{let cursor:Row|undefined=n;while(cursor&&!matching.has(cursor.id)){matching.add(cursor.id);cursor=byId.get(cursor.parent_id)}});
 const roots=items.filter(n=>!n.parent_id&&(!q||matching.has(n.id))).sort((a,b)=>Number(!!b.completeness)-Number(!!a.completeness)||String(a.name).localeCompare(String(b.name),'uk',{numeric:true}));
 function render(node:Row):ReactNode {
  const kids=(children.get(node.id)||[]).filter(n=>!q||matching.has(n.id)),expanded=open.has(node.id)||!!q;
  return <li key={node.id}>
   <div className="assembly-node"><button className="text-button" aria-label={`${expanded?'Згорнути':'Розгорнути'} ${node.name}`} aria-expanded={kids.length?expanded:undefined} disabled={!kids.length} onClick={()=>setOpen(old=>{const next=new Set(old);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next})}>{kids.length?(expanded?'−':'+'):'·'}</button>
    <button className="text-button" onClick={()=>void select(node)}>{node.name}</button>
    <span>{node.consumed_operation_id?(node.consumed_type==='sale'?(node.parent_id?'Продано у складі вузла':'Вузол продано'):'Передано у складі списання'):node.parent_id?'У складі вузла':node.standalone?'Доступна самостійно':'Потенційна позиція'}</span>
    {node.completeness&&<span>{node.completeness==='complete'?'Склад підтверджено':node.completeness==='incomplete'?'Неповний комплект':'Склад не перевірено'}</span>}
    {kids.length>0&&<small>{kids.length} компонентів</small>}
   </div>{expanded&&kids.length>0&&<ul>{kids.map(render)}</ul>}
  </li>;
 }
 return <section className="assembly-tree" aria-label="Фізичний склад вузлів"><h3>Вузли та компоненти</h3>
  <p>Потенційні: {data?.counts.potential??0} · Підтверджено у вузлах: {data?.counts.confirmed_attached??0} · Доступні самостійно: {data?.counts.standalone??0} · Передано у вузлах: {data?.counts.included_in_sale??0}</p>
  {editable&&!!data.unlinked_parts?.length&&<details><summary>Пов’язати наявну складську позицію</summary><p>Створюється лише зв’язок із деревом, без нового залишку.</p><label>Наявна фізична позиція<select aria-label="Наявна фізична позиція" value={legacyPart} onChange={e=>setLegacyPart(e.target.value)}><option value="">Оберіть позицію</option>{data.unlinked_parts.map((p:Row)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button disabled={busy||!legacyPart} onClick={()=>void send('link_part',{part_id:legacyPart,confirm_physical:true})}>Пов’язати з деревом</button></details>}
  <label>Пошук у дереві<input value={q} onChange={e=>{setQ(e.target.value);setLimit(50)}}/></label>
  {error&&<p role="alert">{error}</p>}
  {selected&&<div className="assembly-inspector"><div className="assembly-heading"><h4>{selected.name}</h4><button onClick={()=>{previewEpoch.current++;setSelected(null);setPreview(null)}}>Закрити склад вузла</button></div>
   {!preview?<p role="status">{error?'Не вдалося перевірити склад.':'Перевіряємо склад…'}</p>:<>
    <h5>Фактичний склад</h5><ul>{preview.items.map((n:Row)=><li key={n.item_id}>{n.name}{n.condition==='damaged'?' · Пошкоджено':''}{n.presence==='absent'?' · Відсутня':''}</li>)}</ul>
    {preview.conflicts.length>0&&<p role="alert">Є резерви. Зніміть їх через відповідне замовлення.</p>}{preview.reservation_orders?.map((r:Row)=><p key={r.order_id+r.part_id}><Link to={'/orders/'+r.order_id}>Відкрити замовлення №{r.order_number}</Link></p>)}
    {!selected.consumed_operation_id&&<>
     {editable&&<><label><input type="checkbox" checked={physical} onChange={e=>setPhysical(e.target.checked)}/>Підтверджую фактичну наявність і склад</label>
     {!selected.part_id&&!selected.parent_id&&can('inventory.create')&&<button disabled={busy||!physical} onClick={()=>void send('receipt',{item_id:selected.id,confirm_physical:true})}>Підтвердити 1 фізичний вузол</button>}
     <div className="assembly-actions">
      <label>Компонент для включення<select value={child} onChange={e=>setChild(e.target.value)}><option value="">Оберіть фізичну позицію</option>{items.filter(n=>n.id!==selected.id&&!n.parent_id&&!n.consumed_operation_id).map(n=><option key={n.id} value={n.id}>{n.name}</option>)}</select></label>
      <button disabled={busy||!physical||!child} onClick={()=>void send('attach',{item_id:child,parent_id:selected.id,confirm_physical:true})}>Включити до вузла</button>
      {selected.parent_id?<button disabled={busy||!physical} onClick={()=>void send('detach',{item_id:selected.id,confirm_physical:true})}>Відокремити компонент</button>:<button disabled={busy||!physical} onClick={()=>void send('confirm',{item_id:selected.id,token:preview.token,confirm_physical:true})}>Підтвердити поточний склад</button>}
     </div></>}
     {selected.part_id&&!selected.parent_id&&can('sales.create')&&<div className="assembly-sale">
      <label>Фактична ціна<input type="number" min="0" step="0.01" value={price} onChange={e=>setPrice(e.target.value)}/></label>
      <label>Валюта<select value={currency} onChange={e=>setCurrency(e.target.value)}><option>UAH</option><option>USD</option></select></label>
      <label>Опис продажу<input maxLength={200} value={description} onChange={e=>setDescription(e.target.value)}/></label>
      <label><input type="checkbox" checked={remainder} onChange={e=>setRemainder(e.target.checked)}/>Продати решту вузла за вказаним описом</label>
      <label><input type="checkbox" checked={confirmSale} onChange={e=>setConfirmSale(e.target.checked)}/>Підтверджую передачу всього наведеного складу за одну ціну</label>
      <button disabled={busy||!confirmSale||price===''||Number(price)<0||preview.conflicts.length>0} onClick={()=>void send('sale',{type:'sale',quantity:1,sale_price:price,sale_currency:currency,assembly_token:preview.token,assembly_description:description,assembly_remainder:remainder},selected.part_id)}>{remainder?'Продати решту вузла':selected.completeness?'Продати вузол у зборі':'Продати деталь'}</button>
     </div>}
    </>}
    {editable&&selected.consumed_type==='sale'&&!selected.parent_id&&<>
     <p>Повертається майно за складом продажу. Гроші автоматично не повертаються.</p>
     <label><input type="checkbox" checked={confirmReturn} onChange={e=>setConfirmReturn(e.target.checked)}/>Підтверджую повне повернення фактичного складу без грошової операції</label>
     <button disabled={busy||!confirmReturn} onClick={()=>void send('return',{sale_operation_id:selected.consumed_operation_id,confirm_inventory_return_only:true})}>Повернути вузол на склад</button>
    </>}
   </>}
  </div>}
  <ul className="assembly-roots">{roots.slice(0,limit).map(render)}</ul>
  {roots.length>limit&&<button onClick={()=>setLimit(n=>n+50)}>Показати ще 50 позицій</button>}
 </section>;
}
