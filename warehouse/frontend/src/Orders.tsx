import {Permit,useCan} from './permissions';
import {useEffect,useRef,useState} from 'react';
import {Link,useNavigate,useParams,Navigate} from 'react-router-dom';
import {all,api,money,when,type Row,type Page} from './api';
import {Empty,Modal,Pager} from './components';
import {Confirm,State,useLoad,type Notify} from './shared';
import {useOrderRequests} from './orderRequests';

const statuses:Record<string,string>={new:'Нове',reserved:'Зарезервовано',shipped:'Відправлено',completed:'Завершено',cancelled:'Скасовано'};
const deliveries:Record<string,string>={pickup:'Самовивіз',branch:'Доставка у відділення',address:'Адресна доставка'};
const eventNames:Record<string,string>={created:'Створено замовлення',updated:'Змінено дані',lines_changed:'Змінено позиції',status_changed:'Змінено статус',reserved:'Зарезервовано',reservation_released:'Знято резерв',sale_confirmed:'Підтверджено продаж',cancelled:'Скасовано'};
const totals=(order:Row)=>Object.entries(order.totals_by_currency||{}).map(([currency,value])=>money(value,currency)).join(' + ');
const donor=(part:Row)=>{const v=part.donor_snapshot;return v?.model?`${v.manufacturer} ${v.model} · ${v.year} · №${v.number}`:'';};
function useTerm(value:string){const [term,setTerm]=useState(value);useEffect(()=>{const t=setTimeout(()=>setTerm(value),250);return()=>clearTimeout(t);},[value]);return term;}

export default function Orders({accountId,notify}:{accountId:string;notify:Notify}){
 const can=useCan();
 const {id}=useParams(),navigate=useNavigate(),[create,setCreate]=useState(false),[q,setQ]=useState(''),[status,setStatus]=useState(''),[page,setPage]=useState(0),[error,setError]=useState('');
 const term=useTerm(q),requests=useOrderRequests(accountId);
 const gate=useLoad(()=>api('/orders/readiness'),[]);
 const params=new URLSearchParams({q:term,limit:'50',offset:String(page*50),...(status?{status}:{})});
 const list=useLoad(()=>id?Promise.resolve(null):api<Page>('/orders?'+params),[id,params.toString()]);
 if(!id)return <Navigate to="/sales?tab=orders" replace/>;
 return <>
  <div className="page-heading"><div><h1>Замовлення</h1><p>Покупці, погоджені ціни та доставка.</p></div><Permit permission="orders.create"><button className="secondary" disabled={!can('inventory.view')||gate.data?.contract_version!==6||!!requests.pending} onClick={()=>setCreate(true)}>Нове замовлення</button></Permit></div>
  <State loading={gate.loading} error={gate.error||requests.storageError||error}/>{gate.error&&<button onClick={gate.reload}>Перевірити API знову</button>}
  {requests.pending&&<section className="notice" role="status"><p>Результат попереднього запиту не підтверджений. Перевірте його перед наступною дією. Повтор використовує той самий запит.</p><button disabled={requests.busy} onClick={async()=>{setError('');try{const result=await requests.retry();list.reload();navigate('/orders/'+result.id);}catch(e){setError((e as Error).message);}}}>Перевірити результат запиту</button></section>}
  {id?<OrderDetail key={id} id={id} accountId={accountId} notify={notify}/>:<>
   <section className="panel padded order-filters"><label>Номер або телефон<input type="search" aria-label="Пошук замовлень" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}}/></label><label>Статус<select aria-label="Статус замовлення" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">Усі статуси</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></section>
   <State loading={list.loading||q!==term} error={list.error}/>{list.error&&<button onClick={list.reload}>Повторити завантаження</button>}
   {!list.loading&&q===term&&list.data&&<><section className="orders-list">{list.data.items.map(order=><Link className="panel order-summary" key={order.id} to={'/orders/'+order.id}><header><strong>№{order.number} · {order.contact_name}</strong><span>{statuses[order.status]}{order.sold_at?' · Продано':''}</span></header><small>{when(order.created_at)} · {order.contact_phone}</small><p>{order.lines.map((line:Row)=>`${line.name} × ${line.quantity}`).join(', ')}</p><footer><strong>{totals(order)}</strong><span>{deliveries[order.delivery_method]}</span></footer></Link>)}</section>{!list.data.items.length&&<Empty title="Замовлень не знайдено"/>}<Pager total={list.data.total} page={page} setPage={setPage}/></>}
  </>}
  {create&&<OrderComposer accountId={accountId} onClose={()=>setCreate(false)} onCreated={order=>{notify(order.reservation_warning||'Замовлення збережено');setCreate(false);navigate('/orders/'+order.id);list.reload();}}/>}
 </>;
}

