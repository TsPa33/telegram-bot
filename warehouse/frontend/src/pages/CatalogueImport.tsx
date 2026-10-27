import {useState} from 'react';
import {api,csrf,type Row} from '../api';
import {Heading,State,useLoad} from '../shared';

type Decision={action:string;target_id?:string;name?:string};
const names:Record<string,string>={manufacturers:'Марки',models:'Моделі',categories:'Категорії',subcategories:'Підкатегорії',part_types:'Типи деталей',sources:'Джерела',offers:'Пропозиції',prices:'Спостереження цін',applications:'Зв’язки з моделями',paths:'Шляхи',aliases:'Підтверджені aliases'};

function Resolution({row,value,onChange}:{row:Row;value?:Decision;onChange:(v?:Decision)=>void}) {
 const [query,setQuery]=useState(''),[candidates,setCandidates]=useState<Row[]>(row.candidates||[]),[error,setError]=useState('');
 const selected=value?.action==='target'?`target:${value.target_id}`:value?.action||'';
 return <div className="panel padded"><b>{row.kind}: {row.name}</b><p>{row.reason}</p>
  <label>Рішення для {row.name}<select value={selected} onChange={e=>{const v=e.target.value;onChange(v.startsWith('target:')?{action:'target',target_id:v.slice(7)}:v?{action:v}:undefined);}}>
   <option value="">Без ручного рішення</option>
   {row.allowed_actions.includes('skip')&&<option value="skip">Явно пропустити зіставлення</option>}
   {row.allowed_actions.includes('keep_existing')&&<option value="keep_existing">Зберегти існуючі властивості</option>}
   {row.allowed_actions.includes('accept_incoming')&&<option value="accept_incoming">Підтвердити нові властивості</option>}
   {row.allowed_actions.includes('create_name')&&<option value="create_name">Задати перевірену назву</option>}
   {row.allowed_actions.includes('target')&&candidates.map(c=><option key={c.id} value={`target:${c.id}`}>Об’єднати: {c.name} · {Object.values(c.details||{}).filter(Boolean).join(' / ')}</option>)}
  </select></label>
  {value?.action==='create_name'&&<label>Перевірена назва<input value={value.name||''} maxLength={1000} onChange={e=>onChange({...value,name:e.target.value})}/></label>}
  {row.allowed_actions.includes('target')&&<div className="modal-actions"><label>Пошук відповідності<input value={query} onChange={e=>setQuery(e.target.value)}/></label><button type="button" onClick={async()=>{try{setError('');const r=await api(`/catalogue/admin/entities?kind=${row.kind}&q=${encodeURIComponent(query)}${row.parent_id?`&parent_id=${row.parent_id}`:''}`);setCandidates(r.items);}catch(e){setError((e as Error).message);}}}>Знайти наявний запис</button></div>}
  {(row.existing||row.incoming||row.incoming_examples)&&<details><summary>Порівняти властивості джерела</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({existing:row.existing,incoming:row.incoming,examples:row.incoming_examples},null,2)}</pre></details>}
  {error&&<p role="alert">{error}</p>}
 </div>;
}

export default function CatalogueImport({enabled}:{enabled:boolean}) {
 if(!enabled)return <section className="panel padded"><h1>Доступ обмежено</h1><p>Глобальний імпорт доступний тільки власнику платформи з серверного allowlist.</p></section>;
 return <ImportWorkspace/>;
}

