import {useEffect,useState} from 'react';
import {api,type Row} from './api';
import SearchSelect from './SearchSelect';
type Variant={id:string;modification:string;year_from:number|null;year_to:number|null;year_verified:boolean;displacement_l:string|null;fuel_type:string|null;power_kw:number|null;power_ps:number|null;drive_type:string|null;engine_codes:string[]};
export default function VehicleDirectoryPicker({brand,model,year,onPick}:{brand:string;model:string;year:string;onPick:(row:Row|null)=>void}){
 const [list,setList]=useState<Variant[]>([]),[selected,setSelected]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{
  if(!brand||!model||!/^\d{4}$/.test(year)){setList([]);setSelected('');onPick(null);return;}
  let active=true;setBusy(true);setError('');setSelected('');onPick(null);
  api<Variant[]>(`/vehicle-directory/variants?brand=${encodeURIComponent(brand)}&model=${encodeURIComponent(model)}&year=${encodeURIComponent(year)}`)
   .then(rows=>{if(active)setList(rows)})
   .catch(e=>{if(active){setError((e as Error).message);setList([])}})
   .finally(()=>{if(active)setBusy(false)});
  return()=>{active=false};
 },[brand,model,year]);
 const chosen=list.find(v=>v.id===selected);
 return <div className="r12-picker">
  <SearchSelect label="Модифікація двигуна (необов'язково)" value={selected} disabled={!brand||!model||!year||busy} options={list.map(x=>({
   value:x.id,label:`${x.modification} · ${x.displacement_l||'—'} л · ${x.fuel_type||'паливо ?'} · ${x.power_ps||'—'} к.с.${x.year_verified?'':' · рік не підтверджено'}`
  }))} onChange={id=>{setSelected(id);const choice=list.find(x=>x.id===id);onPick(choice ? (choice as unknown as Row) : null)}}/>
  {busy&&<small role="status">Пошук модифікацій…</small>}
  {!busy&&!error&&!list.length&&<small>У довіднику немає підтвердженої модифікації для цього вибору. Можна додати авто вручну.</small>}
  {chosen&&<small className="r12-variant-note">{chosen.year_verified?'Запис довідника відповідає зазначеному діапазону років.':'Кінець виробництва в джерелі не вказаний. Уточніть комплектацію донора.'} Код двигуна: {chosen.engine_codes.length===1?chosen.engine_codes[0]:'потребує перевірки'}.</small>}
  {error&&<small role="status">Довідник модифікацій недоступний; ручне додавання працює.</small>}
 </div>
}
