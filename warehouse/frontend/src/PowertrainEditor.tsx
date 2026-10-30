import {useCan} from './permissions';
import { useState } from "react";
import { api, type Row } from "./api";
import { Modal, RecordForm } from "./components";

// No verified fitment dictionary is installed. Accept the owner's actual value;
// never infer an engine or transmission from a model name.
export default function PowertrainEditor({vehicle,onSaved,compact=false,inline=false}:{vehicle:Row;onSaved:(row:Row)=>void;compact?:boolean;inline?:boolean}) {
 const can=useCan();
  const [field,setField]=useState<'engine'|'transmission'|null>(null);
  return <>
    <div className={`vehicle-powertrain ${compact?'vehicle-powertrain-compact':''}`}>
      {inline&&<span className="r1-fuel-type">Тип двигуна: {vehicle.fuel_type||'Не вказано'}</span>}
      <button disabled={!can('vehicles.edit')||vehicle.archived} aria-label={`Двигун ${vehicle.manufacturer} ${vehicle.model}`} onClick={()=>setField('engine')}><small>Двигун</small>{vehicle.engine||(compact?'Не вказано':'Вибрати двигун')}</button>
      <button disabled={!can('vehicles.edit')||vehicle.archived} aria-label={`КПП ${vehicle.manufacturer} ${vehicle.model}`} onClick={()=>setField('transmission')}><small>КПП</small>{vehicle.transmission||(compact?'Не вказано':'Вибрати КПП')}</button>
    </div>
    {field&&(inline?<div className="r1-powertrain-editor"><RecordForm initial={vehicle} fields={field==='engine'?[{key:'fuel_type',label:'Тип двигуна'},{key:'engine',label:'Код / опис двигуна'}]:[{key:'transmission',label:'Тип / код / опис КПП'}]} onSave={async values=>{const row=await api(`/vehicles/${vehicle.id}/powertrain`,'PATCH',values);onSaved(row);setField(null);}}/><button onClick={()=>setField(null)}>Закрити редактор двигуна / КПП</button></div>:<Modal title={field==='engine'?'Двигун автомобіля':'КПП автомобіля'} onClose={()=>setField(null)}><RecordForm initial={vehicle} fields={[{key:field,label:field==='engine'?'Двигун':'КПП'}]} onSave={async values=>{const row=await api(`/vehicles/${vehicle.id}/powertrain`,'PATCH',values);onSaved(row);setField(null);}}/></Modal>)}
  </>;
}
