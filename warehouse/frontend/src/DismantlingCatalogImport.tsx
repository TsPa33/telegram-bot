import {useState} from "react";
import {api,type Row} from "./api";

type ImportPreview={created:number;updated:number;total:number;dry_run?:boolean};
export default function DismantlingCatalogImport({onImported}: {onImported:()=>void}) {
 const [payload,setPayload]=useState<Row|null>(null);
 const [filename,setFilename]=useState('');
 const [rights,setRights]=useState(false);
 const [preview,setPreview]=useState<ImportPreview|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [confirmed,setConfirmed]=useState(false);
 const count=Array.isArray(payload?.types)?payload.types.length:0;
 const modelLinks=Array.isArray(payload?.types)?payload.types.reduce((n:number,t:Row)=>n+(Array.isArray(t.applicability)?t.applicability.length:0),0):0;
 async function readFile(file?:File){
  setPayload(null);setFilename('');setPreview(null);setConfirmed(false);setError('');setMessage('');
  if(!file)return;
  try{
   if(file.size>5*1024*1024)throw Error('Файл завеликий: максимум 5 МБ.');
   const result=JSON.parse(await file.text());
   if(!result||Array.isArray(result)||typeof result!=='object'||!Array.isArray(result.types)||!result.types.length)throw Error('Невірний JSON. Потрібен файл із переліком types.');
   setPayload(result);setFilename(file.name);
  }catch(e){setError(e instanceof Error?e.message:'Не вдалося прочитати файл.');}
 }
 async function submit(dry:boolean){
  if(!payload||!rights||busy||(!dry&&(!preview||!confirmed)))return;
  setBusy(true);setError('');setMessage('');
  try{
   const result=await api('/dismantling/catalog/import?dry_run='+dry,'POST',{...payload,rights_confirmed:true}) as ImportPreview;
   if(dry){setPreview(result);setConfirmed(false);}
   else{
    setMessage(`Готово: додано ${result.created}, оновлено ${result.updated}. Для вже створеного автомобіля перевірте оновлення плану розбору.`);
    setPreview(null);setConfirmed(false);onImported();
   }
  }catch(e){setError(e instanceof Error?e.message:'Не вдалося виконати імпорт.');}
  finally{setBusy(false);}
 }
 return <div className="catalogue-own-import">
  <div className="catalogue-own-form">
   <label htmlFor="catalogue-own-file">Файл довідника (.json)</label>
   <input id="catalogue-own-file" type="file" accept=".json,application/json" disabled={busy} onChange={e=>void readFile(e.target.files?.[0])}/>
   {filename&&<div className="catalogue-own-file-summary" role="status">
    <strong>{filename}</strong>
    <span>{count.toLocaleString('uk-UA')} типів деталей · {modelLinks.toLocaleString('uk-UA')} прив’язок до моделей</span>
   </div>}
   <label className="catalogue-own-rights"><input type="checkbox" checked={rights} disabled={busy} onChange={e=>{setRights(e.target.checked);setPreview(null);setConfirmed(false);}}/>
    <span>Підтверджую право використовувати ці дані.</span>
   </label>
   <button type="button" className="primary" disabled={busy||!payload||!rights} onClick={()=>void submit(true)}>
    {busy?'Перевіряємо…':'Перевірити файл'}
   </button>
  </div>
  {preview&&<section className="catalogue-own-preview" aria-label="Результат перевірки" role="status">
   <h3>Результат перевірки</h3>
   <div className="catalogue-own-stats"><span><strong>{preview.created}</strong>Нових</span><span><strong>{preview.updated}</strong>Оновляться</span><span><strong>{preview.total}</strong>Усього в джерелі</span></div>
   <p>Перевірка завершена. Складські залишки, продажі й ціни не змінюються.</p>
   <label className="catalogue-own-rights"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
    <span>Перевірив результат і підтверджую оновлення довідника.</span>
   </label>
   <button type="button" className="primary" disabled={busy||!confirmed} onClick={()=>void submit(false)}>Додати до каталогу</button>
  </section>}
  {message&&<p className="catalogue-own-success" role="status">{message}</p>}
  {error&&<p role="alert" className="error">{error}</p>}
  <details className="catalogue-own-help">
   <summary>Формат файлу й особливості імпорту</summary>
   <p>Підтримується JSON із типами деталей та необов’язковими прив’язками до моделей. Максимальний розмір — 5 МБ. Без прив’язок типи будуть доступні для всіх марок.</p>
   <p>Імпорт не створює залишків та не змінює існуючі складські позиції. Для застосування оновлень до вже створеного плану скористайтеся оновленням списку автомобіля.</p>
  </details>
 </div>;
}
