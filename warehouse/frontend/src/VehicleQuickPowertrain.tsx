import {useState, type FormEvent} from 'react';
import {Cog, Fuel, Gauge, Wrench, GitFork, AlertCircle} from 'lucide-react';
import {api, type Row} from './api';
import {useCan} from './permissions';

type SpecKey = 'engine_displacement_l'|'fuel_type'|'engine_variant'|'transmission'|'drive_type';
const volumes = ['1.0','1.2','1.4','1.5','1.6','1.8','2.0','2.2','2.4','2.5','3.0','3.2','3.5','4.0'];
const fuels = ['Бензин','Дизель','Газ','Газ / бензин','Гібрид','Plug-in hybrid','Електро'];
// Suggestions only: a manufacturer's trim code does NOT determine fuel or displacement.
const versions = ['D3','D4','D5','T4','T5','T6','B4','B5','T8'];
const gearboxes = ['Механіка','Автомат','Робот','Варіатор','5-ступ. механіка','6-ступ. механіка','6-ступ. автомат','7-ступ. робот','8-ступ. автомат','9-ступ. автомат'];
const drives = [
 {value:'FWD',label:'Передній (FWD)'},
 {value:'RWD',label:'Задній (RWD)'},
 {value:'AWD',label:'Повний (AWD)'},
 {value:'4WD',label:'Повний (4WD)'}
];
type SelectOption={value:string;label:string};
export function legacyEngineSuggestion(engine:unknown):{volume:string;fuel:string}|null{
 const match=/^\s*(\d{1,2}(?:[.,]\d)?)\s*(?:л\s*)?(дизель|бензин|газ)\s*$/iu.exec(String(engine||''));
 if(!match)return null;
 const volume=Number(match[1].replace(',','.'));
 if(!Number.isFinite(volume)||volume<=0||volume>12)return null;
 const fuel=match[2].toLowerCase()==='дизель'?'Дизель':match[2].toLowerCase()==='бензин'?'Бензин':'Газ';
 return {volume:volume.toFixed(1),fuel};
}
function options(values:SelectOption[],selected:string):SelectOption[]{
 return selected&&!values.some(x=>x.value===selected)?[{value:selected,label:selected},...values]:values;
}
export default function VehicleQuickPowertrain({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}){
 const can=useCan();
 const editable=can('vehicles.edit')&&!vehicle.archived;
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [custom,setCustom]=useState<SpecKey|null>(null),[customValue,setCustomValue]=useState('');
 const suggested=legacyEngineSuggestion(vehicle.engine);
 const pendingLegacy=!!suggested&&(!vehicle.engine_displacement_l||!vehicle.fuel_type);
 const volume=String(vehicle.engine_displacement_l||suggested?.volume||'');
 const fuel=String(vehicle.fuel_type||suggested?.fuel||'');
 async function save(patch:Partial<Record<SpecKey,string|number|null>>){
  if(!editable||busy)return;
  setBusy(true);setError('');setNotice('');
  try{
   const updated=await api<Row>('/vehicles/'+encodeURIComponent(vehicle.id)+'/specifications','PATCH',patch);
   onSaved(updated);setCustom(null);setCustomValue('');setNotice('Збережено');
  }catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 function select(field:SpecKey,label:string,value:string,items:SelectOption[],Icon:typeof Gauge,withCustom=false){
  const current=options(items,value);
  const manual=custom===field;
  return <label className="r1146-spec" key={field}>
   <span className="r1146-spec-label"><Icon size={15} aria-hidden="true"/>{label}</span>
   <select aria-label={label+' — '+vehicle.manufacturer+' '+vehicle.model+' №'+(vehicle.number??'')} value={manual?'__custom__':value}
     disabled={!editable||busy}
     onChange={e=>{
      const choice=e.target.value;
      if(choice==='__custom__'){setCustom(field);setCustomValue(value);return}
      setCustom(null);
      void save({[field]:field==='engine_displacement_l'?(choice?Number(choice):null):choice||null});
     }}>
    <option value="">Не вказано</option>
    {current.map(x=><option value={x.value} key={x.value}>{x.label}</option>)}
    {withCustom&&<option value="__custom__">Інший варіант…</option>}
   </select>
  </label>;
 }
 function saveCustom(e:FormEvent){
  e.preventDefault();
  if(!custom)return;
  const value=customValue.trim();
  if(custom==='engine_displacement_l'){
   const parsed=Number(value.replace(',','.'));
   if(!Number.isFinite(parsed)||parsed<0.1||parsed>12||!/^\d{1,2}(?:[.,]\d)?$/.test(value)){setError('Укажіть об’єм від 0,1 до 12,0 л з одним знаком після коми.');return}
   void save({engine_displacement_l:parsed});return;
  }
  if(!value||value.length>(custom==='engine_variant'?50:50)){setError('Укажіть значення до 50 символів.');return}
  void save({[custom]:value});
 }
 return <div className="r1146-spec-editor">
  <div className="r1146-spec-row r1146-engine-row">
   {select('engine_displacement_l',"Об'єм",volume,volumes.map(v=>({value:v,label:v+' л'})),Gauge,true)}
   {select('fuel_type','Паливо',fuel,fuels.map(v=>({value:v,label:v})),Fuel,true)}
   {select('engine_variant','Серія',String(vehicle.engine_variant||''),versions.map(v=>({value:v,label:v})),Wrench,true)}
  </div>
  <div className="r1146-spec-row r1146-drive-row">
   {select('transmission','КПП',String(vehicle.transmission||''),gearboxes.map(v=>({value:v,label:v})),Cog,true)}
   {select('drive_type','Привід',String(vehicle.drive_type||''),drives,GitFork)}
  </div>
  {pendingLegacy&&editable&&<div className="r1146-legacy" role="note">
   <span>Зі старого поля «{String(vehicle.engine)}» — перевірте й підтвердьте.</span>
   <button type="button" disabled={busy} onClick={()=>{const patch:Partial<Record<SpecKey,string|number|null>>={};if(!vehicle.engine_displacement_l)patch.engine_displacement_l=Number(suggested?.volume);if(!vehicle.fuel_type)patch.fuel_type=suggested?.fuel||'';void save(patch)}}>Підтвердити</button>
  </div>}
  {custom&&editable&&<form className="r1146-custom" onSubmit={saveCustom}>
   <label>{custom==='engine_displacement_l'?"Інший об’єм (л)":custom==='engine_variant'?'Модифікація':custom==='fuel_type'?'Тип палива':'Тип КПП'}
    <input autoFocus maxLength={50} value={customValue} onChange={e=>setCustomValue(e.target.value)} placeholder={custom==='engine_displacement_l'?'Наприклад, 2.3':'Введіть точне значення'}/></label>
   <button type="submit" disabled={busy||!customValue.trim()}>Зберегти</button>
   <button type="button" onClick={()=>{setCustom(null);setError('')}}>Скасувати</button>
  </form>}
  {busy&&<small className="r1146-feedback" role="status">Збереження…</small>}
  {notice&&!busy&&<small className="r1146-feedback" role="status">{notice}</small>}
  {error&&<p className="r1146-error" role="alert"><AlertCircle size={14}/>{error}</p>}
 </div>;
}
