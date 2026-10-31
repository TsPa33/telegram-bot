import {useEffect,useState,type FormEvent} from 'react';
import {CalendarDays,Coins,Save} from 'lucide-react';
import {api,money,type Row} from './api';
import {useCan} from './permissions';
export default function VehicleFinance({vehicle,analytics,onSaved}:{vehicle:Row;analytics:Row|null;onSaved:(row:Row)=>void}){
 const can=useCan(),seeCost=can('parts.view_cost'),editable=seeCost&&can('vehicles.edit')&&!vehicle.archived;
 const [date,setDate]=useState(String(vehicle.acquisition_date||'')),[cost,setCost]=useState(vehicle.acquisition_cost==null?'':String(vehicle.acquisition_cost));
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[ok,setOk]=useState('');
 useEffect(()=>{setDate(String(vehicle.acquisition_date||''));setCost(vehicle.acquisition_cost==null?'':String(vehicle.acquisition_cost));},[vehicle.id,vehicle.acquisition_date,vehicle.acquisition_cost]);
 async function save(e:FormEvent){e.preventDefault();if(!editable||busy)return;setBusy(true);setError('');setOk('');
 try{const row=await api<Row>('/vehicles/'+vehicle.id,'PUT',{
 manufacturer:vehicle.manufacturer,model:vehicle.model,year:vehicle.year,generation:vehicle.generation||'',
 engine:vehicle.engine||'',fuel_type:vehicle.fuel_type||'',transmission:vehicle.transmission||'',
 vin:vehicle.vin||null,donor_id:vehicle.donor_id,notes:vehicle.notes||'',status:vehicle.status,
 acquisition_date:date||null,acquisition_cost:cost===''?null:Number(cost)
 });onSaved(row);setOk('Дані придбання збережено');
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className="r1144-finance r1144-panel"><h2><Coins size={20}/> Економіка автомобіля</h2>
  <div className="r1144-finance-kpis">
   <div><small>Позицій</small><strong>{analytics?.positions??'—'}</strong></div>
   <div><small>Одиниць</small><strong>{analytics?.stock_units??'—'}</strong></div>
   {can('analytics.financial')&&<div><small>Оцінка майбутніх продажів</small><strong>{analytics?.estimated_sales_value==null?'Немає оцінки':money(analytics.estimated_sales_value)}</strong></div>}
   {seeCost&&<div><small>Вартість придбання</small><strong>{vehicle.acquisition_cost==null?'Не вказано':money(vehicle.acquisition_cost)}</strong></div>}
  </div>
  <form onSubmit={save} className="r1144-finance-form">
   <label><CalendarDays size={15}/> Дата придбання<input type="date" disabled={!editable} value={date} onChange={e=>setDate(e.target.value)}/></label>
   {seeCost&&<label>Вартість придбання, грн<input type="number" min="0" step="0.01" disabled={!editable} value={cost} onChange={e=>setCost(e.target.value)} placeholder="Не вказано"/></label>}
   {editable&&<button type="submit" className="primary" disabled={busy}><Save size={15}/>{busy?'Збереження…':'Зберегти придбання'}</button>}
  </form>
  <p className="r1144-help">Оцінка потенційної виручки не є фактичним прибутком. Відображено лише дані, доступні за вашими правами.</p>
  {error&&<p role="alert" className="error">{error}</p>}{ok&&<p role="status" className="r1144-success">{ok}</p>}
 </section>;
}
