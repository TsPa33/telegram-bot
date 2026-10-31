import {useState} from 'react';
import {Cog, Fuel, Wrench} from 'lucide-react';
import {api, type Row} from './api';
import {useCan} from './permissions';

const engineOptions=['2.0 дизель','2.0 бензин','2.4 дизель','T5','T6','B4','B5','D4','D5','Гібрид','Електро'];
const gearboxOptions=['Автомат','Механіка','Робот','Варіатор','8-ступ. автомат','6-ступ. автомат'];
type Field='engine'|'transmission';
export default function VehicleQuickPowertrain({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const can=useCan();
 const [pending,setPending]=useState<Field|null>(null);
 const [custom,setCustom]=useState<Field|null>(null);
 const [customValue,setCustomValue]=useState('');
 const [error,setError]=useState('');
 const editable=can('vehicles.edit')&&!vehicle.archived;
 async function save(field:Field,value:string){
  if(pending)return;
  setPending(field);setError('');
  try{const result=await api<Row>(`/vehicles/${vehicle.id}/powertrain`,'PATCH',{[field]:value});onSaved(result);setCustom(null);setCustomValue('');}
  catch(e){setError((e as Error).message);}
  finally{setPending(null);}
 }
 function control(field:Field,options:string[],label:string){
  const selected=String(vehicle[field]||'');
  const values=selected&&!options.includes(selected)?[selected,...options]:options;
  return <label className="r1143-powertrain-field" key={field}>
   <span className="r1143-field-name">{field==='engine'?<Wrench size={16}/>:<Cog size={16}/>} {label}</span>
   <select aria-label={label+' — '+vehicle.manufacturer+' '+vehicle.model} value={custom===field?'__custom__':selected} disabled={!editable||pending!==null} onChange={e=>{const v=e.target.value;if(v==='__custom__'){setCustom(field);setCustomValue(selected);return;}setCustom(null);void save(field,v);}}>
    <option value="">Не вказано</option>
    {values.map(value=><option key={value} value={value}>{value}</option>)}
    <option value="__custom__">Інший варіант…</option>
   </select>
   {pending===field&&<small role="status">Збереження…</small>}
  </label>;
 }
 return <div className="r1143-powertrain">
  <div className="r1143-powertrain-fields">
   {control('engine',engineOptions,'Двигун')}
   {control('transmission',gearboxOptions,'КПП')}
  </div>
  {custom&&<form className="r1143-custom" onSubmit={e=>{e.preventDefault();void save(custom,customValue.trim());}}>
   <label>Власне значення — {custom==='engine'?'двигун':'КПП'}<input value={customValue} onChange={e=>setCustomValue(e.target.value)} maxLength={custom==='engine'?100:50} autoFocus placeholder="Введіть точне значення"/></label>
   <button type="submit" disabled={!customValue.trim()||pending!==null}>Зберегти</button>
   <button type="button" onClick={()=>setCustom(null)}>Скасувати</button>
  </form>}
  {error&&<p className="r1143-error" role="alert">{error}</p>}
 </div>;
}
