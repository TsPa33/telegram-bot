import {useEffect,useRef,useState} from 'react';
import {Link} from 'react-router-dom';
import {api,money,when,type Row,type Page} from './api';
import {Empty,Modal,Pager} from './components';
import {useCan} from './permissions';
import {State,useLoad,type Notify} from './shared';

const states:Record<string,string>={new:'Нове',reserved:'Зарезервовано',shipped:'Відправлено',completed:'Завершено',cancelled:'Скасовано'};
const phoneError=(phone:string)=>!phone?'':!/^\+?[0-9() .\-]+$/.test(phone)||phone.replace(/\D/g,'').length>15?'Вкажіть коректний номер телефону':phone.replace(/\D/g,'').length<3?'Вкажіть щонайменше 3 цифри':'';
const totals=(order:Row)=>Object.entries(order.totals_by_currency||{}).map(([currency,value])=>money(value,currency)).join(' + ');

/** Buyers stay workspace-scoped. Phone finds a profile; history uses its immutable ID. */
export default function SalesBuyers({features,notify}:{features:string[];notify:Notify}){
 const can=useCan();
 const [phone,setPhone]=useState(''),[term,setTerm]=useState(''),[page,setPage]=useState(0),[selected,setSelected]=useState<string|null>(null);
 useEffect(()=>{const t=setTimeout(()=>setTerm(phone.trim()),250);return()=>clearTimeout(t);},[phone]);
 const invalid=phoneError(term),key=JSON.stringify([term,page]);
 const results=useLoad(()=>can('orders.view')&&!invalid?api<Page>('/buyers?'+new URLSearchParams({phone:term,limit:'50',offset:String(page*50)})).then(data=>({key,data})):Promise.resolve(null),[key,invalid,can('orders.view')]);
 const current=!results.loading&&!results.error&&!invalid&&phone.trim()===term&&results.data?.key===key?results.data.data:null;
 if(!can('orders.view'))return <p role="alert">Доступ обмежено</p>;
 return <div className="sc-buyers-layout">
  <section className="panel sc-buyers-list" aria-label="Список покупців">
   <h2>Покупці</h2>
   <label>Телефон<input type="tel" aria-label="Пошук покупця за телефоном" placeholder="+380…" maxLength={50} value={phone} onChange={e=>{setPhone(e.target.value);setPage(0);setSelected(null);}}/></label>
   <State loading={results.loading||phone.trim()!==term} error={invalid||results.error}/>
   {results.error&&<button type="button" onClick={results.reload}>Повторити пошук</button>}
   {current&&<>
    <div className="sc-buyer-rows">{current.items.map(buyer=><button type="button" key={buyer.id} aria-pressed={selected===buyer.id} onClick={()=>setSelected(buyer.id)}><strong>{buyer.name}</strong><span>{buyer.phone}</span>{buyer.additional_phone&&<small>{buyer.additional_phone}</small>}</button>)}</div>
    {!current.items.length&&<Empty title="Покупців не знайдено">Спробуйте інший номер телефону.</Empty>}
    <Pager total={current.total} page={page} setPage={setPage}/>
   </>}
  </section>
  <aside className="panel sc-buyer-detail" aria-label="Картка покупця">
   {selected?<BuyerProfile key={selected} id={selected} features={features} notify={notify} onClose={()=>setSelected(null)} onUpdated={results.reload}/>:<p className="sc-note">Виберіть покупця, щоб переглянути контакти та історію замовлень.</p>}
  </aside>
 </div>;
}