function DeliveryFields({value,set}:{value:Row;set:(value:Row)=>void}){
 return <div className="form-grid"><label>Доставка<select aria-label="Доставка" value={value.delivery_method} onChange={e=>set({...value,delivery_method:e.target.value})}>{Object.entries(deliveries).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
 {value.delivery_method!=='pickup'&&<><label>Місто<input required maxLength={150} value={value.city} onChange={e=>set({...value,city:e.target.value})}/></label><label>{value.delivery_method==='branch'?'Відділення':'Адреса'}<input required maxLength={300} value={value.delivery_address} onChange={e=>set({...value,delivery_address:e.target.value})}/></label></>}
 <label>Номер ТТН<input maxLength={100} value={value.tracking_number} onChange={e=>set({...value,tracking_number:e.target.value})}/></label><label className="wide">Примітка до замовлення<textarea maxLength={10000} value={value.notes} onChange={e=>set({...value,notes:e.target.value})}/></label></div>;
}

function BuyerPicker({selected,onSelect}:{selected:Row|null;onSelect:(value:Row|null)=>void}){
 const can=useCan();
 const [phone,setPhone]=useState(''),term=useTerm(phone),[page,setPage]=useState(0),[name,setName]=useState(''),[notes,setNotes]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),guard=useRef(false);
 const digits=term.replace(/\D/g,'');
 const results=useLoad(()=>can('orders.view')&&digits.length>=3?api<Page>('/buyers?'+new URLSearchParams({phone:term,limit:'50',offset:String(page*50)})):Promise.resolve(null),[term,page]);
 if(selected)return <section className="order-buyer-selected"><strong>{selected.name}</strong><span>{selected.phone}</span>{selected.notes&&<p>{selected.notes}</p>}<button type="button" onClick={()=>onSelect(null)}>Інший покупець</button></section>;
 return <section className="order-buyer-picker"><h3>Покупець</h3><label>Телефон покупця<input type="tel" required maxLength={50} value={phone} onChange={e=>{setPhone(e.target.value);setPage(0);}}/></label><State loading={results.loading} error={results.error}/>
  {results.data&&term===phone&&<><div className="order-picker-results">{results.data.items.map(buyer=><button type="button" key={buyer.id} onClick={()=>onSelect(buyer)}>{buyer.name} · {buyer.phone}</button>)}</div>{!results.data.total&&<small>Покупців за цим телефоном не знайдено.</small>}<Pager total={results.data.total} page={page} setPage={setPage}/></>}
  <label>Ім’я нового покупця<input maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label><label>Примітка про покупця<textarea maxLength={10000} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
  {error&&<p role="alert" className="error">{error}</p>}{uncertain&&<p role="alert">Не повторюйте створення: результат невідомий. Знайдіть покупця за телефоном і виберіть його зі списку.</p>}
  <Permit permission="orders.create"><button type="button" disabled={busy||uncertain||!name.trim()||digits.length<7} onClick={async()=>{if(guard.current)return;guard.current=true;setBusy(true);setError('');try{onSelect(await api('/buyers','POST',{name:name.trim(),phone,notes}));}catch(e){setError((e as Error).message);if(!(e instanceof Error&&'status' in e&&Number(e.status)<500))setUncertain(true);results.reload();}finally{guard.current=false;setBusy(false);}}}>Створити покупця</button></Permit>{uncertain&&<button type="button" onClick={results.reload}>Оновити пошук покупця</button>}
 </section>;
}

