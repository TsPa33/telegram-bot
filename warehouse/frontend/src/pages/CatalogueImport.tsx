import {useEffect,useRef,useState} from 'react';
import {api,ApiError,csrf,type Row} from '../api';
import {Heading,State,useLoad} from '../shared';
import {accepted,active,begin,canApply,complete,dirty,draftKey,editDecision,emptyReview,equal,lastKey,openReview,reconcile,savedReview,showReport,type Decision,type Review} from '../catalogueReview';
import '../catalogue-import.css';

const operationNames:Record<string,string>={queued:'Очікує виконання',running:'Виконується',done:'Готово',error:'Помилка'};
const names:Record<string,string>={manufacturers:'Марки',models:'Моделі',categories:'Категорії',subcategories:'Підкатегорії',part_types:'Типи деталей',sources:'Джерела',offers:'Пропозиції',prices:'Спостереження цін',applications:'Зв’язки з моделями',paths:'Шляхи',aliases:'Підтверджені відповідності'};
const errorText=(e:unknown)=>e instanceof ApiError&&e.message==='Не вдалося виконати запит. Спробуйте ще раз.'?`HTTP ${e.status}: сервер не підтвердив запит. Поля залишаються у чернетці.`:(e as Error).message;
const actions:Record<string,string>={create_name:'Створити',target:'Об’єднати',skip:'Пропустити',keep_existing:'Зберегти наявне',accept_incoming:'Підтвердити нове'};

