import {useEffect,useState} from 'react';
import {all,api,labels,money,when,type Page,type Row} from './api';
import {Pager,Empty} from './components';
import {State,useLoad} from './shared';
export default function StockHistory({partId='',vehicleId=''}:{partId?:string;vehicleId?:string}){
 const [type,setType]=useState(''),[vehicle,setVehicle]=useState(vehicleId),[part,setPart]=useState(partId),[from,setFrom]=useState(''),[to,setTo]=useState(''),[page,setPage]=useState(0);
 const lookups=useLoad(()=>Promise.all([all('/vehicles'),all('/vehicles?archived=true'),all('/parts'),all('/parts?archived=true'),api('/auth/me')]),[]);
 const vehicles=[...(lookups.data?.[0] as Row[]||[]),...(lookups.data?.[1] as Row[]||[])],parts=[...(lookups.data?.[2] as Row[]||[]),...(lookups.data?.[3] as Row[]||[])],me=lookups.data?.[4] as Row|undefined;
 const query=new URLSearchParams({limit:'50',offset:String(page*50)});
 if(type)query.set('type',type);if(vehicle)query.set('vehicle_id',vehicle);if(part)query.set('part_id',part);
 if(from)query.set('date_from',new Date(from+'T00:00:00').toISOString());if(to)query.set('date_to',new Date(to+'T23:59:59.999').toISOString());
 const {data,error,loading}=useLoad(()=>api<Page>('/audit?'+query).then(data=>({...data,query_key:query.toString()})),[query.toString()]);
 const current=data?.query_key===query.toString();
 useEffect(()=>setPage(0),[type,vehicle,part,from,to]);
 const vehicleName=(id:string)=>{const v=vehicles.find(v=>v.id===id);return v?`${v.manufacturer} ${v.model} · ${v.year} · №${v.number}`:id?'Автомобіль недоступний':'Без автомобіля';};
 return <section className="stock-history" aria-label="Історія операцій">
  <div className="stock-history-filters">
   <label>Тип операції<select aria-label="Тип історії" value={type} onChange={e=>setType(e.target.value)}><option value="">Усі події аудиту</option>{['sale','write_off','transfer','reserve','release','correction','receipt','part_update'].map(t=><option key={t} value={t}>{labels[t]||t}</option>)}</select></label>
   {!vehicleId&&<label>Автомобіль<select aria-label="Автомобіль історії" value={vehicle} onChange={e=>{setVehicle(e.target.value);setPart(partId);}}><option value="">Усі автомобілі</option>{vehicles.map(v=><option key={v.id} value={v.id}>{vehicleName(v.id)}</option>)}</select></label>}
   {!partId&&<label>Запчастина<select aria-label="Запчастина історії" value={part} onChange={e=>setPart(e.target.value)}><option value="">Усі запчастини</option>{parts.filter(p=>!vehicle||p.vehicle_id===vehicle).map(p=><option key={p.id} value={p.id}>{p.name}{p.archived?' · архів':''}</option>)}</select></label>}
   <label>Від<input aria-label="Історія від" type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>До<input aria-label="Історія до" type="date" min={from||undefined} value={to} onChange={e=>setTo(e.target.value)}/></label>
  </div>
  <State error={error||lookups.error||(from&&to&&from>to?'Початкова дата пізніша за кінцеву.':'')} loading={loading||lookups.loading}/>
  {current&&data.items.map(row=>{
   const before=row.before||{},after=row.after||{},name=after.name||before.name||parts.find(p=>p.id===row.part_id)?.name||'Запис обліку';
   const quantity=Number.isInteger(before.quantity)&&Number.isInteger(after.quantity)?after.quantity-before.quantity:null;
   const reserved=Number.isInteger(before.reserved_quantity)&&Number.isInteger(after.reserved_quantity)?after.reserved_quantity-before.reserved_quantity:null;
   // Preserve missing historical currency/price as unknown; do not infer sale proceeds.
   const price=after.selling_price??before.selling_price,currency=after.currency||before.currency;
   return <article className="stock-history-event" key={row.id}><header><strong>{labels[row.type]||'Інша подія аудиту'}</strong><time>{when(row.created_at)}</time></header><b>{name}</b><small>{vehicleName(row.vehicle_id)}</small>
    {quantity!==null&&<p>Зміна кількості: {quantity>0?'+':''}{quantity} · Залишок після: {after.quantity}</p>}
    {reserved!==null&&reserved!==0&&<p>Зміна резерву: {reserved>0?'+':''}{reserved} · Резерв після: {after.reserved_quantity}</p>}
    {row.type==='transfer'&&<p>Місце: {before.location||'Не вказано'} → {after.location||'Не вказано'}</p>}
    {row.type==='sale'&&<p>Ціна у картці на момент операції: {price==null?'Не зафіксовано':currency?money(price,currency):`${price} · валюту не зафіксовано`}</p>}
    <small>Користувач: {me&&me.id===row.actor_id?me.name:'Не визначено'}</small>{row.reason&&<p>{row.reason}</p>}
   </article>;
  })}
  {current&&!loading&&!data.items.length&&<Empty title="Операцій не знайдено">Змініть фільтри або період.</Empty>}
  {current&&<Pager total={data.total} page={page} setPage={setPage}/>}
 </section>;
}
