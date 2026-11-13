import {useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';
import {useCan} from './permissions';

/** Explicit catalogue references; stock OEM needs separate physical confirmation. */
export default function VolvoOemPreview({vehicle}:{vehicle:Row}) {
 const can=useCan();
 const [choice,setChoice]=useState<Row|null>(null),[verify,setVerify]=useState(false),[physical,setPhysical]=useState(false),[message,setMessage]=useState('');
 const pending=useRef<{body:string,key:string}|null>(null);
 const autoPending=useRef<{body:string,key:string}|null>(null);
 const [queue,setQueue]=useState<{name:string,payload:Row,key:string}[]>([]);
 const [progress,setProgress]=useState('');
 const writing=useRef(false);
 const [data,setData]=useState<Row|null>(null),[detail,setDetail]=useState<Row|null>(null);
 const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [rowId,setRowId]=useState(''),[productId,setProductId]=useState(''),[q,setQ]=useState('');
 const epoch=useRef(0);
 useEffect(()=>{epoch.current++;return()=>{epoch.current++;}},[vehicle.id]);
 const path='/vehicles/'+vehicle.id+'/volvo-oem-preview?source_modification_id=107555';
 const types:Row[]=data?.catalogue_types||[];
 const rows:Row[]=data?.plan_items||[];
 const row=rows.find(r=>r.id===rowId);
 const editable=can('dismantling.manage')&&!vehicle.archived;
 const product=types.find(p=>String(p.product_id)===productId);
 const norm=(s:unknown)=>String(s||'').trim().toLocaleLowerCase('uk');
 const filtered=types.filter(p=>String(p.product_id)===productId||norm((p.name_uk||'')+' '+(p.name_source||'')+' '+(p.candidate_aliases||[]).join(' ')).includes(norm(q))).sort((a,b)=>Number((row?.candidate_product_ids||[]).includes(b.product_id))-Number((row?.candidate_product_ids||[]).includes(a.product_id)));
 async function load(nextProduct?:string){
  const ticket=++epoch.current;
  setBusy(true);setError('');setDetail(null);setChoice(null);setVerify(false);setPhysical(false);setMessage('');
  if(!nextProduct){setData(null);setRowId('');setProductId('');setQ('');}
  try {
   const result=await api(path+(nextProduct?'&product_id='+encodeURIComponent(nextProduct)+'&snapshot_sha='+encodeURIComponent(String(data?.snapshot_sha||'')):''));
   if(ticket!==epoch.current)return;
   if(nextProduct)setDetail(result);else {
    setData(result);
    if(editable){
     const payload={source_modification_id:107555,snapshot_sha:result.snapshot_sha,expected_vehicle_basis:result.vehicle_basis,confirm_modification:true};
     const body=JSON.stringify(payload);
     if(autoPending.current?.body!==body)autoPending.current={body,key:crypto.randomUUID()};
     setProgress('Автоматично підбираємо OEM для всього плану…');
     const saved=await api('/vehicles/'+vehicle.id+'/volvo-oem-auto','POST',{...payload,request_key:autoPending.current.key});
     if(ticket!==epoch.current)return;
     autoPending.current=null;
     window.dispatchEvent(new CustomEvent('warehouse:volvo-oem-changed',{detail:vehicle.id}));
     setMessage('Автоматично додано OEM: '+saved.added+' · збережено наявні: '+saved.preserved+' · без відповідності: '+saved.unresolved+'.');
     const fresh=await api(path);if(ticket===epoch.current)setData(fresh);
    }
   }
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}
  finally{if(ticket===epoch.current){setBusy(false);setProgress('')}}
 }
 function selection(stock:boolean){
  if(!row||!choice||!verify||!data||!detail||!editable)return null;
  return {source_modification_id:107555,snapshot_sha:data.snapshot_sha,expected_vehicle_basis:data.vehicle_basis,item_id:row.id,expected_row_basis:row.row_basis,expected_reference_digest:row.reference_digest,product_id:Number(productId),supplier_id:choice.supplier_id,article_number:choice.article_nr,oem_number:choice.oem_number,confirm_reference:true,assign_stock:stock,confirm_physical_oem:stock&&physical};
 }
 function enqueue(){
  const payload=selection(false);if(!payload||!row||busy||writing.current)return;
  setQueue(old=>[...old.filter(x=>x.payload.item_id!==row.id),{name:row.name,payload,key:crypto.randomUUID()}]);
  setChoice(null);setVerify(false);setPhysical(false);setMessage('Позицію додано до пакета. Збереження ще не виконано.');
 }
 async function saveBatch(){
  if(!queue.length||busy||writing.current||!editable)return;
  writing.current=true;const ticket=++epoch.current;const jobs=[...queue];let done=0;
  setBusy(true);setError('');setMessage('');setProgress('');
  try{
   for(const job of jobs){
    if(ticket!==epoch.current)break;
    setProgress('Збереження '+(done+1)+' / '+jobs.length+' · '+job.name);
    await api('/vehicles/'+vehicle.id+'/volvo-oem-selection','POST',{...job.payload,request_key:job.key});
    if(ticket!==epoch.current)return;
    done++;setQueue(old=>old.filter(x=>x.key!==job.key));
   }
   if(ticket===epoch.current)setMessage('Збережено довідкові OEM: '+done+' із '+jobs.length+'.');
  }catch(e){if(ticket===epoch.current)setError('Збережено '+done+' із '+jobs.length+'. Решту залишено в пакеті. '+(e as Error).message)}
  finally{
   if(ticket===epoch.current){
    try{setData(await api(path));setDetail(null);setChoice(null);setVerify(false);setPhysical(false);}catch(e){setError(old=>old||'Не вдалося оновити перегляд: '+(e as Error).message)}
    if(ticket===epoch.current){setBusy(false);setProgress('');window.dispatchEvent(new CustomEvent('warehouse:volvo-oem-changed',{detail:vehicle.id}));}
   }
   writing.current=false;
  }
 }
 async function save(stock:boolean){
  if(!row||busy||writing.current||queue.some(x=>x.payload.item_id===row.id))return;
  const payload=selection(stock);if(!payload)return;
  writing.current=true;const ticket=++epoch.current;
  const body=JSON.stringify(payload);
  if(pending.current?.body!==body)pending.current={body,key:crypto.randomUUID()};
  setBusy(true);setError('');setMessage('');
  try{
   const result=await api('/vehicles/'+vehicle.id+'/volvo-oem-selection','POST',{...payload,request_key:pending.current.key});
   if(ticket!==epoch.current)return;
   pending.current=null;
   const fresh=await api(path);if(ticket!==epoch.current)return;
   setData(fresh);setDetail(null);setChoice(null);setVerify(false);setPhysical(false);
   setMessage(result.stock_assigned?'OEM збережено у складській картці та плані.':'Довідковий OEM збережено у плані.');
   window.dispatchEvent(new CustomEvent('warehouse:volvo-oem-changed',{detail:vehicle.id}));
   if(result.stock_assigned)window.dispatchEvent(new Event('warehouse:inventory-changed'));
  }catch(e){if(ticket===epoch.current)setError((e as Error).message)}
  finally{writing.current=false;if(ticket===epoch.current)setBusy(false)}
 }
 return <details className="uf-catalogue-disclosure">
  <summary><span><strong>OEM Volvo · власний каталог</strong><small>Автоматичне заповнення OEM без заміни плану</small></span><span className="uf-catalogue-toggle">Переглянути</span></summary>
  <div className="uf-catalogue-details volvo-oem-preview">
   <p>Пілот: XC90 II T6 AWD · джерельна модифікація 107555. Каталог частковий. CarPot автоматично обирає довідковий номер; за потреби його можна замінити. Номери не підтверджені за VIN.</p>
   <label className="volvo-oem-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e=>{setConfirmed(e.target.checked);setData(null);setDetail(null);setRowId('');setProductId('');setError('')}}/> Я перевірив характеристики автомобіля. Заповнити відсутні довідкові OEM автоматично.</label>
   <button type="button" className="secondary" disabled={!confirmed||busy} onClick={()=>void load()}>{busy?'Завантажуємо…':'Завантажити OEM-каталог'}</button>
   {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}{progress&&<p role="status">{progress}</p>}
   {queue.length>0&&<section aria-label="Пакет перевірених OEM"><h3>Пакет перевірених OEM ({queue.length})</h3><p>Кожен номер обрано вручну. Записи зберігаються послідовно; склад не змінюється. Якщо виникне конфлікт, решта залишиться в пакеті.</p>{queue.map(job=><article key={job.key}><strong>{job.name} · {job.payload.oem_number}</strong><button type="button" className="secondary" disabled={busy} onClick={()=>setQueue(old=>old.filter(x=>x.key!==job.key))}>Прибрати</button></article>)}<button type="button" className="secondary" disabled={busy||!editable||!confirmed} onClick={()=>void saveBatch()}>Зберегти пакет OEM</button></section>}
   {data&&<>
    <p role="status">У плані {rows.length} · у джерелі {types.length} типів · {data.coverage==='partial'?'часткове покриття':'перевірене покриття'}.<br/>Збережено OEM: {rows.filter(r=>r.reference).length} · є варіант для перевірки: {rows.filter(r=>r.candidate_product_ids?.length&&!r.reference).length}.</p>
    <label>Змінити OEM / переглянути позицію<select aria-label="Позиція наявного плану" disabled={busy} value={rowId} onChange={e=>{setRowId(e.target.value);const selected=rows.find(r=>r.id===e.target.value);setProductId(String(selected?.reference?.product_id||(selected?.candidate_product_ids?.length===1?selected.candidate_product_ids[0]:'')));setQ('');setDetail(null);setChoice(null);setVerify(false);setPhysical(false)}}><option value="">Оберіть позицію</option>{rows.map(r=><option key={r.id} value={r.id}>{r.name}{r.position?' · '+r.position:''}{r.included===false?' · виключено':''}</option>)}</select></label>
    {row&&<><p>Категорія плану: {row.category} › {row.subcategory}. Назва сама по собі не встановлює відповідність.</p>{row.reference&&<p>Довідковий OEM: {row.reference.oem_number}{row.reference_stale?' · потребує повторної звірки':''}</p>}{row.stock_oem&&<p>OEM на складі: {row.stock_oem}</p>}
     <label>Пошук типу в каталозі<input value={q} disabled={busy} onChange={e=>setQ(e.target.value)} placeholder="Назва запчастини"/></label>
     <label>Каталожний тип<select aria-label="Каталожний тип OEM" value={productId} disabled={busy} onChange={e=>{setProductId(e.target.value);setDetail(null);setChoice(null);setVerify(false);setPhysical(false)}}><option value="">Оберіть тип для порівняння</option>{filtered.map(p=><option key={p.product_id} value={p.product_id}>{p.name_uk||p.name_source} · #{p.product_id} · {p.article_count} арт.{(row.candidate_product_ids||[]).includes(p.product_id)?' · запропоновано для звірки':''}</option>)}</select></label>
     {product&&<p>{(product.category_path||[]).filter(Boolean).join(' › ')||'Категорію не перевірено'} · {product.kind==='part'?'Тип деталі визначено':'Потребує перевірки типу'}{product.pilot_reviewed?' · локальна класифікація Volvo':''}</p>}
     <button type="button" className="secondary" disabled={!product||busy} onClick={()=>void load(productId)}>Знайти артикули та OEM</button>
    </>}
    {detail&&<section aria-label="Результати OEM Volvo"><h3>Артикули та OEM-кроси</h3><p>Лише OEM Volvo. Артикул постачальника не призначається автоматично.</p>{detail.articles.length===0?<p>Артикули відсутні.</p>:detail.articles.map((a:Row)=><article key={a.supplier_id+':'+a.article_nr}><strong>{a.brand||'Невідомий виробник'} · {a.article_nr}</strong><p>OEM: {a.oem_numbers.join(', ')||'Немає даних'}</p>{editable&&product?.kind==='part'&&a.brand&&a.oem_numbers.map((n:string)=><button key={n} type="button" className="secondary" disabled={busy} aria-pressed={choice?.supplier_id===a.supplier_id&&choice?.article_nr===a.article_nr&&choice?.oem_number===n} onClick={()=>{setChoice({...a,oem_number:n});setVerify(false);setPhysical(false)}}>Вибрати OEM {n}</button>)}</article>)}
    {choice&&row&&editable&&<div className="volvo-oem-preview"><p>Обрано: {choice.oem_number} · {row.name}</p><label className="volvo-oem-confirm"><input type="checkbox" checked={verify} disabled={busy} onChange={e=>setVerify(e.target.checked)}/>Підтверджую відповідність типу, модифікації та обраного каталожного OEM. {row.reference?'Замінити попередній довідковий номер у плані.':''}</label><button type="button" className="secondary" disabled={!verify||busy||row.included===false||queue.some(x=>x.payload.item_id===row.id)} onClick={()=>void save(false)}>Зберегти OEM у плані</button><button type="button" className="secondary" disabled={!verify||busy||row.included===false} onClick={enqueue}>Додати до пакета</button>{row.stock_eligible&&can('inventory.edit')&&<><label className="volvo-oem-confirm"><input type="checkbox" checked={physical} disabled={busy} onChange={e=>setPhysical(e.target.checked)}/>Перевірив номер на фактичній деталі; підтверджую запис у складську картку.</label><button type="button" className="secondary" disabled={!verify||!physical||busy||queue.some(x=>x.payload.item_id===row.id)} onClick={()=>void save(true)}>Призначити OEM на складі</button></>}</div>}</section>}
   </>}
  </div>
 </details>
}
