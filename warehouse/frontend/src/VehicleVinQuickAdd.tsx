import {useState} from 'react';
import {ArrowLeft, Search, CarFront, ShieldAlert} from 'lucide-react';
import {api, type Row} from './api';
import {Permit} from './permissions';

type Result={vin:string;source:string;vehicle:Row;available_fields:string[];requires_review:boolean;message:string;conflicts?:Record<string,{primary:string;secondary:string}>};
const fields:[string,string][]=[
 ['manufacturer','Марка'],['model','Модель'],['year','Модельний рік'],
 ['engine','Модель двигуна'],['engine_displacement_l','Об’єм двигуна, л'],
 ['fuel_type','Паливо'],['transmission','КПП'],['drive_type','Привід'],
 ['body_class','Кузов'],['trim','Комплектація'],
 ['engine_cylinders','Циліндри'],['engine_power_kw','Потужність, кВт'],
 ['plant_country','Країна заводу']
];
export default function VehicleVinQuickAdd({onBack,onCreated}:{onBack:()=>void;onCreated:(row:Row)=>void}){
 const [vin,setVin]=useState(''),[result,setResult]=useState<Result|null>(null),[draft,setDraft]=useState<Row>({});
 const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const valid=/^[A-HJ-NPR-Z0-9]{17}$/.test(vin.trim().toUpperCase());
 async function decode(){
  if(!valid||loading)return;
  setLoading(true);setError('');setResult(null);setDraft({});
  try{
   const r=await api<Result>('/vehicles/vin/decode?vin='+encodeURIComponent(vin.trim().toUpperCase()));
   setResult(r);setDraft({...r.vehicle,year:String(r.vehicle.year||'')});
  }catch(e){setError((e as Error).message);}
  finally{setLoading(false);}
 }
 async function create(){
  if(!result||saving)return;
  if(!String(draft.manufacturer||'').trim()||!String(draft.model||'').trim()||!/^\d{4}$/.test(String(draft.year||''))||Number(draft.year)<1886||Number(draft.year)>2100){
   setError('Заповніть марку, модель і коректний рік.');return;
  }
  setSaving(true);setError('');
  const values:Row={manufacturer:String(draft.manufacturer).trim(),model:String(draft.model).trim(),year:Number(draft.year),vin:result.vin,status:'planned'};
  if(draft.engine)values.engine=String(draft.engine);
  if(draft.fuel_type)values.fuel_type=String(draft.fuel_type);
  if(draft.transmission)values.transmission=String(draft.transmission);
  if(draft.drive_type)values.drive_type=String(draft.drive_type);
  if(draft.engine_displacement_l&&Number(draft.engine_displacement_l)>0)values.engine_displacement_l=Number(draft.engine_displacement_l);
  try{onCreated(await api('/vehicles','POST',values));}
  catch(e){setError((e as Error).message);}
  finally{setSaving(false);}
 }
 return <section className="panel padded" aria-label="Швидке додавання за VIN" style={{maxWidth:980,margin:'auto'}}>
  <button type="button" className="secondary" onClick={onBack}><ArrowLeft size={16}/> Автомобілі</button>
  <h1>Швидко додати автомобіль за VIN</h1>
  <p>Отримайте базові характеристики, перевірте їх і створіть картку. Розбір можна почати пізніше.</p>
  <div className="form-grid"><label>VIN-код (17 символів)
   <input value={vin} maxLength={17} autoCapitalize="characters" spellCheck={false} onChange={e=>{setVin(e.target.value.toUpperCase());setResult(null);setError('');}} placeholder="Наприклад, YV1MV8481D2036066" />
  </label><div style={{alignSelf:'end'}}><button type="button" disabled={!valid||loading} onClick={decode}><Search size={16}/> {loading?'Перевірка…':'Розшифрувати VIN'}</button></div></div>
  {error&&<p role="alert">{error}</p>}
  {result&&<><p role="status"><ShieldAlert size={15}/> {result.message} Джерело: {result.source}. Дані можуть бути неповними для європейських VIN.</p>
   {result.conflicts&&Object.keys(result.conflicts).length>0&&<p role="alert">Джерела VIN повернули суперечливі характеристики: {Object.entries(result.conflicts).map(([key,values])=>`${fields.find(f=>f[0]===key)?.[1]||key}: ${values.primary} / ${values.secondary}`).join("; ")}. Перевірте ці поля вручну перед створенням.</p>}
   <h2><CarFront size={19}/> Картка характеристик</h2>
   <div className="form-grid">{fields.map(([key,label])=><label key={key}>{label}
    <input value={String(draft[key]??'')} onChange={e=>setDraft(p=>({...p,[key]:e.target.value}))} aria-label={label}/>
    <small>{result.available_fields.includes(key)?'Дані VIN-сервісу · перевірте':'Не визначено · заповніть вручну'}</small>
   </label>)}</div>
   <p>Код двигуна, заводський код КПП і точна сумісність OEM не підтверджуються цим декодером.</p>
   <Permit permission="vehicles.create"><button type="button" disabled={saving} onClick={create}>{saving?'Створення…':'Створити картку автомобіля'}</button></Permit>
  </>}
 </section>;
}
