import {useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';

/** Explicit comparison only: never writes to the donor, plan, stock or payments. */
export default function VolvoOemPreview({vehicle}:{vehicle:Row}) {
 const [data,setData]=useState<Row|null>(null),[detail,setDetail]=useState<Row|null>(null);
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [rowId,setRowId]=useState(''),[productId,setProductId]=useState(''),[q,setQ]=useState('');
 const epoch=useRef(0);
 useEffect(()=>{epoch.current++;return()=>{epoch.current++;}},[vehicle.id]);
 const path='/vehicles/'+vehicle.id+'/volvo-oem-preview?source_modification_id=107555';
 const types:Row[]=data?.catalogue_types||[];
 const rows:Row[]=data?.plan_items||[];
 const row=rows.find(r=>r.id===rowId);
 const product=types.find(p=>String(p.product_id)===productId);
 const norm=(s:unknown)=>String(s||'').trim().toLocaleLowerCase('uk');
 const filtered=types.filter(p=>String(p.product_id)===productId||norm((p.name_uk||'')+' '+(p.name_source||'')).includes(norm(q)));
 async function load(nextProduct?:string){
  const ticket=++epoch.current;
  setBusy(true);setError('');setDetail(null);
  if(!nextProduct){setData(null);setRowId('');setProductId('');setQ('');}
  try {
   const result=await api(path+(nextProduct?'&product_id='+encodeURIComponent(nextProduct)+'&snapshot_sha='+encodeURIComponent(String(data?.snapshot_sha||'')):''));
   if(ticket!==epoch.current)return;
   if(nextProduct)setDetail(result);else setData(result);
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}
  finally{if(ticket===epoch.current)setBusy(false)}
 }
 return <details className="uf-catalogue-disclosure">
  <summary><span><strong>OEM Volvo · власний каталог</strong><small>Порівняння з наявним планом без його заміни</small></span><span className="uf-catalogue-toggle">Переглянути</span></summary>
  <div className="uf-catalogue-details volvo-oem-preview">
   <p>Пілот: XC90 II T6 AWD · джерельна модифікація 107555. Каталог частковий. Номери є каталожними кросами, а не підтвердженням сумісності за VIN.</p>
   <label className="volvo-oem-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>{setConfirmed(e.target.checked);setData(null);setDetail(null);setRowId('');setProductId('');setError('')}}/> Я перевірив характеристики автомобіля і хочу порівняти його з цією модифікацією.</label>
   <button type="button" className="secondary" disabled={!confirmed||busy} onClick={()=>void load()}>{busy?'Завантажуємо…':'Завантажити OEM-каталог'}</button>
   {error&&<p role="alert">{error}</p>}
   {data&&<>
    <p role="status">У плані {rows.length} · у джерелі {types.length} типів · {data.coverage==='partial'?'часткове покриття':'перевірене покриття'}.</p>
    <label>Позиція наявного плану<select aria-label="Позиція наявного плану" disabled={busy} value={rowId} onChange={e=>{setRowId(e.target.value);setProductId('');setDetail(null)}}><option value="">Оберіть позицію</option>{rows.map(r=><option key={r.id} value={r.id}>{r.name}{r.position?' · '+r.position:''}{r.included===false?' · виключено':''}</option>)}</select></label>
    {row&&<><p>Категорія плану: {row.category} › {row.subcategory}. Назва сама по собі не встановлює відповідність.</p>
     <label>Пошук типу в каталозі<input value={q} disabled={busy} onChange={e=>setQ(e.target.value)} placeholder="Назва запчастини"/></label>
     <label>Каталожний тип<select aria-label="Каталожний тип OEM" value={productId} disabled={busy} onChange={e=>{setProductId(e.target.value);setDetail(null)}}><option value="">Оберіть тип для порівняння</option>{filtered.map(p=><option key={p.product_id} value={p.product_id}>{p.name_uk||p.name_source} · #{p.product_id} · {p.article_count} арт.{norm(p.name_uk)===norm(row.name)?' · однакова назва':''}</option>)}</select></label>
     {product&&<p>{(product.category_path||[]).filter(Boolean).join(' › ')} · {product.kind==='part'?'Деталь':'Потребує перевірки типу'}</p>}
     <button type="button" className="secondary" disabled={!product||busy} onClick={()=>void load(productId)}>Знайти артикули та OEM</button>
    </>}
    {detail&&<section aria-label="Результати OEM Volvo"><h3>Артикули та OEM-кроси</h3><p>Тільки перегляд. Дані складу не змінено.</p>{detail.articles.length===0?<p>Артикули відсутні.</p>:detail.articles.map((a:Row)=><article key={a.supplier_id+':'+a.article_nr}><strong>{a.brand||'Невідомий виробник'} · {a.article_nr}</strong><p>OEM: {a.oem_numbers.join(', ')||'Немає даних'}</p></article>)}</section>}
   </>}
  </div>
 </details>
}
