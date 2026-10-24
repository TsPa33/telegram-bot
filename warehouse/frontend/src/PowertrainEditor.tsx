import { useState } from "react";
import { api, type Row } from "./api";
import { Modal, RecordForm } from "./components";

// No verified fitment dictionary is installed. Accept the owner's actual value;
// never infer an engine or transmission from a model name.
export default function PowertrainEditor({vehicle,onSaved,compact=false}:{vehicle:Row;onSaved:(row:Row)=>void;compact?:boolean}) {
  const [field,setField]=useState<'engine'|'transmission'|null>(null);
  return <>
    <div className={`vehicle-powertrain ${compact?'vehicle-powertrain-compact':''}`}>
      <button disabled={vehicle.archived} aria-label={`Двигун ${vehicle.manufacturer} ${vehicle.model}`} onClick={()=>setField('engine')}><small>Двигун</small>{vehicle.engine||(compact?'Не вказано':'Вибрати двигун')}</button>
      <button disabled={vehicle.archived} aria-label={`КПП ${vehicle.manufacturer} ${vehicle.model}`} onClick={()=>setField('transmission')}><small>КПП</small>{vehicle.transmission||(compact?'Не вказано':'Вибрати КПП')}</button>
    </div>
    {field&&<Modal title={field==='engine'?'Двигун автомобіля':'КПП автомобіля'} onClose={()=>setField(null)}>
      <RecordForm initial={vehicle} fields={[{key:field,label:field==='engine'?'Двигун':'КПП'}]} onSave={async values=>{
        const row=await api(`/vehicles/${vehicle.id}/powertrain`,'PATCH',values);
        onSaved(row);setField(null);
      }}/>
    </Modal>}
  </>;
}