function DecisionRow({row,value,checked,sent,onChange}:{row:Row;value?:Decision;checked?:Decision;sent?:Decision;onChange:(v?:Decision)=>void}){
 const [candidates,setCandidates]=useState<Row[]>(row.candidates||[]),[query,setQuery]=useState(''),[error,setError]=useState('');
 const verified=!!value&&!!checked&&equal({v:value},{v:checked});
 const submitted=!!value&&!!sent&&equal({v:value},{v:sent});
 const status=verified?'Перевірено сервером':submitted?'Відправлено на перевірку':complete(value)?'Готово до перевірки':'Потрібне рішення';
 return <tr>
  <td data-label="Початкова назва"><b>{row.sourceUnavailable?'Початкова назва відсутня у завершеному звіті':row.name}</b><small>{row.sourceUnavailable?row.name:row.reason}</small>{(row.existing||row.incoming||row.incoming_examples)&&<details><summary>Дані джерела</summary><pre>{JSON.stringify({existing:row.existing,incoming:row.incoming,examples:row.incoming_examples},null,2)}</pre></details>}</td>
  <td data-label="Український відповідник">
   {value?.action==='create_name'?<input aria-label={`Український відповідник для ${row.name}`} value={value.name||''} placeholder="Введіть перевірену українську назву" maxLength={1000} onChange={e=>onChange({...value,name:e.target.value})}/>:value?.action==='target'?<>
    <select aria-label={`Наявний відповідник для ${row.name}`} value={value.target_id||''} onChange={e=>onChange({...value,target_id:e.target.value})}><option value="">Оберіть наявний запис</option>{value.target_id&&!candidates.some(c=>c.id===value.target_id)&&<option value={value.target_id}>Обраний запис</option>}{candidates.map(c=><option key={c.id} value={c.id}>{c.name} · {Object.values(c.details||{}).filter(Boolean).join(' / ')}</option>)}</select>
    {row.kind&&<details><summary>Знайти інший відповідник</summary><input aria-label={`Пошук відповідника для ${row.name}`} value={query} onChange={e=>setQuery(e.target.value)}/><button type="button" onClick={async()=>{try{setError('');const r=await api(`/catalogue/admin/entities?kind=${row.kind}&q=${encodeURIComponent(query)}${row.parent_id?`&parent_id=${row.parent_id}`:''}`);setCandidates(r.items);}catch(e){setError(errorText(e));}}}>Знайти</button></details>}
   </>:<span>{value?.action==='skip'?'Без зіставлення':value?actions[value.action]:'Оберіть тип рішення'}</span>}
   {error&&<p role="alert">{error}</p>}
  </td>
  <td data-label="Тип рішення"><select aria-label={`Рішення для ${row.name}`} value={value?.action||''} onChange={e=>onChange(e.target.value?{action:e.target.value,...(e.target.value==='create_name'?{name:row.suggested_name||row.name}:{})}:undefined)}><option value="">Оберіть рішення</option>{row.allowed_actions.map((a:string)=><option key={a} value={a}>{actions[a]||a}</option>)}</select></td>
  <td data-label="Статус"><span className={`catalogue-decision-status ${verified?'verified':''}`}>{status}</span></td>
 </tr>;
}
function DecisionTable({rows,state,onChange}:{rows:Row[];state:Review;onChange:(row:Row,v?:Decision)=>void}){
 return <table className="catalogue-decisions"><thead><tr><th>Початкова назва</th><th>Український відповідник</th><th>Тип рішення</th><th>Статус</th></tr></thead><tbody>{rows.map(r=><DecisionRow key={r.key} row={r} value={state.draft[r.key]} checked={showReport(state)?state.checked[r.key]:undefined} sent={state.pending?.sent[r.key]} onChange={v=>onChange(r,v)}/>)}</tbody></table>;
}
export default function CatalogueImport({enabled,actorKey}:{enabled:boolean;actorKey:string}){
 if(!enabled)return <section className="panel padded"><h1>Доступ обмежено</h1><p>Глобальний імпорт доступний тільки власнику платформи з серверного allowlist.</p></section>;
 return <ImportWorkspace key={actorKey} actorKey={actorKey}/>;
}
function ImportWorkspace({actorKey}:{actorKey:string}){
 const history=useLoad(()=>api('/catalogue/admin/jobs'),[]);
 const [state,setState]=useState<Review>(emptyReview),ref=useRef(state);
 const [busy,setBusy]=useState(false),[file,setFile]=useState<File|null>(null),[confirmed,setConfirmed]=useState<string|null>(null),[storageError,setStorageError]=useState('');
 const sending=useRef(false),generation=useRef(0),mounted=useRef(true);
 function persist(next:Review){
  if(!next.job)return;
  try{const raw=JSON.stringify(savedReview(next,actorKey));if(raw.length>4*1024*1024)throw Error('Draft limit');sessionStorage.setItem(draftKey(actorKey,next.job),raw);sessionStorage.setItem(lastKey(actorKey),next.job.id);setStorageError('');return true;}
  catch{setStorageError('Не вдалося зберегти чернетку на пристрої. Поля залишаються відкритими; не оновлюйте сторінку.');return false;}
 }
 function update(fn:(current:Review)=>Review){if(!mounted.current)return;const next=fn(ref.current);if(next===ref.current)return;ref.current=next;setState(next);persist(next);setConfirmed(null);}
 async function load(id:string){
  const ticket=++generation.current;
  try{
   const job=await api(`/catalogue/admin/jobs/${id}`);if(!mounted.current||ticket!==generation.current)return;
   let saved:Row|null=null,restoreError='';
   try{const raw=sessionStorage.getItem(draftKey(actorKey,job));if(raw){if(raw.length>4*1024*1024)throw Error();saved=JSON.parse(raw);}}
   catch{restoreError='Збережена чернетка пошкоджена або недоступна. Перевірте поля перед продовженням.';}
   update(()=>{const restored=openReview(job,saved,actorKey);return restoreError?{...restored,invalid:true,error:restoreError}:restored;});
  }catch(e){if(ticket===generation.current)update(s=>({...s,error:errorText(e)}));}
 }
 useEffect(()=>{
  mounted.current=true;
  try{const id=sessionStorage.getItem(lastKey(actorKey));if(id)void load(id);}catch{setStorageError('Сховище чернеток недоступне. Не оновлюйте сторінку з незбереженими полями.');}
  return ()=>{mounted.current=false;generation.current++;};
 },[actorKey]);
 const awaiting=!!state.pending||active(state.job);
 useEffect(()=>{
  if(!state.job||!awaiting||busy)return;
  let cancelled=false,timer:ReturnType<typeof setTimeout>;
  const id=state.job.id,expected=state.pending?.operationId;
  async function poll(){
   try{
    const job=await api(`/catalogue/admin/jobs/${id}`);if(cancelled)return;
    update(s=>s.job?.id!==id||(expected&&s.pending?.operationId!==expected)?s:reconcile(s,job));
    if(ref.current.pending||active(ref.current.job))timer=setTimeout(poll,1000);else history.reload();
   }catch(e){if(!cancelled){update(s=>({...s,error:`Не вдалося оновити статус: ${errorText(e)}. Введені поля залишаються у чернетці.`}));timer=setTimeout(poll,2000);}}
  }
  timer=setTimeout(poll,200);
  return ()=>{cancelled=true;clearTimeout(timer);};
 },[state.job?.id,state.pending?.operationId,state.job?.operation?.id,awaiting,busy]);
 async function request(kind:'preview'|'apply'){
  if(sending.current||awaiting||!ref.current.job||(kind==='apply'&&(!canApply(ref.current)||confirmed!==ref.current.job.preview_token)))return;
  generation.current++;sending.current=true;setBusy(true);const before=ref.current,id=before.job!.id;
  update(s=>begin(s,kind));
  try{
   const response=await api(`/catalogue/admin/jobs/${id}/${kind}`,'POST',kind==='preview'?{resolutions:ref.current.pending!.sent}:{preview_token:before.job!.preview_token,confirm:true});
   update(s=>accepted(s,response));
  }catch(e){
   update(s=>({...s,pending:e instanceof ApiError&&e.status>=400&&e.status<500?null:s.pending,invalid:true,error:errorText(e)}));
   try{const current=await api(`/catalogue/admin/jobs/${id}`);update(s=>reconcile(s,current));}catch{/* Preserve exact request error, draft and pending intent for polling. */}
  }finally{sending.current=false;setBusy(false);history.reload();}
 }
 function change(row:Row,value?:Decision){update(s=>({...editDecision(s,row.key,value),rows:s.rows.some(r=>r.key===row.key)?s.rows:[...s.rows,{...row,required:false}]}));}
 const job=state.job,report=job?.report,locked=busy||awaiting||job?.status==='applied';
 const required=state.rows.filter(r=>r.required!==false),filled=required.filter(r=>complete(state.draft[r.key])).length;
 const eligible=canApply(state)&&!busy;
 return <>
  <Heading eyebrow="АДМІНІСТРУВАННЯ → КАТАЛОГ" title="Імпорт глобального каталогу" description="Завантажте файл, перевірте відповідності та окремо підтвердьте застосування."/>
  <section className="panel padded"><label>Файл каталогу<input type="file" accept=".csv,.zip,.sqlite3,.gz" disabled={busy||awaiting} onChange={e=>setFile(e.target.files?.[0]||null)}/></label><p>CSV/ZIP Catalogue v2 або Aleto v1 SQLite/GZIP, до 16 MiB.</p>
   <button disabled={!file||busy||awaiting} onClick={async()=>{
    if(!file||sending.current)return;generation.current++;sending.current=true;setBusy(true);
    try{
     const before=csrf(),r=await fetch('/api/v1/catalogue/admin/jobs',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':before,'X-Catalogue-Filename':encodeURIComponent(file.name)},body:file});
     if(csrf()!==before)throw Error('Сесію змінено; оновіть сторінку');
     const body=await r.json();if(!r.ok){if(r.status===401)window.dispatchEvent(new Event('warehouse:logout'));if(r.status===403)window.dispatchEvent(new Event('warehouse:permissions-changed'));throw Error(typeof body.detail==='string'?body.detail:'Файл відхилено');}
     update(()=>openReview(body,null,actorKey));history.reload();
    }catch(e){update(s=>({...s,error:errorText(e)}));}finally{sending.current=false;setBusy(false);}
   }}>Завантажити файл</button>
  </section>
  {storageError&&<p role="alert" className="error">{storageError}</p>}
  {state.error&&<p role="alert" className="error">{state.error}</p>}
  {job&&<section className="panel padded catalogue-review"><h2>{job.filename}</h2><small className="catalogue-file-id">Job {job.id} · SHA-256: {job.file_sha256}</small>
   {awaiting?<div role="status"><h3>{active(job)?operationNames[job.operation.status]:'Очікує підтвердження сервера'}</h3><p>{(state.pending?.kind||job.operation?.kind)==='apply'?'Очікуємо підтвердження застосування. Повторне застосування не запускається.':'Рішення не втрачено. Очікуємо фактичний результат нової перевірки; попередній звіт приховано.'}</p>{active(job)&&<progress value={job.operation.progress?.done||0} max={job.operation.progress?.total||1}/>}</div>:state.notice&&<p role="status">{state.notice}</p>}
   <fieldset disabled={locked} className="catalogue-review-fields"><legend>Ручні відповідності</legend>
    {!!required.length&&<><p className="catalogue-review-progress">Підтверджено {filled} із {required.length}{!eligible&&' · чернетка, ще не підтверджена новим preview'}</p><DecisionTable rows={required} state={state} onChange={change}/></>}
    {!required.length&&<p>Немає обов’язкових відповідностей для ручного рішення.</p>}
    <div className="modal-actions"><button type="button" onClick={()=>{if(persist(ref.current))update(s=>({...s,notice:'Чернетку збережено в цій вкладці для цього файла й акаунта.'}));}}>Зберегти чернетку</button><button type="button" onClick={()=>request('preview')}>Перевірити рішення</button></div>
    <p>Чернетка зберігається автоматично в цій вкладці. {dirty(state)&&'Поля змінено — перед застосуванням потрібна нова перевірка.'}</p>
    {!awaiting&&!!report?.suggestion_total&&<details><summary>Рекомендації: нові записи ({report.suggestion_total}) — необов’язкова перевірка</summary><p>Переглядати всі нові записи не потрібно. Показано до 200 рекомендацій; вони не блокують імпорт.</p><DecisionTable rows={report.suggestions||[]} state={state} onChange={change}/></details>}
   </fieldset>
   {showReport(state)&&report?.counts&&<section aria-label="Актуальний результат перевірки"><h3>{job.status==='applied'?'Імпорт застосовано':job.status==='ready'?'Перевірку завершено: готово':'Перевірку завершено: потрібні рішення'}</h3><p>Рядків: {report.input_rows}; невирішених відповідностей: {report.unresolved_total}. {report.committed?'Дані застосовано.':'Каталог не змінено.'}</p><div className="table-wrap"><table><thead><tr><th>Сутність</th><th>Нові</th><th>Оновлені</th><th>Без змін</th></tr></thead><tbody>{Object.entries(report.counts).map(([k,v])=>{const c=v as Row;return <tr key={k}><td>{names[k]||k}</td><td>{c.inserted}</td><td>{c.updated}</td><td>{c.unchanged}</td></tr>;})}</tbody></table></div>{!!report.price_changes?.length&&<details><summary>Довідкові ціни: нові спостереження (перші 50)</summary><div className="table-wrap"><table><thead><tr><th>Артикул</th><th>Попередня UAH / USD</th><th>Нова UAH / USD</th><th>Дата</th></tr></thead><tbody>{report.price_changes.map((p:Row,i:number)=><tr key={i}><td>{p.source} · {p.source_article}</td><td>{p.previous_uah??'—'} / {p.previous_usd??'—'}</td><td>{p.price_uah??'—'} / {p.price_usd??'—'}</td><td>{p.observed_at}</td></tr>)}</tbody></table></div></details>}</section>}
   {eligible&&<section className="catalogue-apply"><label><input type="checkbox" checked={confirmed===job.preview_token} onChange={e=>setConfirmed(e.target.checked?job.preview_token:null)}/> Підтверджую застосування саме цього перевіреного preview до глобального каталогу</label>{confirmed===job.preview_token&&<button className="primary" onClick={()=>request('apply')}>Застосувати імпорт</button>}</section>}
   {!awaiting&&report?.issues_truncated&&<p>Показано перші 200 відповідностей. Після перевірки з’являться наступні, якщо вони є.</p>}
  </section>}
  <Heading eyebrow="ЗБЕРЕЖЕНІ РЕЗУЛЬТАТИ" title="Історія імпортів" description="Відкрийте файл, щоб відновити чернетку та перевірити фактичний стан операції."/>
  <State error={history.error} loading={history.loading}/><section className="panel padded">{history.data?.items.map((j:Row)=><p key={j.id}><button disabled={busy||awaiting} onClick={()=>load(j.id)}>{j.filename} · {j.operation?operationNames[j.operation.status]:j.status}</button></p>)}</section>
 </>;
}
