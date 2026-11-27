import {useContext,useEffect,useRef,useState} from 'react';
import {api,money,labels,type Row} from './api';
import {ReferenceQuickApply} from './ReferenceQuickApply';
import {pricesChanged} from './MarketPricing';
import {TeamIdentity,useCan} from './permissions';
import {Modal} from './components';
import './aleto-price-reference.css';

export default function AletoPriceButton({part,vehicle,onSaved,inline=false}:{part:Row;vehicle?:Row|null;onSaved?:(row:Row)=>void;inline?:boolean}){
 const can=useCan(),identity=useContext(TeamIdentity);
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[data,setData]=useState<Row|null>(null);
 const sequence=useRef(0),guard=useRef(false),dirty=useRef(false),visible=useRef(false),mounted=useRef(false);
 const [confirmed,setConfirmed]=useState<Row|null>(null);
 const scope=JSON.stringify([identity?.id,identity?.workspace_account_id,part.id,part.name,part.oem_number,part.article_number,part.condition,part.vehicle_id,vehicle?.id,vehicle?.manufacturer,vehicle?.model,vehicle?.year,vehicle?.generation,vehicle?.ktype]);
 // The list intentionally removes rows while reloading. A price dialog
 // nested in such a row must not trigger that reload until the user closes it.
 function flush(){if(dirty.current){dirty.current=false;pricesChanged();if(onSaved)void api('/parts/'+part.id).then(row=>{if(mounted.current)onSaved(row);}).catch(()=>{});}}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;visible.current=false;if(dirty.current){dirty.current=false;queueMicrotask(pricesChanged);}};},[]);
 useEffect(()=>{sequence.current++;guard.current=false;visible.current=false;setOpen(false);setBusy(false);setError('');setData(null);setConfirmed(null);return()=>{sequence.current++;if(dirty.current){dirty.current=false;queueMicrotask(pricesChanged);}};},[scope]);
 function committed(row:Row){
  if(!mounted.current||!visible.current){pricesChanged();return;}
  dirty.current=true;setConfirmed(row);
 }
 const allowed=can('inventory.view')&&can('catalog.view')&&can('market.check');
 function close(){sequence.current++;guard.current=false;visible.current=false;setBusy(false);setOpen(false);setData(null);setError('');setConfirmed(null);flush();}
 async function lookup(){
  if(guard.current||!allowed||!part.id)return;
  guard.current=true;const n=++sequence.current;
  visible.current=true;setOpen(true);setBusy(true);setError('');setData(null);
  try{const r=await api('/parts/'+encodeURIComponent(String(part.id))+'/market-reference','POST',{individual:true});if(sequence.current===n)setData(r);}
  catch(e){if(sequence.current===n)setError(e instanceof Error?e.message:'Не вдалося перевірити ціни');}
  finally{if(sequence.current===n){guard.current=false;setBusy(false);}}
 }
 if(!allowed||!part.id||part.catalogue_only)return null;
 const references:Row[]=data?.references||[];
 const historical:Row[]=data?.historical||[];
 const date=(value:string)=>new Date(value).toLocaleDateString('uk-UA',{timeZone:'Europe/Kyiv'});
 const panel=<div className="aleto-reference-panel">
    {vehicle&&<p>{[vehicle.manufacturer,vehicle.model,vehicle.year].filter(Boolean).join(' · ')}</p>}
    <p>{data?.price_mode==='live'?'Оновлені ринкові ціни.':data?.price_mode==='cached'?'Ринкові ціни з останньої перевірки.':'Орієнтовні ціни за збереженими даними. Наявність не перевірено.'} Сам пошук не змінює власну ціну.</p>
    {busy&&<p role="status">Шукаємо схожі пропозиції…</p>}
    {error&&<p role="alert">{error} <button type="button" onClick={lookup}>Повторити</button></p>}
    {data&&<div aria-live="polite">
     {data.truncated&&<p>Вибірку обмежено. Середня ціна не обчислюється.</p>}
     {data.lookup_status==='missing_oem'&&<p>Не вдалося уточнити номер деталі. Пошук за назвою доступний за наявності моделі.</p>}
     {data.lookup_status==='unavailable_or_limited'&&<p>Зовнішня перевірка тимчасово недоступна. Показано збережені дані, якщо вони є.</p>}
     {data.lookup_status==='missing_vehicle'&&<p>Для пошуку за назвою потрібні марка і модель автомобіля.</p>}
     {data.lookup_status==='busy'&&<p>Виконується інший зовнішній пошук. Повторіть пізніше.</p>}
     {data.lookup_status==='source_not_found'&&<p>У перевірених джерелах не знайдено сторінку запчастини.</p>}
     {data.lookup_status==='source_no_cards'&&<p>На сторінці цього OEM не виявлено товарних карток.</p>}
     {['robots_denied','robots_unavailable','source_access_denied','source_redirect'].includes(data.lookup_status)&&<p>Правила або відповідь джерела не дозволили виконати автоматичну перевірку.</p>}
     {['source_timeout','source_network_error','source_http_error'].includes(data.lookup_status)&&<p>Не вдалося отримати відповідь джерела. Повторіть пізніше.</p>}
     {['source_content_error','source_response_limit','source_parse_error'].includes(data.lookup_status)&&<p>Відповідь джерела не вдалося безпечно обробити. Ціну не вигадуємо.</p>}
     {data.lookup_status==='no_comparable'&&<p>У перевірених джерелах не знайдено порівнюваних пропозицій.</p>}
     {data.lookup_status==='disabled'&&<p>Зовнішній пошук не активовано.</p>}
     {!references.length&&!data.truncated&&<p>Немає доступних цінових орієнтирів для цієї деталі. <a href={'https://www.google.com/search?q='+encodeURIComponent([vehicle?.manufacturer||part.manufacturer,vehicle?.model||part.model,vehicle?.year,part.name,'ціна'].filter(Boolean).join(' '))} target="_blank" rel="noopener noreferrer">Перевірити за назвою в інтернеті</a></p>}
     {references.map((r,index)=><section className="aleto-reference-group" key={index}>
      <strong>Група {index+1} · {labels[r.condition]||'Стан невідомий'}</strong>
      <small>{r.match_basis==='name_model'?'Збіг за назвою та моделлю · сумісність не підтверджена':r.match_basis==='brand_oem'?'Точний номер і бренд · сумісність не підтверджена':r.match==='exact'?'Точний OEM та узгоджені ознаки':'Схожі деталі · сумісність не підтверджена'} · {labels[r.condition]||'Стан невідомий'} · {r.currency}{r.assembly==='complete'?' · У зборі':r.assembly==='bare'?' · Без комплектування':''}{r.availability==='available'?' · Наявність зазначена':r.availability==='unknown'?' · Наявність не підтверджена':''}</small>
      {r.average!=null?<><small>Середня ціна</small><strong className="aleto-reference-average">{money(r.average,r.currency)}</strong></>:<strong>{r.offer_count===1?'Ціна окремої пропозиції':'Мало пропозицій для середньої ціни'}</strong>}
      <p>{r.offer_count} пропозицій · {money(r.minimum,r.currency)} – {money(r.maximum,r.currency)}</p>
      <small>Останнє спостереження: {date(r.observed_at)}. Показано {r.examples.length} із {r.offer_count}.</small>
      {r.examples.map((e:Row,index:number)=><div className="aleto-reference-offer" key={index}><span>Ціна №{index+1}</span><strong>{money(e.amount,r.currency)}</strong><small>{date(e.observed_at)} {typeof e.reference_url==='string'&&/^https:\/\/((www\.)?aleto\.ua|autopalma\.parts)\//.test(e.reference_url)&&<a href={e.reference_url} target="_blank" rel="noopener noreferrer">{r.source_name==='AutoPalma'?'AutoPalma · першоджерело':'Переглянути першоджерело'}</a>}</small></div>)}
      </section>)}
     {historical.length>0&&<details><summary>Історичні пропозиції ({historical.length})</summary><p>Старі спостереження не враховано в середній ціні.</p>{historical.map((e,index)=><p key={index}>{money(e.amount,e.currency)} · {date(e.observed_at)}</p>)}</details>}
    </div>}
    {can('parts.change_price')&&!part.archived&&<ReferenceQuickApply key={scope} part={confirmed||part} groups={references} token={data?.price_token} truncated={data?.truncated} onSaved={committed}/>}
   </div>;
 return <div className={'aleto-reference-action'+(inline?' reference-inline':'')} onClick={e=>e.stopPropagation()}>
  {inline&&<strong>Уточнення цін</strong>}
  <button type="button" className="secondary aleto-reference-button" aria-label={'Дізнатися ціни '+part.name} disabled={busy} onClick={lookup}>{busy?'Пошук цін…':open&&inline?'Оновити орієнтири':'Дізнатися ціни'}</button>
  {open&&(inline?<><button type="button" className="secondary" onClick={close}>Згорнути орієнтири</button>{panel}</>:<Modal title={'Орієнтир цін · '+part.name} onClose={close}>{panel}</Modal>)}
 </div>;
}
