import {useContext,useEffect,useRef,useState} from 'react';
import {Boxes,ChevronDown,Package} from 'lucide-react';
import {api,ApiError,type Row} from './api';
import {assemblyUnitFor,assemblyReferenceLines} from './assemblyUnitCatalog';
import {TeamIdentity,useCan} from './permissions';
import {State,useLoad} from './shared';

type Command={path:string;body:Row};
const running=new Set<string>();
/** Physical operations belong to stock, never to catalogue selection.
 * Reuses the guarded assembly API; a reference is not a stored Part. */
export default function StockAssemblyPanel({part,onChanged}:{part:Row;onChanged:()=>void}){
 const can=useCan(),identity=useContext(TeamIdentity);
 const scope='warehouse-stock-assembly:'+identity?.workspace_account_id+':'+identity?.id+':'+part.id;
 const allowed=can('vehicles.view')&&can('inventory.view');
 const writable=allowed&&['dismantling.manage','inventory.edit','inventory.adjust_quantity'].every(can);
 const path='/vehicles/'+part.vehicle_id+'/assemblies';
 const [open,setOpen]=useState(false),[chosen,setChosen]=useState<number[]>([]),[conditions,setConditions]=useState<Record<number,string>>({}),[confirmed,setConfirmed]=useState(false),[complete,setComplete]=useState(false),[detach,setDetach]=useState<Row|null>(null),[detachConfirmed,setDetachConfirmed]=useState(false);
 const [busy,setBusy]=useState(false),[pending,setPending]=useState<Command|null>(null),[error,setError]=useState(''),[result,setResult]=useState('');
 const guard=useRef(false);
 useEffect(()=>{try{setPending(JSON.parse(sessionStorage.getItem(scope)||'null'));}catch{setError('Не вдалося відновити незавершену операцію.');}},[scope]);
 const data=useLoad(async()=>{
  if(!allowed||!part.vehicle_id)return null;
  const [ready,tree]=await Promise.all([api(path+'/readiness'),api(path)]);
  const node=tree.items?.find((n:Row)=>n.part_id===part.id);
  return {ready,tree,node,preview:open&&node?await api(path+'/'+node.id+'/preview'):null};
 },[open,allowed,part.id,part.vehicle_id,part.quantity,part.reserved_quantity]);
 const node=data.data?.node,preview=data.data?.preview,tree=data.data?.tree,unit=assemblyUnitFor(node||part);
 const children:Row[]=(tree?.items||[]).filter((n:Row)=>n.parent_id===node?.id&&node);
 const detached:Row[]=(tree?.items||[]).filter((n:Row)=>preview?.missing_component_ids?.includes(n.id));
 const refs=node&&unit?assemblyReferenceLines(node,tree.items,children):[];
 const alreadySeparated=(label:string)=>detached.some(n=>String(n.name).trim().toLocaleLowerCase('uk')===label.trim().toLocaleLowerCase('uk'));
 const block=!writable?'Немає дозволу на керування вузлом.':data.loading?'Перевіряємо фактичний склад…':data.error?'Не вдалося перевірити вузол.':!data.data?.ready?.enabled?'Керування вузлами недоступне.':Number(part.quantity)!==1?'Для розбору потрібна одна фізична одиниця. Уточніть партію; не змінюйте залишок вручну.':part.archived||part.assortment_enabled===false?'Позиція неактивна.':part.reserved_quantity>0||preview?.conflicts?.length?'Вузол зарезервований. Спочатку зніміть резерв.':node?.parent_id?'Спочатку відокремте цей компонент від батьківського вузла.':node?.consumed_operation_id||node?.consumed_type||node?.presence==='absent'?'Вузол уже передано або позначено відсутнім.':'';
 async function send(command:Command){
  if(guard.current||running.has(scope))return;
  guard.current=true;running.add(scope);setBusy(true);setError('');setResult('');
  let replay=false;
  try{
   replay=sessionStorage.getItem(scope)!==null;
   sessionStorage.setItem(scope,JSON.stringify(command));setPending(command);
   const r=await api(command.path,'POST',command.body);
   sessionStorage.removeItem(scope);setPending(null);
   setChosen([]);setConditions({});setConfirmed(false);setComplete(false);setDetach(null);setDetachConfirmed(false);
   setResult(r.count?`Відокремлено та додано на склад: ${r.count}. Вузол залишився неповним.`:r.detached?'Компонент відокремлено й оприбутковано.':r.confirmed?'Комплектність підтверджено.':'Вузол пов’язано зі складською позицією.');
   data.reload();onChanged();
  }catch(e){if(e instanceof ApiError&&[400,404,409,422].includes(e.status)||e instanceof ApiError&&e.status===403&&!replay){try{sessionStorage.removeItem(scope);}catch{}setPending(null);data.reload();}setError((e as Error).message);}
  finally{guard.current=false;running.delete(scope);setBusy(false);}
 }
 async function run(body:Row,split=false){if(busy||pending||block||!open)return;await send({path:path+(split?'/split':''),body:{...body,request_key:crypto.randomUUID(),confirm_physical:true}});}
 // Show a compact entry point even when a legacy part has not yet been linked.
 // For unrelated parts no new fetch or fake assembly is necessary.
 if(!allowed||!part.vehicle_id||(!unit&&!node?.completeness&&!children.length&&!pending&&!open))return null;
 const disabled=!!block||busy||!!pending||data.loading;
 return <section className="stock-assembly-panel" aria-label="Керування фізичним вузлом">
  <button type="button" className="stock-assembly-toggle secondary" aria-expanded={open} onClick={()=>setOpen(v=>!v)}><Boxes size={16}/>Керувати вузлом<ChevronDown size={15}/></button>
  {open&&<div className="stock-assembly-body">
   <State loading={data.loading} error={data.error}/>{data.error&&<button type="button" onClick={data.reload}>Повторити перевірку</button>}
   {pending&&<div className="notice"><p>Результат попередньої операції ще не підтверджено.</p><button type="button" disabled={busy} onClick={()=>void send(pending)}>Перевірити результат</button></div>}
   {error&&<p role="alert" className="error">{error}</p>}{result&&<p role="status" className="stock-assembly-result">{result}</p>}
   {!!block&&!data.loading&&<p role="status" className="stock-assembly-block">{block}</p>}
   {!data.loading&&data.data&&!node&&unit&&<><p>Ця складська позиція ще не пов’язана з фізичним вузлом.</p><label className="check-inline"><input type="checkbox" checked={complete} disabled={disabled} onChange={e=>setComplete(e.target.checked)}/>Підтверджую одну фізичну одиницю</label><button type="button" disabled={disabled||!complete} onClick={()=>void run({action:'link_part',part_id:part.id})}>Зв’язати зі складом</button></>}
   {node&&preview&&<><div className="stock-assembly-summary"><strong>{node.name}{node.position?' · '+node.position:''}</strong><small>{preview.missing_component_ids?.length||node.completeness==='incomplete'?'Неповний вузол':node.completeness==='complete'?'Комплектність підтверджено':'Комплектність потребує перевірки'}</small></div>
    {children.length>0&&<><h4>Фактичні складові</h4>{children.map(c=><div className="stock-assembly-child" key={c.id}><Package size={14}/><span>{c.name}</span><button type="button" disabled={disabled||!can('inventory.create')} onClick={()=>{setDetach(c);setDetachConfirmed(false);}}>Відокремити</button></div>)}</>}
    {detached.length>0&&<><h4>Відокремлено раніше</h4>{detached.map(c=><div className="stock-assembly-child" key={c.id}><Package size={14}/><span>{c.name}</span><small>Окремий облік</small></div>)}</>}
    {detach&&<div className="notice"><strong>Відокремити: {detach.name}</strong><label className="check-inline"><input type="checkbox" checked={detachConfirmed} onChange={e=>setDetachConfirmed(e.target.checked)}/>Підтверджую фізичне відокремлення</label><button type="button" className="primary" disabled={disabled||!detachConfirmed||!can('inventory.create')} onClick={()=>void run({action:'detach',item_id:detach.id})}>Відокремити й оприбуткувати</button><button type="button" onClick={()=>setDetach(null)}>Скасувати</button></div>}
    {unit&&<><h4>Розібрати вузол</h4><p className="stock-assembly-hint">Оберіть лише складові, які фактично зняли. Решта довідкова, не окремі залишки.</p>{refs.map((entry,i)=>{const separated=alreadySeparated(entry.label);const checked=chosen.includes(i);return <div key={entry.key} className="stock-assembly-ref"><label className="check-inline"><input type="checkbox" checked={checked} disabled={disabled||separated||entry.kind==='attached'||!can('inventory.create')} onChange={e=>{setChosen(v=>e.target.checked?[...v,i]:v.filter(x=>x!==i));setConfirmed(false);}}/><span>{entry.label}</span></label>{separated?<small>Відокремлено</small>:entry.kind==='attached'?<small>У складі вузла</small>:<small>Можлива складова</small>}{checked&&<select aria-label={'Стан '+entry.label} value={conditions[i]||'used'} disabled={disabled} onChange={e=>{setConditions(v=>({...v,[i]:e.target.value}));setConfirmed(false);}}><option value="used">Вживана</option><option value="new">Нова</option><option value="damaged">Пошкоджена</option><option value="refurbished">Відновлена</option></select>}</div>})}
    {!!chosen.length&&<><label className="check-inline"><input type="checkbox" checked={confirmed} disabled={disabled} onChange={e=>setConfirmed(e.target.checked)}/>Підтверджую фактичний демонтаж {chosen.length} складових</label><button type="button" className="primary" disabled={disabled||!confirmed||!can('inventory.create')} onClick={()=>void run({root_item_id:node.id,unit_id:unit.id,token:preview.token,components:chosen.slice().sort((a,b)=>a-b).map(index=>({index,condition:conditions[index]||'used'}))},true)}>Відокремити й оприбуткувати {chosen.length}</button></>}</>}
    {!preview.missing_component_ids?.length&&!preview.issues?.length&&node.completeness!=='complete'&&<><label className="check-inline"><input type="checkbox" checked={complete} disabled={disabled} onChange={e=>setComplete(e.target.checked)}/>Фактичний склад перевірено</label><button type="button" disabled={disabled||!complete} onClick={()=>void run({action:'confirm',item_id:node.id,token:preview.token})}>Підтвердити комплектність</button></>}
   </>}
  </div>}
 </section>;
}
