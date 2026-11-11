import {useEffect,useState} from 'react';
import {api,type Row} from './api';
import './unified-dismantling.css';
import {useCan} from './permissions';
import AssemblyTree from './AssemblyTree';
import UniversalPlanGenerator from './UniversalPlanGenerator';

export function GlobalVehicleForm({onSaved,vehicle,expectedBasis}:{onSaved:(row:Row)=>void;vehicle?:Row;expectedBasis?:string}) {
 const [items,setItems]=useState<Row[]>([]),[picked,setPicked]=useState(''),[brand,setBrand]=useState(''),[model,setModel]=useState(''),[gen,setGen]=useState(''),[year,setYear]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [requestKey]=useState(()=>crypto.randomUUID()),[confirmed,setConfirmed]=useState(false);
 useEffect(()=>{let active=true;async function load(){try{let after=0;const all:Row[]=[];for(let i=0;i<100;i++){const page=await api(`/vehicles/catalogue-directory/available?after=${after}`);all.push(...page.items);if(page.next_after==null){if(active)setItems(all);return}if(page.next_after<=after)throw Error('Некоректна відповідь каталогу');after=page.next_after}throw Error('Каталог потребує посторінкового пошуку')}catch(e){if(active)setError((e as Error).message)}}void load();return()=>{active=false}},[]);
 const filtered=items.filter(r=>r.manufacturer===brand&&String(r.model_id)===model&&(r.generation||'unknown')===gen);
 const selected=filtered.find(r=>String(r.source_modification_id)===picked);
 return <form aria-label={vehicle?'Модифікація наявного автомобіля':'Автомобіль із каталогу'} className="uf-fields" onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);setError('');try{if(vehicle){if(!confirmed||!selected)return;await api(`/vehicles/${vehicle.id}/catalogue-selection`,'POST',{request_key:requestKey,source_modification_id:Number(picked),model_id:selected.model_id,manufacturer_id:selected.manufacturer_id,source_snapshot_sha:selected.snapshot_sha,expected_basis:expectedBasis,confirm_exact_modification:true});onSaved(await api(`/vehicles/${vehicle.id}`));}else onSaved(await api('/vehicles/catalogue-directory/vehicles','POST',{request_key:requestKey,source_modification_id:Number(picked),year:Number(year)}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>
 <label>Марка<select aria-label="Марка" required value={brand} onChange={e=>{setConfirmed(false);setBrand(e.target.value);setModel('');setGen('');setPicked('')}}><option value="">Оберіть марку</option>{[...new Set(items.map(r=>r.manufacturer))].map(v=><option key={v}>{v}</option>)}</select></label>
 <label>Модель<select aria-label="Модель" required value={model} onChange={e=>{setConfirmed(false);setModel(e.target.value);setGen('');setPicked('')}}><option value="">Оберіть модель</option>{items.filter(r=>r.manufacturer===brand).filter((r,i,all)=>all.findIndex(v=>v.model_id===r.model_id)===i).map(r=><option key={r.model_id} value={r.model_id}>{r.model}</option>)}</select></label>
 <label>Покоління<select aria-label="Покоління" required value={gen} onChange={e=>{setConfirmed(false);setGen(e.target.value);setPicked('')}}><option value="">Оберіть покоління</option>{[...new Set(items.filter(r=>String(r.model_id)===model&&r.manufacturer===brand).map(r=>r.generation||'unknown'))].map(v=><option key={v} value={v}>{v==='unknown'?'Немає даних':v}</option>)}</select></label>
 <label>Модифікація<select aria-label="Модифікація" required value={picked} onChange={e=>{setConfirmed(false);setPicked(e.target.value)}}><option value="">Оберіть модифікацію</option>{filtered.map(r=><option key={r.source_modification_id} value={r.source_modification_id}>{r.modification?.description||'Назву не надано'}</option>)}</select></label>
 {selected&&<p>{selected.type_count} типів · {selected.article_count} артикулів · {selected.oem_links} OEM-зв’язків · {selected.coverage==='partial'?'Часткове покриття':'Покриття перевірено'}</p>}
 {!vehicle&&<label>Рік конкретного автомобіля<input required type="number" min="1886" max="2100" value={year} onChange={e=>setYear(e.target.value)}/></label>}
 <p>Показано лише доступні зв’язки глобального каталогу. Невідомі характеристики не заповнюються автоматично.</p>
 {vehicle&&<><p>Автомобіль: {vehicle.manufacturer} {vehicle.model} · {vehicle.year}. VIN і збережені характеристики залишаться без змін.</p><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>Перевірив модель, покоління й характеристики та підтверджую цю модифікацію. Сам VIN не доводить відповідність каталогу.</label></>}
 {error&&<p role="alert">{error}</p>}<button disabled={busy||!picked||!!vehicle&&(!confirmed||!expectedBasis)}>{busy?'Зберігаємо…':vehicle?'Підтвердити модифікацію':'Додати автомобіль'}</button></form>;
}

export default function GlobalCatalogueFlow({vehicle,onSaved}:{vehicle:Row;onSaved:(row:Row)=>void}) {
 const can=useCan();
 const [assemblyMode,setAssemblyMode]=useState<boolean|null>(null);
 const [legacy,setLegacy]=useState<Row[]|null>(null);
 const [state,setState]=useState<Row>({}),[revision,setRevision]=useState(0),[chooseModification,setChooseModification]=useState(false);
 const saved=state.saved;
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[detail,setDetail]=useState<Row|null>(null),[q,setQ]=useState(''),[page,setPage]=useState(0);
 useEffect(()=>{let active=true;setState({});api(`/vehicles/${vehicle.id}/global-dismantling`).then(r=>{if(active)setState(r)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[vehicle.id,revision]);
 const products:Row[]=saved?.payload?.categories||[];
 const filtered=products.filter(p=>`${p.name_uk} ${p.name_source}`.toLowerCase().includes(q.toLowerCase()));
 return <section className="unified-flow" aria-label="Розбір автомобіля">
  <details className="uf-catalogue-disclosure">
   <summary><span><strong>Каталог і модифікація</strong><small>{state.selection?'Точна модифікація вибрана':'Точна модифікація не підтверджена · базовий каталог'}</small></span><span className="uf-catalogue-toggle">Налаштувати</span></summary>
   <div className="uf-catalogue-details">
    <div className="uf-source-strip" aria-label="Модифікація каталогу">
   <span className={state.selection?'uf-source-confirmed':'uf-source-warning'}>
    {state.selection?'Модифікація: '+(state.selection.modification_description||'підтверджена користувачем'):'Точну каталожну модифікацію не вибрано — показано базовий каталог'}
   </span>
   <button className="secondary" disabled={vehicle.archived||!can('vehicles.edit')||!can('dismantling.manage')} onClick={()=>setChooseModification(v=>!v)}>{chooseModification?'Закрити вибір':'Вибрати модифікацію'}</button>
  </div>
  {chooseModification&&state.selection_basis&&<div className="uf-source-picker"><GlobalVehicleForm key={vehicle.id+':'+state.selection_basis} vehicle={vehicle} expectedBasis={state.selection_basis} onSaved={row=>{setChooseModification(false);setRevision(n=>n+1);onSaved(row)}}/></div>}
  <UniversalPlanGenerator vehicle={vehicle} revision={revision} onSaved={()=>{setRevision(n=>n+1);onSaved(vehicle)}}/>
   </div>
  </details>
  <AssemblyTree vehicle={vehicle} revision={revision} onReady={setAssemblyMode}/>{!assemblyMode&&<h2>Розбір автомобіля</h2>}{error&&<p role="alert">{error}</p>}
 {state.legacy&&<details><summary>Збережені попередні списки</summary><p>Історичний список збережено окремо від глобального каталогу.</p><button onClick={async()=>{try{setLegacy((await api(`/vehicles/${vehicle.id}/dismantling-workspace?source=${state.legacy_source}`)).items)}catch(e){setError((e as Error).message)}}}>Переглянути збережений список</button>{legacy?.map(r=><p key={r.key}>{r.name}</p>)}</details>}
 {!saved?null:assemblyMode===false?<>
 <p>Список збережено · {products.length} типів · {saved.payload.coverage==='partial'?'Часткове покриття — повноту не підтверджено':'Покриття перевірено'}</p>
 <label>Пошук деталей<input value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/></label>
 <div style={{overflowX:'auto'}}><table><thead><tr><th>Деталь</th><th>Категорія</th><th>Артикули</th><th>Дані</th></tr></thead><tbody>{filtered.slice(page*25,(page+1)*25).map(p=><tr key={p.product_id}><td>{p.name_uk||p.name_source}<small>{p.name_uk&&p.name_source}</small></td><td>{p.category_path?.filter(Boolean).join(' → ')||'Потребує уточнення'}</td><td>{p.article_count} <button disabled={busy||!state.keys} onClick={async()=>{const key=state.keys?.[p.product_id];if(!key){setError('Позицію не знайдено у збереженому списку');return}setBusy(true);try{setDetail(await api(`/vehicles/${vehicle.id}/unified-catalogue/articles?key=${encodeURIComponent(key)}`))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Переглянути</button></td><td>{p.mapping_reviewed_by?'Категорію перевірено':'Потребує перевірки'}</td></tr>)}</tbody></table></div>{filtered.length>25&&<nav aria-label="Сторінки деталей"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Попередня</button><span> {page+1} / {Math.ceil(filtered.length/25)} </span><button disabled={(page+1)*25>=filtered.length} onClick={()=>setPage(p=>p+1)}>Наступна</button></nav>}
 {detail&&<section aria-label="Каталожні варіанти"><h3>Артикули та OEM-кроси</h3><button onClick={()=>setDetail(null)}>Закрити</button><p>Каталожний крос не підтверджує VIN-сумісність.</p>{detail.articles.map((a:Row)=><article key={a.art_id}><strong>{a.article_nr} · {a.brand||'Виробника не вказано'}</strong><p>OEM: {a.oem_numbers.join(', ')||'Немає даних'}</p></article>)}</section>}</>:null}
 </section>;
}