type LineDraft={part_id:string;name:string;donor:string;quantity:string;unit_price:string;currency:string};
const draft=(part:Row):LineDraft=>({part_id:part.part_id||part.id,name:part.name,donor:donor(part),quantity:String(part.quantity&&part.part_id?part.quantity:1),unit_price:String(part.unit_price??part.selling_price??''),currency:part.currency||'UAH'});
function linePayload(lines:LineDraft[]){return lines.map(line=>{const price=line.unit_price.replace(',','.');if(!/^\d{1,12}(\.\d{1,2})?$/.test(price))throw Error('Вкажіть погоджену ціну кожної деталі з точністю до двох знаків.');if(!/^\d+$/.test(line.quantity)||+line.quantity<1||+line.quantity>1000000)throw Error('Кількість має бути цілим числом від 1 до 1 000 000.');return {part_id:line.part_id,quantity:Number(line.quantity),unit_price:price,currency:line.currency};});}
function DraftTotals({lines}:{lines:LineDraft[]}){
 const values:Record<string,bigint>={};for(const line of lines){const match=/^(\d{1,12})(?:[.,](\d{1,2}))?$/.exec(line.unit_price);if(match&&/^\d+$/.test(line.quantity))values[line.currency]=(values[line.currency]||0n)+(BigInt(match[1])*100n+BigInt((match[2]||'').padEnd(2,'0')))*BigInt(line.quantity);}
 return <p className="order-totals">{Object.entries(values).map(([currency,cents])=><strong key={currency}>{money(`${cents/100n}.${String(cents%100n).padStart(2,'0')}`,currency)}</strong>)}</p>;
}
function LineEditor({lines,set}:{lines:LineDraft[];set:(value:LineDraft[])=>void}){
 const can=useCan();
 const [q,setQ]=useState(''),term=useTerm(q),[page,setPage]=useState(0);
 const vehicles=useLoad(()=>can('vehicles.view')?Promise.all([all('/vehicles'),all('/vehicles?archived=true')]).then(groups=>groups.flat()):Promise.resolve([]),[]);
 const results=useLoad(()=>can('inventory.view')&&term?api<Page>('/parts?'+new URLSearchParams({q:term,in_stock:'true',limit:'50',offset:String(page*50)})):Promise.resolve(null),[term,page]);
 function update(i:number,key:string,value:string){set(lines.map((line,n)=>n===i?{...line,[key]:value}:line));}
 return <section><h3>Запчастини</h3><div className="order-lines-editor">{lines.map((line,i)=><article className="order-line-editor" key={line.part_id}><header><strong>{line.name}</strong><button type="button" aria-label={`Прибрати ${line.name}`} onClick={()=>set(lines.filter((_,n)=>n!==i))}>Прибрати</button></header>{line.donor&&<small>{line.donor}</small>}<div className="order-line-values"><label>Кількість<input aria-label={`Кількість ${line.name}`} type="number" required min={1} max={1000000} step={1} value={line.quantity} onChange={e=>update(i,'quantity',e.target.value)}/></label><label>Погоджена ціна<input aria-label={`Погоджена ціна ${line.name}`} inputMode="decimal" required value={line.unit_price} onChange={e=>update(i,'unit_price',e.target.value)}/></label><label>Валюта<select aria-label={`Валюта ${line.name}`} value={line.currency} onChange={e=>update(i,'currency',e.target.value)}><option>UAH</option><option>USD</option></select></label></div></article>)}</div>
  <DraftTotals lines={lines}/><Permit permission="inventory.view"><label>Додати запчастину<input type="search" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}} placeholder="Назва, OEM або артикул"/></label></Permit><State loading={results.loading} error={results.error}/>
  {results.data&&q===term&&<><div className="order-picker-results">{results.data.items.map(part=><button type="button" key={part.id} disabled={lines.some(line=>line.part_id===part.id)||lines.length>=100} onClick={()=>{set([...lines,draft({...part,donor_snapshot:vehicles.data?.find(v=>v.id===part.vehicle_id)})]);setQ('');}}>{part.name} · Вільних: {part.available_quantity}{part.oem_number?` · OEM ${part.oem_number}`:''}{part.article_number?` · ${part.article_number}`:''}</button>)}</div>{!results.data.total&&<small>Запчастин не знайдено.</small>}<Pager total={results.data.total} page={page} setPage={setPage}/></>}
 </section>;
}

