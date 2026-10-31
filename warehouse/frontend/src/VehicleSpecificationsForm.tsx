import {useEffect,useState,type FormEvent} from 'react';
import {Cog,Fuel,Save,Wrench} from 'lucide-react';
import {api,type Row} from './api';
import {useCan} from './permissions';

const fuels=['Дизель','Бензин','Гібрид','Електро','Газ'];
const variants=['D3','D4','D5','T4','T5','T6','B4','B5','T8'];
const gearboxes=['Механіка','Автомат','Варіатор','Робот'];
const gearboxPrecise=['6-ступ. автомат','8-ступ. автомат','6-ступ. механіка','7-ступ. робот'];
const drives=[['','Не уточнено'],['FWD','Передній (FWD)'],['RWD','Задній (RWD)'],['AWD','Повний (AWD)'],['4WD','Повний (4WD)']];
const prepare=(v:Row)=>({fuel_type:String(v.fuel_type||''),engine_displacement_l:String(v.engine_displacement_l||''),engine_variant:String(v.engine_variant||''),engine_code:String(v.engine_code||''),transmission:String(v.transmission||''),drive_type:String(v.drive_type||'')});
export default function VehicleSpecificationsForm({vehicle,onSaved}:{vehicle:Row;onSaved:(v:Row)=>void}){
 const can=useCan(),editable=can('vehicles.edit')&&!vehicle.archived;
 const [form,setForm]=useState(()=>prepare(vehicle)),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>setForm(prepare(vehicle)),[vehicle.id,vehicle.fuel_type,vehicle.engine_displacement_l,vehicle.engine_variant,vehicle.engine_code,vehicle.transmission,vehicle.drive_type]);
 const change=(key:keyof ReturnType<typeof prepare>,value:string)=>setForm(v=>({...v,[key]:value}));
 async function submit(e:FormEvent){e.preventDefault();if(!editable||busy)return;setBusy(true);setError('');setMessage('');
  try{const payload={
   fuel_type:form.fuel_type,
   engine_displacement_l:form.engine_displacement_l?Number(form.engine_displacement_l):null,
   engine_variant:form.engine_variant.trim()||null,
   engine_code:form.engine_code.trim().toUpperCase()||null,
   transmission:form.transmission.trim(),
   drive_type:form.drive_type||null
  };
  const row=await api<Row>('/vehicles/'+vehicle.id+'/specifications','PATCH',payload);
  onSaved(row);setMessage('Характеристики збережено');
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <form onSubmit={submit} className="r1144-panel r1144-specifications">
  <h2><Wrench size={19}/> Двигун</h2>
  <fieldset className="r1144-fieldset"><legend>Тип палива</legend><div className="r1144-choices">{fuels.map(f=><label className={form.fuel_type===f?'selected':''} key={f}><input type="radio" name={'fuel-'+vehicle.id} disabled={!editable} checked={form.fuel_type===f} onChange={()=>change('fuel_type',f)}/><Fuel size={14}/>{f}</label>)}</div></fieldset>
  <div className="r1144-grid r1144-engine-fields">
   <label>Об'єм двигуна, л<input list={'volume-'+vehicle.id} type="number" min="0.1" max="12" step="0.1" disabled={!editable} value={form.engine_displacement_l} onChange={e=>change('engine_displacement_l',e.target.value)} placeholder="Наприклад, 2.0"/><datalist id={'volume-'+vehicle.id}>{['1.5','1.6','2.0','2.4','2.5','3.0','3.2'].map(v=><option key={v} value={v}/>)}</datalist></label>
   <label>Модифікація<input list={'variant-'+vehicle.id} maxLength={50} disabled={!editable} value={form.engine_variant} onChange={e=>change('engine_variant',e.target.value)} placeholder="D4, D5, T5…"/><datalist id={'variant-'+vehicle.id}>{variants.map(v=><option key={v} value={v}/>)}</datalist></label>
   <label className="r1144-wide">Код двигуна<input maxLength={80} disabled={!editable} value={form.engine_code} onChange={e=>change('engine_code',e.target.value)} placeholder="Укажіть код із маркування, якщо відомий"/></label>
  </div>
  <div className="r1144-gearbox"><h2><Cog size={19}/> Коробка передач</h2>
   <fieldset className="r1144-fieldset"><legend>Тип КПП</legend><div className="r1144-choices">{gearboxes.map(t=><label className={form.transmission===t?'selected':''} key={t}><input type="radio" name={'gearbox-'+vehicle.id} disabled={!editable} checked={form.transmission===t} onChange={()=>change('transmission',t)}/>{t}</label>)}</div></fieldset>
   <div className="r1144-grid">
    <label className="r1144-wide">Точне позначення КПП<input list={'gear-'+vehicle.id} disabled={!editable} maxLength={50} value={form.transmission} onChange={e=>change('transmission',e.target.value)} placeholder="Наприклад, 8-ступ. автомат"/><datalist id={'gear-'+vehicle.id}>{[...gearboxes,...gearboxPrecise].map(v=><option key={v} value={v}/>)}</datalist></label>
    <label className="r1144-wide">Привід<select disabled={!editable} value={form.drive_type} onChange={e=>change('drive_type',e.target.value)}>{drives.map(([v,l])=><option value={v} key={v}>{l}</option>)}</select></label>
   </div>
  </div>
  <p className="r1144-help">Позначення D5/T5/B5 не визначає об'єм двигуна. Вибирайте характеристики за документами або маркуванням конкретного автомобіля.</p>
  <div className="r1144-form-actions">{editable&&<button type="submit" className="primary" disabled={busy}><Save size={15}/>{busy?'Збереження…':'Зберегти характеристики'}</button>}</div>
  {error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status" className="r1144-success">{message}</p>}
 </form>;
}
