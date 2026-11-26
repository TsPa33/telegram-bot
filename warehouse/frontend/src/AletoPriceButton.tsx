import {useContext,useEffect,useRef,useState} from 'react';
import {api,money,labels,type Row} from './api';
import {TeamIdentity,useCan} from './permissions';
import {Modal} from './components';
import './aleto-price-reference.css';

export default function AletoPriceButton({part,vehicle}:{part:Row;vehicle?:Row|null}){
 const can=useCan(),identity=useContext(TeamIdentity);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[data,setData]=useState<Row|null>(null);
 const sequence=useRef(0),guard=useRef(false);
 const scope=JSON.stringify([identity?.id,identity?.workspace_account_id,part.id,part.name,part.oem_number,part.article_number,part.condition,part.vehicle_id,vehicle?.id,vehicle?.manufacturer,vehicle?.model,vehicle?.year,vehicle?.generation,vehicle?.ktype]);
 useEffect(()=>{sequence.current++;guard.current=false;setOpen(false);setBusy(false);setError('');setData(null);return()=>{sequence.current++;};},[scope]);
 const allowed=can('inventory.view')&&can('catalog.view')&&can('market.check');
 function close(){sequence.current++;guard.current=false;setBusy(false);setOpen(false);setData(null);setError('');}
 async function lookup(){
  if(guard.current||!allowed||!part.id)return;
  guard.current=true;const n=++sequence.current;
  setOpen(true);setBusy(true);setError('');setData(null);
  try{const r=await api('/parts/'+encodeURIComponent(String(part.id))+'/market-refresh','POST',{});if(sequence.current===n)setData(r);}
  catch(e){if(sequence.current===n)setError(e instanceof Error?e.message:'Не вдалося перевірити ціни');}
  finally{if(sequence.current===n){guard.current=false;setBusy(false);}}
 }
 if(!allowed||!part.id)return null;
 const references:Row[]=data?.guidance?.aleto_reference||[];
 const historical:Row[]=(data?.offers||[]).filter((e:Row)=>e.status==='historical_not_recommendation');
 const date=(value:string)=>new Date(value).toLocaleDateString('uk-UA',{timeZone:'Europe/Kyiv'});
 return <div className="aleto-reference-action" onClick={e=>e.stopPropagation()}>
  <button type="button" className="secondary aleto-reference-button" aria-label={'Дізнатися ціни '+part.name} disabled={busy} onClick={lookup}>{busy?'Пошук цін…':'Дізнатися ціни'}</button>
  {open&&<Modal title={'Орієнтир цін · '+part.name} onClose={close}>
   <div className="aleto-reference-panel">
    {vehicle&&<p>{[vehicle.manufacturer,vehicle.model,vehicle.year].filter(Boolean).join(' · ')}</p>}
    <p>Джерело: імпортований каталог Aleto. Не ціни в реальному часі. Власна ціна не змінюється.</p>
    {busy&&<p role="status">Шукаємо схожі пропозиції…</p>}
    {error&&<p role="alert">{error} <button type="button" onClick={lookup}>Повторити</button></p>}
    {data&&<div aria-live="polite">
     {data.guidance?.truncated&&<p>Вибірку обмежено. Середня ціна не обчислюється.</p>}
     {!references.length&&!data.guidance?.truncated&&<p>Немає достатніх актуальних імпортованих даних для орієнтира.</p>}
     {references.map(r=><section className="aleto-reference-group" key={[r.currency,r.condition,r.match].join(':')}>
      <small>{r.match==='exact'?'Точний OEM та узгоджені ознаки':'Схожі деталі · сумісність не підтверджена'} · {labels[r.condition]||'Стан невідомий'} · {r.currency}</small>
      {r.average!=null?<><small>Середня ціна</small><strong className="aleto-reference-average">{money(r.average,r.currency)}</strong></>:<strong>Мало пропозицій для середньої ціни</strong>}
      <p>{r.offer_count} пропозицій · {money(r.minimum,r.currency)} – {money(r.maximum,r.currency)}</p>
      <small>Останнє спостереження: {date(r.observed_at)}. Показано {r.examples.length} із {r.offer_count}.</small>
      {r.examples.map((e:Row)=><div className="aleto-reference-offer" key={e.article}><a href={e.url} target="_blank" rel="noopener noreferrer">Пропозиція {e.article}</a><strong>{money(e.amount,r.currency)}</strong><small>{date(e.observed_at)}{e.oem?' · OEM '+e.oem:''}</small></div>)}
     </section>)}
     {historical.length>0&&<details><summary>Історичні пропозиції ({historical.length})</summary><p>Старі спостереження не враховано в середній ціні.</p>{historical.map(e=><p key={[e.source,e.article,e.currency].join(':')}><a href={e.url} target="_blank" rel="noopener noreferrer">{money(e.amount,e.currency)}</a> · {date(e.observed_at)}</p>)}</details>}
     <a href="https://aleto.ua/" target="_blank" rel="noopener noreferrer">Відкрити Aleto для актуальної ручної перевірки</a>
    </div>}
   </div>
  </Modal>}
 </div>;
}