export function OrderComposer({accountId,initialPart,onClose,onCreated}:{accountId:string;initialPart?:Row;onClose:()=>void;onCreated:(order:Row)=>void}){
 const can=useCan();
 const [lines,setLines]=useState<LineDraft[]>(initialPart?[draft(initialPart)]:[]),[buyer,setBuyer]=useState<Row|null>(null),[delivery,setDelivery]=useState<Row>({delivery_method:'pickup',city:'',delivery_address:'',tracking_number:'',notes:''}),[error,setError]=useState(''),[reserve,setReserve]=useState(false);
 const request=useOrderRequests(accountId),guard=useRef(false),gate=useLoad(()=>api('/orders/readiness'),[]);
 return <Modal className="order-dialog" title="Оформити замовлення" onClose={()=>{if(!request.busy)onClose();}}><form onSubmit={async e=>{e.preventDefault();if(guard.current)return;guard.current=true;setError('');try{if(!buyer)throw Error('Виберіть або створіть покупця.');const order=await request.run('/orders','POST',{buyer_id:buyer.id,lines:linePayload(lines),...delivery});if(reserve){try{await request.run('/orders/'+order.id+'/reserve','POST',{});}catch(e){order.reservation_warning='Замовлення збережено. Резерв не підтверджено: '+(e as Error).message;}}onCreated(order);}catch(e){setError((e as Error).message);}finally{guard.current=false;}}}>
 <State loading={gate.loading} error={gate.error||request.storageError}/><fieldset disabled={request.busy||!!request.pending}><LineEditor lines={lines} set={setLines}/><BuyerPicker selected={buyer} onSelect={setBuyer}/><h3>Доставка й примітки</h3><small>Для Нової пошти або іншої доставки виберіть відділення чи адресу. Перевізника вкажіть у примітці.</small><DeliveryFields value={delivery} set={setDelivery}/><Permit permission="orders.fulfill"><label className="check-inline"><input type="checkbox" checked={reserve} onChange={e=>setReserve(e.target.checked)}/>Після збереження зарезервувати</label></Permit>{reserve&&<small>Резервування — окрема дія. Якщо залишку не вистачить, замовлення збережеться без резерву.</small>}</fieldset>
 {error&&<p role="alert" className="error">{error}</p>}{request.pending&&!request.busy&&<p role="status">Відкрийте «Замовлення», щоб перевірити результат запиту перед повторним створенням.</p>}<div className="modal-actions"><button className="primary" disabled={request.busy||!!request.pending||gate.data?.contract_version!==6||!lines.length||!buyer}>Зберегти замовлення</button></div></form></Modal>;
}