function BuyerProfile({id,features,notify,onClose,onUpdated}:{id:string;features:string[];notify:Notify;onClose:()=>void;onUpdated:()=>void}){
 const can=useCan(),[page,setPage]=useState(0),[edit,setEdit]=useState(false);
 const profile=useLoad(()=>api<Row>('/buyers/'+encodeURIComponent(id)),[id]);
 const supported=features.includes('buyer_order_history');
 const historyKey=id+':'+page;
 const history=useLoad(()=>supported?api<Page>('/orders?'+new URLSearchParams({buyer_id:id,limit:'50',offset:String(page*50)})).then(data=>({key:historyKey,data})):Promise.resolve(null),[historyKey,supported]);
 const current=!history.loading&&!history.error&&history.data?.key===historyKey?history.data.data:null;
 const row=profile.data?.id===id?profile.data:null;
 return <>
  <div className="sc-buyer-heading"><h2>{row?.name||'Покупець'}</h2><button type="button" aria-label="Закрити картку покупця" onClick={onClose}>×</button></div>
  <State loading={profile.loading} error={profile.error}/>
  {profile.error&&<button type="button" onClick={profile.reload}>Повторити завантаження</button>}
  {row&&!profile.error&&<>
   <dl className="details sc-buyer-contacts">
    <div><dt>Телефон</dt><dd><a href={'tel:'+row.phone}>{row.phone}</a></dd></div>
    {row.additional_phone&&<div><dt>Додатковий телефон</dt><dd><a href={'tel:'+row.additional_phone}>{row.additional_phone}</a></dd></div>}
    {row.notes&&<div><dt>Примітка</dt><dd>{row.notes}</dd></div>}
   </dl>
   {can('orders.edit')&&<button type="button" className="secondary" onClick={()=>setEdit(true)}>Редагувати покупця</button>}
   <h3 className="sc-buyer-history-heading">Історія замовлень</h3>
   {!supported?<p className="sc-note" role="status">Історія за покупцем поки недоступна. Контакти можна переглядати.</p>:<>
    <State loading={history.loading} error={history.error}/>
    {history.error&&<button type="button" onClick={history.reload}>Повторити історію</button>}
    {current&&<>
     <div className="sc-buyer-orders">{current.items.map(order=><Link key={order.id} to={'/orders/'+order.id} className="sc-buyer-order">
      <strong>Замовлення №{order.number}</strong>
      <span>{states[order.status]||'Замовлення'}{order.sold_at?' · Продаж проведено':''}</span>
      <small>{when(order.created_at)} · {(order.lines||[]).length} поз.</small>
      <small>{(order.lines||[]).map((line:Row)=>line.name).join(', ')}</small>
      {can('sales.view_financials')&&totals(order)&&<b>{totals(order)}</b>}
     </Link>)}</div>
     {!current.items.length&&<Empty title="Замовлень ще немає"/>}
     <Pager total={current.total} page={page} setPage={setPage}/>
    </>}
   </>}
   {edit&&<EditBuyer buyer={row} notify={notify} onClose={()=>setEdit(false)} onSaved={()=>{setEdit(false);profile.reload();onUpdated();}}/>}
  </>}
 </>;
}

function EditBuyer({buyer,notify,onClose,onSaved}:{buyer:Row;notify:Notify;onClose:()=>void;onSaved:()=>void}){
 const [name,setName]=useState(String(buyer.name||'')),[phone,setPhone]=useState(String(buyer.phone||'')),[additional,setAdditional]=useState(String(buyer.additional_phone||'')),[notes,setNotes]=useState(String(buyer.notes||'')),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const guard=useRef(false);
 const close=()=>{if(!guard.current)onClose();};
 return <Modal title="Редагувати покупця" onClose={close}><form onSubmit={async e=>{
  e.preventDefault();if(guard.current)return;guard.current=true;setBusy(true);setError('');
  try{await api('/buyers/'+encodeURIComponent(buyer.id),'PUT',{name:name.trim(),phone,additional_phone:additional,notes});notify('Дані покупця оновлено');onSaved();}
  catch(e){setError((e as Error).message);}finally{guard.current=false;setBusy(false);}
 }}>
  <fieldset disabled={busy}><div className="form-grid">
   <label>Ім’я<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label>
   <label>Телефон<input required type="tel" maxLength={50} value={phone} onChange={e=>setPhone(e.target.value)}/></label>
   <label>Додатковий телефон<input type="tel" maxLength={50} value={additional} onChange={e=>setAdditional(e.target.value)}/></label>
   <label className="wide">Примітка<textarea maxLength={10000} value={notes} onChange={e=>setNotes(e.target.value)}/></label>
  </div></fieldset>
  {error&&<p role="alert" className="error">{error}</p>}
  <p className="sc-note">Зміна контактів покупця не переписує історичні дані проведених продажів.</p>
  <div className="modal-actions"><button type="submit" className="primary" disabled={busy||!name.trim()||phone.replace(/\D/g,'').length<7}>Зберегти</button></div>
 </form></Modal>;
}
