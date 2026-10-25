import {WorkshopGate} from './WorkshopDialogs';
import {useState} from 'react';
import {all,api,money,when,type Page} from './api';
import {Pager,Empty} from './components';
import {Heading,State,useLoad} from './shared';
export default function SalesLedger(){return <WorkshopGate><SalesLedgerContent/></WorkshopGate>;}
function SalesLedgerContent(){
 const [q,setQ]=useState(''),[vehicle,setVehicle]=useState(''),[source,setSource]=useState(''),[from,setFrom]=useState(''),[to,setTo]=useState(''),[page,setPage]=useState(0);
 const vehicles=useLoad(()=>Promise.all([all('/vehicles'),all('/vehicles?archived=true')]).then(v=>v.flat()),[]);
 const params=new URLSearchParams({q,limit:'50',offset:String(page*50)});if(vehicle)params.set('vehicle_id',vehicle);if(source)params.set('source',source);if(from)params.set('date_from',new Date(from+'T00:00:00').toISOString());if(to)params.set('date_to',new Date(to+'T23:59:59.999').toISOString());
 const key=params.toString(),{data,error,loading}=useLoad(()=>api<Page>('/sales?'+params).then(r=>({...r,key})),[key]);
 function change(set:(s:string)=>void,value:string){set(value);setPage(0);}
 return <><Heading eyebrow="МАЙСТЕРНЯ" title="Продажі" description="Фактичні списання через швидкий продаж і замовлення."/><div className="stock-history-filters">
 <label>Назва / артикул<input aria-label="Пошук продажів" value={q} onChange={e=>change(setQ,e.target.value)}/></label>
 <label>Автомобіль<select aria-label="Автомобіль продажів" value={vehicle} onChange={e=>change(setVehicle,e.target.value)}><option value="">Усі автомобілі</option>{vehicles.data?.map(v=><option key={v.id} value={v.id}>{v.manufacturer} {v.model} · №{v.number}</option>)}</select></label>
 <label>Джерело<select aria-label="Джерело продажів" value={source} onChange={e=>change(setSource,e.target.value)}><option value="">Усі продажі</option><option value="quick">Швидкий продаж</option><option value="order">Замовлення</option></select></label>
 <label>Від<input type="date" aria-label="Продажі від" value={from} onChange={e=>change(setFrom,e.target.value)}/></label><label>До<input type="date" aria-label="Продажі до" min={from||undefined} value={to} onChange={e=>change(setTo,e.target.value)}/></label></div>
 <State error={error||vehicles.error} loading={loading}/>{data?.key===key&&<section className="sales-ledger" aria-label="Фактичні продажі">{data.items.map(s=><article className="panel padded" key={s.id}><header><strong>{s.name}</strong><time>{when(s.created_at)}</time></header><small>{s.donor?`${s.donor.manufacturer} ${s.donor.model} · ${s.donor.year}`:'Без автомобіля'}{s.donor_is_current?' · поточні дані автомобіля':''}</small><p>{s.quantity} шт. · {s.price_recorded?`${money(s.unit_price,s.currency)} / шт. · Разом ${money(s.total,s.currency)}`:'Фактичну ціну не зафіксовано'}</p><small>{s.source==='order'?'Замовлення':'Швидкий продаж'} · Покупець: {s.buyer_name||'Не зазначено'} · Працівник: {s.actor_name||'Не зафіксовано'}</small>{s.note&&<p>{s.note}</p>}</article>)}{!loading&&!data.items.length&&<Empty title="Продажів не знайдено">Змініть фільтри або період.</Empty>}<Pager total={data.total} page={page} setPage={setPage}/></section>}<p className="muted">Скасування продажу з поверненням залишку поки недоступне. Не додавайте кількість вручну як заміну скасуванню.</p></>;
}