function OrderDetail({id,accountId,notify}:{id:string;accountId:string;notify:Notify}){
 const order=useLoad(()=>api('/orders/'+id),[id]),[eventPage,setEventPage]=useState(0),events=useLoad(()=>api<Page>(`/orders/${id}/events?limit=50&offset=${eventPage*50}`),[id,eventPage]);
 const [edit,setEdit]=useState(false),[editLines,setEditLines]=useState(false),[confirm,setConfirm]=useState<string|null>(null),[error,setError]=useState('');
 const request=useOrderRequests(accountId),row=order.data;
 const reload=()=>{order.reload();events.reload();};
 useEffect(()=>{window.addEventListener('warehouse:orders-changed',reload);return()=>window.removeEventListener('warehouse:orders-changed',reload);},[id]);
 async function perform(action:string){setError('');try{await request.run('/orders/'+id+(action==='shipped'||action==='completed'?'/status':'/'+action),'POST',action==='shipped'||action==='completed'?{status:action}:{});notify('Замовлення оновлено');}catch(e){setError((e as Error).message);throw e;}finally{reload();}}
 const closed=row&&['completed','cancelled'].includes(row.status),open=row&&!closed&&!row.sold_at;
 return <><Link to="/orders">← Усі замовлення</Link><State loading={order.loading} error={order.error||error}/>{order.error&&<button onClick={order.reload}>Повторити завантаження</button>}
 {row&&<article className="panel padded order-detail"><header className="order-detail-heading"><div><h2>Замовлення №{row.number}</h2><small>{when(row.created_at)}</small></div><strong>{statuses[row.status]}{row.sold_at?' · Продано':''}</strong></header><section><h3>{row.contact_name}</h3><a href={'tel:'+row.contact_phone}>{row.contact_phone}</a></section>
 <section className="order-detail-lines">{row.lines.map((line:Row)=><article key={line.id}><strong>{line.name}</strong>{donor(line)&&<small>{donor(line)}</small>}<span>{line.quantity} × {money(line.unit_price,line.currency)}</span><b>{money(line.line_total,line.currency)}</b></article>)}</section><p className="order-totals">Разом: {totals(row)}</p>
 <section className="order-delivery"><strong>{deliveries[row.delivery_method]}</strong>{row.delivery_method!=='pickup'&&<p>{row.city} · {row.delivery_address}</p>}{row.tracking_number&&<p>ТТН: {row.tracking_number}</p>}{row.notes&&<p className="order-notes">{row.notes}</p>}</section>
 <div className="stock-detail-actions"><fieldset className="order-action-group" disabled={request.busy||!!request.pending||order.loading}>
 {!closed&&<Permit permission="orders.edit"><button onClick={()=>setEdit(true)}>Редагувати</button></Permit>}{open&&row.status==='new'&&<Permit permission="orders.fulfill"><button onClick={()=>setConfirm('reserve')}>Зарезервувати</button></Permit>}{open&&row.status==='reserved'&&<Permit permission="orders.fulfill"><button onClick={()=>setConfirm('release')}>Зняти резерв</button></Permit>}{open&&<Permit permission="orders.fulfill"><Permit permission="sales.create"><button className="primary" onClick={()=>setConfirm('sell')}>Підтвердити продаж</button></Permit></Permit>}
 {!closed&&['new','reserved'].includes(row.status)&&(row.sold_at||row.reservations.length>0)&&<Permit permission="orders.edit"><button onClick={()=>setConfirm('shipped')}>Позначити відправленим</button></Permit>}{row.status==='shipped'&&row.sold_at&&<Permit permission="orders.edit"><button onClick={()=>setConfirm('completed')}>Завершити замовлення</button></Permit>}{open&&<Permit permission="orders.fulfill"><button onClick={()=>setConfirm('cancel')}>Скасувати замовлення</button></Permit>}{open&&row.status==='new'&&!row.reservations.length&&<Permit permission="orders.edit"><Permit permission="sales.view_financials"><button onClick={()=>setEditLines(true)}>Змінити позиції</button></Permit></Permit>}</fieldset></div>
 <h3>Історія подій</h3><State loading={events.loading} error={events.error}/>{events.error&&<button onClick={events.reload}>Повторити історію</button>}<ol className="order-events">{events.data?.items.map(event=><li key={event.id}><strong>{eventNames[event.type]||'Зміна замовлення'}</strong><small>{when(event.created_at)} · {event.actor_name||event.data.actor_identity?.name||'Не зафіксовано'}</small>{event.type==='status_changed'&&<span>{statuses[event.data.before]} → {statuses[event.data.after]}</span>}{event.type==='sale_confirmed'&&event.data.lines?.map((line:Row)=><span key={line.id}>{line.name} × {line.quantity} · {money(line.unit_price,line.currency)}</span>)}{event.type==='updated'&&<span>{event.data.after?.contact_name} · {event.data.after?.contact_phone}</span>}</li>)}</ol><Pager total={events.data?.total||0} page={eventPage} setPage={setEventPage}/>
 </article>}
 {confirm&&<Confirm destructive={confirm==='cancel'} title={{sell:'Підтвердити продаж?',cancel:'Скасувати замовлення?',reserve:'Зарезервувати запчастини?',release:'Зняти резерв?',shipped:'Позначити відправленим?',completed:'Завершити замовлення?'}[confirm]||''} text={confirm==='sell'?'Погоджені позиції буде списано зі складу. Повторний продаж цього замовлення неможливий.':confirm==='cancel'?'Замовлення буде скасовано, його резерви — знято.':'Зміни застосуються до всіх позицій замовлення.'} onClose={()=>setConfirm(null)} onConfirm={async()=>{try{await perform(confirm);}finally{setConfirm(null);}}}/>}
 {edit&&row&&<MetadataEditor row={row} accountId={accountId} onClose={()=>setEdit(false)} onSaved={()=>{setEdit(false);reload();}}/>}
 {editLines&&row&&<OrderLinesEditor row={row} accountId={accountId} onClose={()=>setEditLines(false)} onSaved={()=>{setEditLines(false);reload();}}/>}
 </>;
}
function MetadataEditor({row,accountId,onClose,onSaved}:{row:Row;accountId:string;onClose:()=>void;onSaved:()=>void}){
 const [value,setValue]=useState<Row>({...row}),[error,setError]=useState(''),request=useOrderRequests(accountId);
 return <Modal title="Дані замовлення" onClose={()=>{if(!request.busy)onClose();}}><form onSubmit={async e=>{e.preventDefault();setError('');try{const {contact_name,contact_phone,delivery_method,city,delivery_address,tracking_number,notes}=value;await request.run('/orders/'+row.id,'PATCH',{contact_name,contact_phone,delivery_method,city,delivery_address,tracking_number,notes});onSaved();}catch(e){setError((e as Error).message);}}}><fieldset disabled={request.busy||!!request.pending}><div className="form-grid"><label>Ім’я покупця<input required maxLength={200} value={value.contact_name} onChange={e=>setValue({...value,contact_name:e.target.value})}/></label><label>Телефон<input required maxLength={50} type="tel" value={value.contact_phone} onChange={e=>setValue({...value,contact_phone:e.target.value})}/></label></div><DeliveryFields value={value} set={setValue}/></fieldset>{error&&<p role="alert" className="error">{error}</p>}<div className="modal-actions"><button className="primary" disabled={request.busy||!!request.pending}>Зберегти зміни</button></div></form></Modal>;
}
function OrderLinesEditor({row,accountId,onClose,onSaved}:{row:Row;accountId:string;onClose:()=>void;onSaved:()=>void}){
 const [lines,setLines]=useState<LineDraft[]>(row.lines.map(draft)),[error,setError]=useState(''),request=useOrderRequests(accountId);
 return <Modal className="order-dialog" title="Позиції замовлення" onClose={()=>{if(!request.busy)onClose();}}><form onSubmit={async e=>{e.preventDefault();setError('');try{await request.run('/orders/'+row.id+'/lines','PUT',{lines:linePayload(lines)});onSaved();}catch(e){setError((e as Error).message);}}}><fieldset disabled={request.busy||!!request.pending}><LineEditor lines={lines} set={setLines}/></fieldset>{error&&<p role="alert" className="error">{error}</p>}<div className="modal-actions"><button className="primary" disabled={request.busy||!!request.pending||!lines.length}>Зберегти позиції</button></div></form></Modal>;
}
