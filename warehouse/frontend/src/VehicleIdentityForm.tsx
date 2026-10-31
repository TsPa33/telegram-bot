import {useEffect,useState,type FormEvent} from 'react';
import {CarFront,Save} from 'lucide-react';
import {api,type Row} from './api';
import {useCan} from './permissions';

const prepare=(v:Row)=>({manufacturer:String(v.manufacturer||''),model:String(v.model||''),generation:String(v.generation||''),year:String(v.year||''),status:String(v.status||'dismantling'),vin:String(v.vin||''),notes:String(v.notes||'')});
export default function VehicleIdentityForm({vehicle,onSaved,onArchive}:{vehicle:Row;onSaved:(v:Row)=>void;onArchive:()=>void}){
 const can=useCan(),editable=can('vehicles.edit')&&!vehicle.archived;
 const [form,setForm]=useState(()=>prepare(vehicle)),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>setForm(prepare(vehicle)),[vehicle.id,vehicle.manufacturer,vehicle.model,vehicle.generation,vehicle.year,vehicle.status,vehicle.vin,vehicle.notes]);
 const change=(key:keyof ReturnType<typeof prepare>,value:string)=>setForm(f=>({...f,[key]:value}));
 async function submit(e:FormEvent){e.preventDefault();if(!editable||busy)return;setBusy(true);setError('');setMessage('');
  try{const body={
   manufacturer:form.manufacturer.trim(),model:form.model.trim(),generation:form.generation.trim(),year:Number(form.year),status:form.status,
   vin:form.vin.trim().toUpperCase()||null,notes:form.notes,donor_id:vehicle.donor_id,
   engine:vehicle.engine||'',fuel_type:vehicle.fuel_type||'',transmission:vehicle.transmission||'',
   acquisition_date:vehicle.acquisition_date||null
  };
  const result=await api<Row>('/vehicles/'+vehicle.id,'PUT',body);onSaved(result);setMessage('Дані автомобіля збережено');
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <form onSubmit={submit} className="r1144-panel r1144-identity"><h2><CarFront size={19}/> Дані автомобіля</h2>
  <div className="r1144-grid">
   <label>Номер донора<input readOnly value={'№ '+(vehicle.number??'—')} title="Номер присвоюється системою"/><small>Системний номер</small></label>
   <label>Статус<select value={form.status} disabled={!editable} onChange={e=>change('status',e.target.value)}><option value="planned">Заплановано</option><option value="dismantling">На розборі</option><option value="completed">Завершено</option></select></label>
   <label>Марка *<input required maxLength={100} disabled={!editable} value={form.manufacturer} onChange={e=>change('manufacturer',e.target.value)}/></label>
   <label>Модель *<input required maxLength={100} disabled={!editable} value={form.model} onChange={e=>change('model',e.target.value)}/></label>
   <label>Покоління<input maxLength={100} disabled={!editable} value={form.generation} placeholder="Не уточнено" onChange={e=>change('generation',e.target.value)}/></label>
   <label>Рік *<input type="number" required min={1886} max={2100} disabled={!editable} value={form.year} onChange={e=>change('year',e.target.value)}/></label>
   <label className="r1144-wide">VIN<input maxLength={17} minLength={17} pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{17}" disabled={!editable} value={form.vin} placeholder="17 символів, якщо відомий" onChange={e=>change('vin',e.target.value.toUpperCase())}/></label>
   <label className="r1144-wide">Примітки<textarea rows={3} maxLength={10000} disabled={!editable} value={form.notes} placeholder="Додаткова інформація про донора" onChange={e=>change('notes',e.target.value)}/></label>
  </div>
  <div className="r1144-form-actions">{editable&&<button className="primary" type="submit" disabled={busy}><Save size={15}/>{busy?'Збереження…':'Зберегти дані'}</button>}{can('inventory.archive')&&!vehicle.archived&&<button type="button" className="secondary" onClick={onArchive}>Архівувати авто</button>}</div>
  {error&&<p className="error" role="alert">{error}</p>}{message&&<p className="r1144-success" role="status">{message}</p>}
 </form>;
}
