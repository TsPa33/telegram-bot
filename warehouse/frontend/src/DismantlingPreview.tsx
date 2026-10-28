import {useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';
import './dismantling-preview.css';
const positions:Record<string,string>={left:'Ліва',right:'Права',front:'Передня',rear:'Задня',unknown:'Невідома'};
const labels:Record<string,string>={confirmed:'Підтверджено',possible:'Можливо',unknown:'Невідомо',incompatible:'Несумісно'};
const fields:[string,string,string[]?][]=[['vin','VIN'],['generation','Покоління'],['year','Рік'],['powertrain','Силова установка',['petrol','diesel','HEV','PHEV','BEV']],['fuel_type','Пальне',['petrol','diesel','electric','other']],['engine_code','Точний код двигуна'],['transmission','Трансмісія'],['drive','Привід',['FWD','RWD','AWD','4WD']],['body_type','Кузов'],['options','Відомі коди опцій']];
const names:Record<string,string>={petrol:'Бензин',diesel:'Дизель',electric:'Електрика',other:'Інше'};
export default function DismantlingPreview({vehicle}:{vehicle:Row}){
 const [configuration,setConfiguration]=useState<Row|null>(null),[draft,setDraft]=useState<Record<string,string>>({}),[result,setResult]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const epoch=useRef(0),active=useRef(false);
 useEffect(()=>{const id=++epoch.current;active.current=false;setBusy(false);setDraft({});setResult(null);setConfiguration(null);setError('');api(`/vehicles/${vehicle.id}/configuration`).then(r=>{if(id===epoch.current)setConfiguration(r.configuration);}).catch(e=>{if(id===epoch.current)setError(e.message);});return()=>{epoch.current++;};},[vehicle.id]);
 async function generate(){
  if(active.current)return;active.current=true;const id=epoch.current;setBusy(true);setError('');setResult(null);
  try{const facts=Object.entries(draft).filter(([,value])=>value.trim()).map(([field,value])=>({field,value:field==='year'?Number(value):field==='options'?value.split(',').map(x=>x.trim()).filter(Boolean):value.trim(),kind:'manual',reference:'Уточнення лише для поточного preview',confidence:'reported'}));
   const r=await api(`/vehicles/${vehicle.id}/dismantling-preview`,'POST',{facts});if(id===epoch.current)setResult(r);
  }catch(e){if(id===epoch.current)setError((e as Error).message);}finally{if(id===epoch.current){setBusy(false);active.current=false;}}
 }
 const values=configuration?.status==='confirmed'?configuration.values:vehicle;
 return <section className="dismantling-v3" aria-label="Попередній план розбору v3">
  <h3>Попередній план розбору v3</h3>
  <p>Перевірка без збереження плану. Невідомі параметри не означають відсутність деталей.</p>
  <p>Поточна конфігурація: {vehicle.manufacturer} {vehicle.model} · {values?.year??'Рік невідомий'} · {names[values?.powertrain]||values?.powertrain||'Силова установка невідома'}{configuration?.status==='stale'?' · збережена конфігурація застаріла':''}</p>
  <dl>{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{Array.isArray(values?.[key])?values[key].join(', ')||'Невідомо':names[values?.[key]]||values?.[key]||'Невідомо'}</dd></div>)}</dl>
  <details><summary>Уточнити параметри лише для preview</summary><div className="dismantling-v3-fields">
   {fields.map(([key,label,options])=><label key={key}>{label}{options?<select aria-label={label} disabled={busy} value={draft[key]??''} onChange={e=>{setDraft(d=>({...d,[key]:e.target.value}));setResult(null);}}><option value="">Без уточнення ({values?.[key]||'невідомо'})</option>{options.map(x=><option key={x} value={x}>{names[x]??x}</option>)}</select>:<input aria-label={label} disabled={busy} type={key==='year'?'number':'text'} placeholder={String(values?.[key]||'Невідомо')} value={draft[key]??''} onChange={e=>{setDraft(d=>({...d,[key]:e.target.value}));setResult(null);}}/>}</label>)}
  </div><p>Ці уточнення не підтверджують комплектацію та не змінюють дані автомобіля.</p></details>
  <button disabled={busy} onClick={generate}>{busy?'Формуємо попередній план…':'Сформувати попередній план'}</button>
  {error&&<p role="alert">{error}</p>}
  {result&&<div aria-live="polite"><p>Унікальних позицій: <strong>{result.total}</strong>; канонічних типів: {result.unique_type_count}. {Object.entries(result.status_counts).map(([key,n])=>`${labels[key]}: ${n}`).join(' · ')}</p>
   {!result.published&&<p role="status">Глобальна нормалізація ще не опублікована. Показано базовий конструктивний довідник.</p>}
   <p>{result.coverage_note}. Неопрацьованих шляхів: {result.unmapped_paths}. Кількість деталей для встановлення потребує окремого підтвердження.</p>
   {result.configuration.conflicts.length>0&&<p role="alert">Конфліктні характеристики: {result.configuration.conflicts.map((x:Row)=>fields.find(([key])=>key===x.field)?.[1]??x.field).join(', ')}. Деталі не виключено.</p>}
   {result.items.map((item:Row)=><article className="dismantling-v3-item" key={item.id}><small>{item.category} / {item.subcategory}</small><h4>{item.name}</h4><p>{labels[item.applicability_status]} · {positions[item.installation_position.side]} / {positions[item.installation_position.position]}</p><p>{item.explanation}</p><p>Ринкових пропозицій: {item.relevant_offer_count} · OEM-варіантів: {item.variants.length}</p>
    {item.reference_prices.length?item.reference_prices.map((p:Row)=><p key={`${p.variant_id}-${p.condition}-${(p.condition_details??[]).join(',')}-${p.currency}`}>{p.label}: OEM {p.oem}, стан: {p.condition}{p.condition_details?.length?` (${p.condition_details.join(', ')})`:''}; {p.minimum}–{p.maximum} {p.currency}; медіана {p.median}; {p.offer_count} пропозиції; {new Date(p.observed_at).toLocaleDateString('uk-UA')}</p>):<p>Ціну не визначено</p>}
    <details><summary>Джерела включення</summary>{item.source.map((s:Row)=><p key={s.key}>{s.kind==='base'?'Базовий конструктивний довідник':s.provider??'Перевірений каталог'}{s.article?` · артикул ${s.article}`:''}</p>)}{item.source_truncated&&<p>Показано частину джерел із {item.source_ref_count}.</p>}</details>
    {item.evidence_details?.map((e:Row)=><p key={e.id}>Доказ: {e.explanation}</p>)}
    {item.variants.length>0&&<details><summary>Варіанти та докази</summary>{item.variants.map((v:Row)=><p key={v.id}>OEM {v.oem??'невідомий'} · {labels[v.applicability_status]} · {v.explanation} · доказів: {v.compatibility?.evidence_ids?.length??0}</p>)}</details>}
   </article>)}
  </div>}
 </section>;
}
