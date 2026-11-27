import {useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';

const base='/admin/aleto-worker';
type ResultQuery={q:string;sort:string;direction:string};
const actions:Record<string,Record<string,string>>={
 queued:{pause:'Пауза',cancel:'Скасувати'},
 paused:{resume:'Продовжити',cancel:'Скасувати'},
 failed:{retry:'Повторити'},
 needs_clarification:{cancel:'Скасувати'},
 completed:{refresh:'Оновити ціни'},
 partial:{refresh:'Повторити збір'},
};

export default function AletoWorkerPanel({onPrepared,permissions}:{onPrepared?:(id:string)=>void;permissions:string[]}){
 const manage=permissions.includes('catalog_parser_manage');
 const admin=permissions.includes('catalog_parser_admin');
 const publish=permissions.includes('catalog_parser_publish')&&Boolean(onPrepared);
 const [jobs,setJobs]=useState<Row[]>([]),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [vin,setVin]=useState(''),[make,setMake]=useState(''),[model,setModel]=useState('');
 const [year,setYear]=useState(''),[generation,setGeneration]=useState(''),[busy,setBusy]=useState(false);
 const [oracle,setOracle]=useState<Row|null>(null);
 const [result,setResult]=useState<{id:number;rows:Row[];offset:number;next:number|null;query:ResultQuery}|null>(null);
 const [filter,setFilter]=useState('');
 const [sort,setSort]=useState('source_order'),[direction,setDirection]=useState('asc');
 const [report,setReport]=useState<{id:number;offset:number;data:Row}|null>(null);
 const [exportState,setExport]=useState<{job:number;id:string;status:string;count?:number}|null>(null);
 const importRequest=useRef<AbortController|null>(null);
 useEffect(()=>()=>importRequest.current?.abort(),[]);
 async function loadResults(id:number,offset=0,query:ResultQuery={q:filter,sort,direction}){
  const params=new URLSearchParams({...query,offset:String(offset)});
  const data=await api(base+'/jobs/'+id+'/results?'+params);
  setResult({id,rows:data.items,offset,next:data.next_offset,query});
 }
 async function loadReport(id:number,offset=0,signal?:AbortSignal){
  const data=await api(base+'/jobs/'+id+'/prepare?offset='+offset,'GET',undefined,undefined,{signal});
  setReport({id,offset,data});
  return data;
 }
 async function prepare(id:number){
  const controller=new AbortController();
  importRequest.current=controller;
  try{
   let data=await loadReport(id,0,controller.signal);
   while(!data.done&&!controller.signal.aborted){
    data=await api(base+'/jobs/'+id+'/prepare','POST',{cursor:data.cursor},undefined,{signal:controller.signal});
    setReport(previous=>previous&&({...previous,data:{...previous.data,...data}}));
   }
   if(!controller.signal.aborted)await loadReport(id,0,controller.signal);
   window.dispatchEvent(new Event('warehouse:catalogue-admin-changed'));
  }catch(error){if(!controller.signal.aborted)throw error;}
  finally{importRequest.current=null;}
 }
 const exportJob=exportState?.job,exportId=exportState?.id,exportStatus=exportState?.status;
 useEffect(()=>{
  if(exportJob==null||!exportId||exportStatus!=='queued')return;
  const controller=new AbortController();
  let timer:number;
  async function poll(){
   try{
    const state=await api(base+'/jobs/'+exportJob+'/exports/'+exportId,'GET',undefined,undefined,{signal:controller.signal});
    if(controller.signal.aborted)return;
    if(state.status!=='queued'){
     setExport(previous=>previous&&({...previous,status:state.status,count:state.row_count}));
     return;
    }
   }catch(error){
    if(!controller.signal.aborted)setNotice((error as Error).message);
   }
   if(!controller.signal.aborted)timer=window.setTimeout(poll,2000);
  }
  void poll();
  return()=>{controller.abort();window.clearTimeout(timer);};
 },[exportJob,exportId,exportStatus]);
 useEffect(()=>{
  let active=true,timer:number;
  const controller=new AbortController();
  async function poll(){
   try{
    const data=await api(base+'/jobs','GET',undefined,undefined,{signal:controller.signal});
    if(active){setJobs(data.items);setError('');}
   }catch(e){if(active)setError((e as Error).message);}
   if(active)timer=window.setTimeout(poll,5000);
  }
  void poll();
  return()=>{active=false;controller.abort();window.clearTimeout(timer);};
 },[]);
 async function act(run:()=>Promise<void>){
  setBusy(true);setNotice('');
  try{await run();}catch(e){setNotice((e as Error).message);}finally{setBusy(false);}
 }
 async function post(path:string,body?:unknown){
  const job=await api(base+path,'POST',body);
  setJobs(old=>[job,...old.filter(item=>item.id!==job.id)].sort((a,b)=>b.id-a.id));
 }
 return <section className="pa-panel" aria-label="Завдання Aleto Worker">
  <h2>Aleto Worker</h2>
  {error&&<p role="status">{error}</p>}
  <form onSubmit={e=>{e.preventDefault();void act(()=>post('/jobs',{manufacturer:make,model,year:year?Number(year):null,generation}));}}>
   <fieldset disabled={busy||!manage}>
    <div className="pa-fields">
     <label>VIN<input maxLength={17} value={vin} onChange={e=>{setVin(e.target.value);setOracle(null);}}/></label>
     <button type="button" disabled={!vin.trim()} onClick={()=>void act(async()=>{
      const decoded=await api(base+'/vin','POST',{vin});
      setOracle(decoded.oracle);
      setMake(decoded.vehicle.manufacturer||'');setModel(decoded.vehicle.model||'');
      setYear(decoded.vehicle.year||'');setGeneration(decoded.vehicle.generation||'');
      setNotice(decoded.status==='NOT_IDENTIFIED'?'Введіть марку й модель вручну.':'Перевірте характеристики перед створенням завдання.');
     })}>Декодувати VIN</button>
     <label>Марка<input required maxLength={100} value={make} onChange={e=>setMake(e.target.value)}/></label>
     <label>Модель<input required maxLength={100} value={model} onChange={e=>setModel(e.target.value)}/></label>
     <label>Рік<input type="number" min={1886} max={2100} value={year} onChange={e=>setYear(e.target.value)}/></label>
     <label>Покоління<input maxLength={100} value={generation} onChange={e=>setGeneration(e.target.value)}/></label>
    </div>
    <button type="submit" disabled={Boolean(error)}>Знайти каталог Aleto</button>
   </fieldset>
  </form>
  {oracle&&oracle.items?.length>0&&<details><summary>Кандидати модифікацій Oracle</summary><ul>
   {oracle.items.map((item:Row,i:number)=><li key={i}>{item.manufacturer} {item.model} · {item.modification} · #{item.source_modification_id}</li>)}
  </ul></details>}
  {notice&&<p role="status">{notice}</p>}
  {jobs.map(job=><article key={job.id}>
   <h3>{job.manufacturer} {job.model} {job.year}</h3>
   <p>#{job.id} · {job.status} · Сторінок: {job.pages.done??0} оброблено, {job.pages.queued??0} у черзі · Пропозицій: {job.unique_articles} · З OEM: {job.with_oem} · З ціною: {job.with_price} · Помилки: {job.page_issues+(job.pages.failed??0)}</p>
   {job.progress&&<p>Початок: {new Date(job.progress.started_at).toLocaleString('uk-UA')} · Остання активність: {new Date(job.progress.activity_at).toLocaleString('uk-UA')}{job.status==='queued'&&job.progress.current_page&&' · '+job.progress.current_page}</p>}
   {job.error&&<p>{job.error}</p>}
   {manage&&job.status==='needs_clarification'&&job.candidates.map((url:string)=><button key={url} disabled={busy} onClick={()=>void act(()=>post('/jobs/'+job.id+'/command',{action:'choose',url}))}>{url}</button>)}
   <div className="pa-actions">
    {manage&&Object.entries(actions[job.status]||{}).map(([action,label])=><button key={action} disabled={busy} onClick={()=>void act(()=>post('/jobs/'+job.id+'/command',{action}))}>{label}</button>)}
    {admin&&job.status==='completed'&&<button disabled={busy} onClick={()=>void act(()=>post('/jobs/'+job.id+'/command',{action:job.scheduled?'unschedule':'schedule'}))}>
     {job.scheduled?'Вимкнути щоденне оновлення':'Оновлювати щодня'}
    </button>}
    {job.unique_articles>0&&<button disabled={busy} onClick={()=>void act(()=>loadResults(job.id))}>Показати пропозиції</button>}
    {publish&&job.status==='completed'&&job.unique_articles>0&&<>
     <button disabled={busy} onClick={()=>void act(()=>prepare(job.id))}>Підготувати / продовжити імпорт</button>
     <button disabled={busy} onClick={()=>void act(async()=>{await loadReport(job.id);})}>Звіт імпорту</button>
    </>}

   </div>
  </article>)}
  {result&&<div>
   <h3>Пропозиції завдання #{result.id}</h3>
   <form onSubmit={e=>{e.preventDefault();void act(()=>loadResults(result.id));}}>
    <label>Пошук<input maxLength={160} value={filter} onChange={e=>setFilter(e.target.value)}/></label>
    <label>Сортування<select value={sort} onChange={e=>setSort(e.target.value)}>
     <option value="source_order">Порядок збору</option><option value="part_name">Назва</option>
     <option value="source_article">Артикул</option><option value="price_uah">Ціна UAH</option>
     <option value="price_usd">Ціна USD</option><option value="observed_at">Дата перевірки</option>
    </select></label>
    <label>Напрямок<select value={direction} onChange={e=>setDirection(e.target.value)}>
     <option value="asc">За зростанням</option><option value="desc">За спаданням</option>
    </select></label>
    <button disabled={busy}>Застосувати</button>
   </form>
   <div className="pa-actions">
    <button disabled={busy||!result.offset} onClick={()=>void act(()=>loadResults(result.id,result.offset-50,result.query))}>Попередня сторінка</button>
    <button disabled={busy||result.next===null} onClick={()=>void act(()=>loadResults(result.id,result.next??0,result.query))}>Наступна сторінка</button>
    <button disabled={busy} onClick={()=>void act(async()=>{
     const data=await api(base+'/jobs/'+result.id+'/exports','POST',result.query);
     setExport({job:result.id,id:data.id,status:'queued'});
    })}>Підготувати повний CSV</button>
   </div>
   {exportState?.job===result.id&&<p role="status">{exportState.status==='ready'?
    <a href={'/api/v1'+base+'/jobs/'+result.id+'/exports/'+exportState.id+'/download'}>Завантажити CSV ({exportState.count} записів)</a>:
    exportState.status==='failed'?'Помилка підготовки CSV':'CSV готується'}</p>}
   <ul>{result.rows.map((row,i)=><li key={i}>
    {row.part_name} · {row.category} / {row.subcategory} · {row.source_article} · {row.oem||'OEM відсутній'} · {row.price_uah?row.price_uah+' грн':row.price_usd?row.price_usd+' USD':'Ціна відсутня'}
    {/^https:\/\/(?:www\.)?aleto\.ua\//.test(row.source_url)&&<> · <a href={row.source_url} target="_blank" rel="noreferrer">Картка Aleto</a></>}
   </li>)}</ul>
  </div>}
  {report&&<div>
   <h3>Звіт імпорту #{report.id}</h3>
   <p role="status">{report.data.done?'Підготовку завершено':'Підготовку можна продовжити'} · Записів: {report.data.seen} · Відхилено: {report.data.rejected}</p>
   {busy&&<button onClick={()=>importRequest.current?.abort()}>Призупинити підготовку</button>}
   {report.data.batches.map((batch:Row)=><details key={batch.start_cursor}>
    <summary>Пакет {batch.end_cursor} · {batch.entries.length} записів · {batch.status??'Відхилено'}</summary>
    {batch.catalogue_job_id&&<button onClick={()=>onPrepared?.(batch.catalogue_job_id)}>Відкрити preview пакета</button>}
    <ul>{batch.entries.map((entry:Row)=><li key={entry.id}>#{entry.id} · {entry.article} · {entry.status==='prepared'?'Підготовлено':'Відхилено'+(entry.fields?.length?' · '+entry.fields.map((field:string[])=>field.join('.')).join(', '):'')}</li>)}</ul>
   </details>)}
   <button disabled={busy||!report.offset} onClick={()=>void act(async()=>{await loadReport(report.id,report.offset-10);})}>Попередні пакети</button>
   <button disabled={busy||report.data.next_offset===null} onClick={()=>void act(async()=>{await loadReport(report.id,report.data.next_offset);})}>Наступні пакети</button>
  </div>}

 </section>;
}