function ImportWorkspace() {
 const history=useLoad(()=>api('/catalogue/admin/jobs'),[]);
 const [job,setJob]=useState<Row|null>(null),[resolutions,setResolutions]=useState<Record<string,Decision>>({}),[dirty,setDirty]=useState(false),[confirmed,setConfirmed]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[file,setFile]=useState<File|null>(null);
 function accept(next:Row){setJob(next);setResolutions(next.resolutions||{});setDirty(false);setConfirmed(false);}
 async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();history.reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const report=job?.report;
 return <>
  <Heading eyebrow="АДМІНІСТРУВАННЯ → КАТАЛОГ" title="Імпорт глобального каталогу" description="Спільний довідник усіх складів. Preview не записує каталог; apply потребує окремого підтвердження."/>
  <section className="panel padded"><label>Файл каталогу<input type="file" accept=".csv,.zip,.sqlite3,.gz" disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
   <p>CSV/ZIP CarPot Catalogue Import v2 або Aleto v1 SQLite/GZIP. До 16 MiB; тестові ціни не є реальними ринковими.</p>
   <button disabled={!file||busy} onClick={()=>run(async()=>{
    if(!file)return;const before=csrf();
    const r=await fetch('/api/v1/catalogue/admin/jobs',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':before,'X-Catalogue-Filename':encodeURIComponent(file.name)},body:file});
    if(csrf()!==before)throw Error('Сесію змінено; оновіть сторінку');
    const body=await r.json();if(!r.ok){if(r.status===401)window.dispatchEvent(new Event('warehouse:logout'));if(r.status===403)window.dispatchEvent(new Event('warehouse:permissions-changed'));throw Error(body.detail||'Файл відхилено');}accept(body);
   })}>Завантажити файл</button>
  </section>
  {error&&<p className="error" role="alert">{error}</p>}
  {busy&&<p role="status">Обробка каталогу… Стан зберігається на сервері.</p>}
  {job&&<section className="panel padded"><h2>{job.filename}</h2><p>Job {job.id} · {job.status} · {job.format}</p><small style={{overflowWrap:'anywhere'}}>SHA-256: {job.file_sha256}</small>
   <div className="modal-actions"><button disabled={busy||job.status==='applied'||job.status==='failed'} onClick={()=>run(async()=>accept(await api(`/catalogue/admin/jobs/${job.id}/preview`,'POST',{resolutions})))}>Побудувати preview</button><button disabled={busy} onClick={()=>{setResolutions({});setDirty(true);setConfirmed(false);}}>Очистити ручні рішення</button></div>
   {report?.counts&&<><h3>План змін</h3><p>Рядків: {report.input_rows}; невирішених відповідностей: {report.unresolved_total}; явно пропущено: {report.skipped_rows}. {report.committed?'Дані застосовано.':'Каталог не змінено.'}</p>
    <div className="table-wrap"><table><thead><tr><th>Сутність</th><th>Нові</th><th>Оновлені</th><th>Без змін</th></tr></thead><tbody>{Object.entries(report.counts).map(([key,v])=>{const c=v as Row;return <tr key={key}><td>{names[key]||key}</td><td>{c.inserted}</td><td>{c.updated}</td><td>{c.unchanged}</td></tr>;})}</tbody></table></div>
    {!!report.price_changes?.length&&<details><summary>Нові спостереження цін (перші 50)</summary><div className="table-wrap"><table><thead><tr><th>Джерело / артикул</th><th>Попередня UAH / USD</th><th>Нова UAH / USD</th><th>Дата джерела</th></tr></thead><tbody>{report.price_changes.map((p:Row,i:number)=><tr key={i}><td>{p.source} · {p.source_article}</td><td>{p.previous_uah??'—'} / {p.previous_usd??'—'}</td><td>{p.price_uah??'—'} / {p.price_usd??'—'}</td><td>{p.observed_at}</td></tr>)}</tbody></table></div></details>}
    {job.status!=='applied'&&<><h3>Потребують перевірки</h3>{report.issues?.map((r:Row)=><Resolution key={r.key} row={r} value={resolutions[r.key]} onChange={v=>{setResolutions(old=>{const next={...old};if(v)next[r.key]=v;else delete next[r.key];return next;});setDirty(true);setConfirmed(false);}}/>)}
     {report.issues_truncated&&<p>Показано перші 200 відповідностей. Після їх вирішення побудуйте preview знову.</p>}
     <details><summary>Нові записи та ручне об’єднання ({report.suggestion_total})</summary>{report.suggestions?.map((r:Row)=><Resolution key={r.key} row={r} value={resolutions[r.key]} onChange={v=>{setResolutions(old=>{const next={...old};if(v)next[r.key]=v;else delete next[r.key];return next;});setDirty(true);setConfirmed(false);}}/>)}</details>
     {dirty&&<p role="status">Рішення змінено — потрібен новий preview.</p>}
     <label><input type="checkbox" checked={confirmed} disabled={busy||dirty||job.status!=='ready'} onChange={e=>setConfirmed(e.target.checked)}/> Підтверджую застосування саме цього перевіреного preview до глобального каталогу</label>
     <button className="primary" disabled={busy||dirty||!confirmed||job.status!=='ready'} onClick={()=>run(async()=>accept(await api(`/catalogue/admin/jobs/${job.id}/apply`,'POST',{preview_token:job.preview_token,confirm:true})))}>Застосувати імпорт</button>
    </>}
   </>}
   {report?.error&&<p role="alert">{report.error}</p>}
  </section>}
  <Heading eyebrow="ЗБЕРЕЖЕНІ РЕЗУЛЬТАТИ" title="Історія імпортів" description="Після перезапуску відкрийте job і продовжте збережений preview."/>
  <State error={history.error} loading={history.loading}/>
  <section className="panel padded">{history.data?.items.map((j:Row)=><p key={j.id}><button disabled={busy} onClick={()=>run(async()=>accept(await api(`/catalogue/admin/jobs/${j.id}`)))}>{j.filename} · {j.status}</button> · {new Date(j.created_at).toLocaleString('uk-UA')}</p>)}</section>
 </>;
}
