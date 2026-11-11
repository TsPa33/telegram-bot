import {useContext,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {Permit,TeamIdentity} from './permissions';
import './vin-intake.css';

type Result={vin:string;source:string;vehicle:Row;available_fields:string[];field_sources?:Row;message:string;observed_at?:string;conflicts?:Row;consistency_issues?:Row;additional?:Row;counts?:Row;provider_status?:Row;diagnostics?:Row;cached?:boolean};
const groups:[string,[string,string][]][]=[
 ['Автомобіль',[['manufacturer','Марка'],['model','Модель'],['generation','Покоління'],['year','Рік'],['trim','Модифікація / комплектація'],['series','Серія'],['series_secondary','Додаткова серія'],['trim_secondary','Додаткова комплектація']]],
 ['Двигун',[['engine','Двигун'],['engine_code','Код двигуна'],['engine_displacement_l','Об’єм двигуна, л'],['engine_power_kw','Потужність, кВт'],['engine_power_hp','Потужність, к.с.'],['engine_cylinders','Циліндри'],['fuel_type','Паливо'],['fuel_secondary','Додаткове паливо'],['electrification','Силова установка'],['engine_manufacturer','Виробник двигуна'],['engine_configuration','Конфігурація двигуна'],['fuel_injection','Впорскування']]],
 ['Трансмісія',[['transmission','КПП'],['transmission_code','Код КПП'],['drive_type','Привід'],['transmission_speeds','Ступені КПП']]],
 ['Кузов',[['body_class','Тип кузова'],['doors','Кількість дверей']]],
 ['Додаткові характеристики',[['plant_country','Країна заводу'],['plant_city','Місто заводу'],['plant_company','Компанія заводу'],['market','Ринок / регіон'],['vehicle_type','Тип автомобіля']]]
];
export default function VehicleVinQuickAdd({onBack,onCreated}:{onBack:()=>void;onCreated:(row:Row)=>void}){
 const identity=useContext(TeamIdentity);
 const [extra,setExtra]=useState<Row>({});
 const [vin,setVin]=useState(''),[result,setResult]=useState<Result|null>(null),[draft,setDraft]=useState<Row>({});
 const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[existing,setExisting]=useState<Row|null>(null);
 const epoch=useRef(0),writing=useRef(false);
 const valid=/^[A-HJ-NPR-Z0-9]{17}$/.test(vin.trim().toUpperCase());
 function manual(){epoch.current++;setLoading(false);setConfirmed(false);setError('');setResult({vin:valid?vin:'',source:'manual',vehicle:{},available_fields:[],message:'Заповніть відомі характеристики вручну.'});setDraft({});setExtra({});}
 async function decode(){
  if(!valid||loading)return;const ticket=++epoch.current;setLoading(true);setError('');setResult(null);setDraft({});setConfirmed(false);setExisting(null);
  try {const r=await api<Result>('/vehicles/vin/decode?vin='+encodeURIComponent(vin));if(ticket===epoch.current){setResult(r);setDraft({...r.vehicle,year:String(r.vehicle.year||'')});setExtra(r.additional||{});}}
  catch(e){if(ticket===epoch.current){setError((e as Error).message);setResult({vin,source:'unavailable',vehicle:{},available_fields:[],message:'Декодер недоступний. Заповніть дані вручну.'});}}
  finally{if(ticket===epoch.current)setLoading(false);}
 }
 async function create(){
  if(!result||writing.current||!confirmed)return;
  if((vin&&!valid)||!String(draft.manufacturer||'').trim()||!String(draft.model||'').trim()||!/^\d{4}$/.test(String(draft.year||''))){setError('Перевірте VIN, марку, модель і рік.');return;}
  const values:Row={manufacturer:draft.manufacturer,model:draft.model,generation:draft.generation||'',year:Number(draft.year),status:'planned'};
  if(valid)values.vin=vin;
  for(const field of ['engine','engine_code','fuel_type','transmission'])if(draft[field])values[field]=draft[field];
  if(draft.drive_type)values.drive_type=draft.drive_type;
  if(draft.engine_displacement_l){const d=Number(String(draft.engine_displacement_l).replace(',','.'));if(!Number.isFinite(d)||d<=0||d>12){setError('Об’єм двигуна має бути більше 0 та не більше 12 л.');return;}values.engine_displacement_l=Math.round(d*10)/10;}
  values.vin_details={diagnostics:result.diagnostics||{},consistency_issues:result.consistency_issues||{},additional:extra,decoded_additional:result.additional||{},characteristics:draft,decoded:result.vehicle,field_sources:result.field_sources||{},conflicts:result.conflicts||{},source:result.source,observed_at:result.observed_at||''};
  writing.current=true;setSaving(true);setError('');
  try{onCreated(await api('/vehicles','POST',values));}
  catch(e){setError((e as Error).message);if(e instanceof ApiError&&e.status===409&&valid){try{const found=await api('/vehicles?q='+encodeURIComponent(vin));setExisting(found.items.find((r:Row)=>r.vin===vin)||null);}catch{/* Existing VIN remains blocked even if listing is unavailable. */}}}
  finally{writing.current=false;setSaving(false);}
 }
 const required=new Set(['manufacturer','model','year']);
 const has=(key:string)=>result?.vehicle[key]!==undefined&&result?.vehicle[key]!==null&&String(result?.vehicle[key]).trim()!=='';
 const unknown=groups.flatMap(([,fields])=>fields).filter(([key])=>!has(key)&&!required.has(key));
 function field(key:string,label:string){
  const modified=String(draft[key]??'')!==String(result?.vehicle[key]??'');
  const source=modified?'Змінено вручну':has(key)?result?.field_sources?.[key]||result?.source:'Потребує уточнення';
  return <label key={key}>{label}<input aria-label={label} disabled={saving} value={String(draft[key]??'')} onChange={e=>{setDraft(p=>({...p,[key]:e.target.value}));setConfirmed(false);}}/><small>{modified?'Змінено вручну':has(key)?'Знайдено':'Потребує уточнення'}</small>{result?.conflicts?.[key]&&<small className="vin-conflict">Розбіжність: {result.conflicts[key].primary} / {result.conflicts[key].secondary}</small>}</label>;
 }
 return <section className="vin-intake" aria-label="Додавання автомобіля за VIN">
  <div className="vin-actions"><label>VIN<input aria-label="VIN" value={vin} maxLength={17} spellCheck={false} disabled={saving} onChange={e=>{epoch.current++;setVin(e.target.value.trim().toUpperCase());setResult(null);setDraft({});setExtra({});setLoading(false);setConfirmed(false);setError('');setExisting(null);}} placeholder="YV4L12RK6N1970668"/></label>
  <button type="button" disabled={!valid||loading||saving} onClick={()=>void decode()}>{loading?'Визначаємо…':'Визначити автомобіль'}</button><button type="button" disabled={saving} onClick={manual}>Додати вручну</button></div>
  {vin&&!valid&&<p role="status">Введіть 17 символів без I, O, Q.</p>}
  {error&&<p role="alert">{error}</p>}{existing&&<button onClick={()=>onCreated(existing)}>Відкрити наявний автомобіль</button>}
  {result&&<><p role="status">{result.message}</p>
   <div className="vin-summary" role="region" aria-label="Зведення автомобіля"><strong>{[draft.manufacturer,draft.model,draft.year].filter(Boolean).join(' · ')||'Автомобіль потребує уточнення'}</strong><dl>{[['trim','Модифікація'],['body_class','Кузов'],['engine','Двигун'],['fuel_type','Паливо'],['transmission','КПП'],['drive_type','Привід']].map(([key,label])=><div key={key}><dt>{label}</dt><dd>{String(draft[key]||'Не визначено')}</dd></div>)}</dl></div>
   {result.counts&&<p className="vin-counts">Отримано: {result.counts.received_useful} · Важливих уточнень: {result.counts.undefined_important} · Конфліктів: {result.counts.conflicting}</p>}
   {Object.keys(result.consistency_issues||{}).length>0&&<p role="alert">{Object.values(result.consistency_issues||{}).join(' ')}</p>}
   {groups.map(([name,fields])=>{const visible=fields.filter(([key])=>has(key)||required.has(key));return (visible.length>0||name==='Додаткові характеристики'&&Object.keys(extra).length>0)&&<fieldset key={name}><legend>{name}</legend><div className="vin-fields">{visible.map(([key,label])=>field(key,label))}{name==='Додаткові характеристики'&&Object.entries(extra).map(([key,item])=><label key={'extra-'+key}>{item.label}<input aria-label={item.label} disabled={saving} value={item.value} onChange={e=>{setExtra(p=>({...p,[key]:{...p[key],value:e.target.value,source:'manual'}}));setConfirmed(false);}}/><small>{item.source==='manual'?'Змінено вручну':'Знайдено'}</small>{item.alternative&&<small className="vin-conflict">Розбіжність: {item.alternative}</small>}</label>)}</div></fieldset>})}
   {unknown.length>0&&<details className="vin-unknown"><summary>Потребує уточнення ({unknown.length})</summary><div className="vin-fields">{unknown.map(([key,label])=>field(key,label))}</div></details>}
   {identity?.catalogue_platform_admin===true&&result.provider_status&&<details className="vin-source-status"><summary>Технічні деталі</summary>{result.cached&&<p>Нещодавно отримана відповідь з кешу; час спостереження збережено.</p>}{Object.entries(result.provider_status).map(([name,state])=><p key={name}>{name}: {state==='reported'?'дані отримано':state==='not_needed'?'доповнення не потрібне':state==='robots_denied'?'автоматичний доступ заборонено правилами джерела':state==='rate_limited'?'досягнуто обмеження частоти':state==='empty'||state==='no_explicit_vehicle_data'?'потрібних даних немає':'дані недоступні; повторіть пізніше'}</p>)}</details>}
   <p className="vin-disclaimer">Відповідь джерела не підтверджує заводську комплектацію. Рік може бути модельним. Невідомі значення можна залишити порожніми.</p>
   <label className="vin-confirm"><input type="checkbox" checked={confirmed} disabled={saving} onChange={e=>setConfirmed(e.target.checked)}/>Характеристики перевірено, підтверджую додавання</label>
   <div className="vin-actions"><Permit permission="vehicles.create"><button className="primary" type="button" disabled={saving||!confirmed} onClick={()=>void create()}>{saving?'Зберігаємо…':'Додати автомобіль'}</button></Permit><button disabled={saving} onClick={onBack}>Скасувати</button></div>
  </>}
 </section>;
}
