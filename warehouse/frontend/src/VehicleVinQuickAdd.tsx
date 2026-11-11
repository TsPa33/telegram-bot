import {useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {Permit} from './permissions';

type Result={vin:string;source:string;vehicle:Row;available_fields:string[];field_sources?:Row;message:string;observed_at?:string;conflicts?:Row;consistency_issues?:Row};
const groups:[string,[string,string][]][]=[
 ['Автомобіль',[['manufacturer','Марка'],['model','Модель'],['generation','Покоління'],['year','Рік'],['trim','Модифікація / комплектація'],['series','Серія']]],
 ['Двигун',[['engine','Двигун'],['engine_code','Код двигуна'],['engine_displacement_l','Об’єм двигуна, л'],['engine_power_kw','Потужність, кВт'],['engine_power_hp','Потужність, к.с.'],['engine_cylinders','Циліндри'],['fuel_type','Паливо']]],
 ['Трансмісія',[['transmission','КПП'],['transmission_code','Код КПП'],['drive_type','Привід']]],
 ['Кузов і ринок',[['body_class','Тип кузова'],['doors','Кількість дверей'],['plant_country','Країна заводу'],['plant_city','Місто заводу'],['market','Ринок / регіон'],['vehicle_type','Тип автомобіля']]]
];
export default function VehicleVinQuickAdd({onBack,onCreated}:{onBack:()=>void;onCreated:(row:Row)=>void}){
 const [vin,setVin]=useState(''),[result,setResult]=useState<Result|null>(null),[draft,setDraft]=useState<Row>({});
 const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[existing,setExisting]=useState<Row|null>(null);
 const epoch=useRef(0),writing=useRef(false);
 const valid=/^[A-HJ-NPR-Z0-9]{17}$/.test(vin.trim().toUpperCase());
 function manual(){epoch.current++;setLoading(false);setConfirmed(false);setError('');setResult({vin:valid?vin:'',source:'manual',vehicle:{},available_fields:[],message:'Заповніть відомі характеристики вручну.'});setDraft({});}
 async function decode(){
  if(!valid||loading)return;const ticket=++epoch.current;setLoading(true);setError('');setResult(null);setDraft({});setConfirmed(false);setExisting(null);
  try {const r=await api<Result>('/vehicles/vin/decode?vin='+encodeURIComponent(vin));if(ticket===epoch.current){setResult(r);setDraft({...r.vehicle,year:String(r.vehicle.year||'')});}}
  catch(e){if(ticket===epoch.current){setError((e as Error).message);setResult({vin,source:'unavailable',vehicle:{},available_fields:[],message:'Декодер недоступний. Заповніть дані вручну.'});}}
  finally{if(ticket===epoch.current)setLoading(false);}
 }
 async function create(){
  if(!result||writing.current||!confirmed)return;
  if((vin&&!valid)||!String(draft.manufacturer||'').trim()||!String(draft.model||'').trim()||!/^\d{4}$/.test(String(draft.year||''))){setError('Перевірте VIN, марку, модель і рік.');return;}
  const values:Row={manufacturer:draft.manufacturer,model:draft.model,generation:draft.generation||'',year:Number(draft.year),status:'planned'};
  if(valid)values.vin=vin;
  for(const field of ['engine','engine_code','fuel_type','transmission'])if(draft[field])values[field]=draft[field];
  if(draft.drive_type){const code=String(draft.drive_type).toUpperCase().match(/\b(FWD|RWD|AWD|4WD)\b/)?.[1];if(!code){setError('Уточніть привід: FWD, RWD, AWD або 4WD.');return;}values.drive_type=code;}
  if(draft.engine_displacement_l){const d=Number(String(draft.engine_displacement_l).replace(',','.'));if(!Number.isFinite(d)||d<=0||d>12){setError('Об’єм двигуна має бути більше 0 та не більше 12 л.');return;}values.engine_displacement_l=Math.round(d*10)/10;}
  values.vin_details={characteristics:draft,decoded:result.vehicle,field_sources:result.field_sources||{},conflicts:result.conflicts||{},source:result.source,observed_at:result.observed_at||''};
  writing.current=true;setSaving(true);setError('');
  try{onCreated(await api('/vehicles','POST',values));}
  catch(e){setError((e as Error).message);if(e instanceof ApiError&&e.status===409&&valid){try{const found=await api('/vehicles?q='+encodeURIComponent(vin));setExisting(found.items.find((r:Row)=>r.vin===vin)||null);}catch{/* Existing VIN remains blocked even if listing is unavailable. */}}}
  finally{writing.current=false;setSaving(false);}
 }
 return <section className="panel padded" aria-label="Додавання автомобіля за VIN">
  <button type="button" onClick={onBack} disabled={saving}>Автомобілі</button>
  <h2>1. Визначити автомобіль за VIN</h2>
  <label>VIN (17 символів)<input aria-label="VIN" value={vin} maxLength={17} spellCheck={false} disabled={saving} onChange={e=>{epoch.current++;setVin(e.target.value.trim().toUpperCase());setResult(null);setDraft({});setLoading(false);setConfirmed(false);setError('');setExisting(null);}} placeholder="YV4L12RK6N1970668"/></label>
  {vin&&!valid&&<p role="status">Введіть 17 символів без I, O, Q.</p>}
  <button type="button" disabled={!valid||loading||saving} onClick={()=>void decode()}>{loading?'Визначаємо…':'Визначити автомобіль'}</button>
  <button type="button" disabled={saving} onClick={manual}>Додати вручну</button>
  {error&&<p role="alert">{error}</p>}
  {existing&&<button onClick={()=>onCreated(existing)}>Відкрити наявний автомобіль</button>}
  {result&&<><h2>2. Перевірити характеристики</h2><p role="status">{result.message}</p>
   {Object.keys(result.conflicts||{}).length>0&&<p role="alert">Джерела мають розбіжності. Перевірте характеристики вручну.</p>}
   {Object.keys(result.consistency_issues||{}).length>0&&<p role="alert">{Object.values(result.consistency_issues||{}).join(' ')}</p>}
   {groups.map(([name,fields])=><fieldset key={name}><legend>{name}</legend><div className="form-grid">{fields.map(([key,label])=><label key={key}>{label}<input aria-label={label} disabled={saving} value={String(draft[key]??'')} onChange={e=>{setDraft(p=>({...p,[key]:e.target.value}));setConfirmed(false);}}/><small>{String(draft[key]??'')!==String(result.vehicle[key]??'')?'Введено / змінено вручну':result.available_fields.includes(key)?`Повідомлено джерелом: ${result.field_sources?.[key]||result.source}; перевірте`:'Не визначено · можна уточнити'}</small></label>)}</div></fieldset>)}
   <h2>3. Зберегти автомобіль</h2><p>Ці дані не є підтвердженням заводської комплектації або сумісності запчастин.</p>
   <label><input type="checkbox" checked={confirmed} disabled={saving} onChange={e=>setConfirmed(e.target.checked)}/>Характеристики перевірено, підтверджую додавання</label>
   <Permit permission="vehicles.create"><button className="primary" type="button" disabled={saving||!confirmed} onClick={()=>void create()}>{saving?'Зберігаємо…':'Додати автомобіль'}</button></Permit>
  </>}
 </section>;
}
