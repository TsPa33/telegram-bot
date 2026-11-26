import {useContext,useEffect,useRef,useState} from 'react';
import {api,ApiError,money,labels,type Row} from './api';
import {TeamIdentity} from './permissions';
import {pricesChanged,SellerPriceEditor} from './MarketPricing';
import {cents,formatCents,singleOptions,defaultSingleOption} from './priceReferencePolicy';

export function ReferenceQuickApply({part,groups,token,truncated=false,onSaved}:{part:Row;groups:Row[];token?:string;truncated?:boolean;onSaved?:(row:Row)=>void}){
 const identity=useContext(TeamIdentity),key='warehouse.reference-single.v1:'+JSON.stringify([identity?.id,identity?.workspace_account_id||identity?.id,part.id]);
 const options=singleOptions(groups,truncated||!token),signature=JSON.stringify([key,token,options]);
 const [selected,setSelected]=useState(''),[amount,setAmount]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[manual,setManual]=useState(false),[done,setDone]=useState(false);
 const guard=useRef(false);
 function pending(){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
 const stored=pending(),choice=options.find(o=>o.key===selected),group=choice?groups[choice.group]:null;
 useEffect(()=>{
  const initial=defaultSingleOption(groups,part,options),option=options.find(o=>o.key===initial);
  setSelected(initial);setAmount(option?.amount||'');setDone(false);setError('');setManual(false);
 },[signature]);
 function pick(value:string){const o=options.find(x=>x.key===value);setSelected(value);setAmount(o?.amount||'');setDone(false);}
 const value=cents(amount.replace(',','.').trim()),valid=!!choice&&value!==null&&value>0n&&!!token;
 async function save(){
  if(guard.current||(!stored&&!valid))return;guard.current=true;setBusy(true);setError('');
  try{
   const body=pending()||{selling_price:formatCents(value!),currency:choice!.currency,expected_token:token,request_key:crypto.randomUUID()};
   sessionStorage.setItem(key,JSON.stringify(body));
   await api('/parts/'+part.id+'/price','PATCH',body);
   sessionStorage.removeItem(key);setDone(true);pricesChanged();
   if(onSaved){try{onSaved(await api('/parts/'+part.id));}catch{/* confirmed write; refresh event emitted */}}
  }catch(e){if(e instanceof ApiError&&e.status<500&&![401,403].includes(e.status))sessionStorage.removeItem(key);setError(e instanceof ApiError&&e.status===409?'Ціна або дані змінилися. Повторіть пошук.':(e as Error).message);}
  finally{guard.current=false;setBusy(false);}
 }
 return <section className="reference-single-editor" aria-label="Встановлення ціни">
  <div className="reference-current"><span>Поточна ціна</span><strong>{part.selling_price==null?'Не встановлено':money(part.selling_price,part.currency||'UAH')}</strong></div>
  {done?<p role="status">Ціну встановлено</p>:stored?<button className="primary" type="button" disabled={busy} onClick={()=>void save()}>Перевірити запис {money(stored.selling_price,stored.currency)}</button>:<>
   {options.length>0&&<>
    <label>Ціновий орієнтир<select aria-label="Вибрати ціновий орієнтир" value={selected} disabled={busy} onChange={e=>pick(e.target.value)}>
     <option value="">Оберіть ціну</option>
     {groups.map((g,i)=>options.some(o=>o.group===i)&&<optgroup key={i} label={'Група '+(i+1)+' · '+(labels[g.condition]||'Стан невідомий')+' · '+g.currency+' · '+(g.match==='exact'?'точний OEM':'схожі деталі')}>
      {options.filter(o=>o.group===i).map(o=><option value={o.key} key={o.key}>{o.label} · {money(o.amount,o.currency)}</option>)}
     </optgroup>)}
    </select></label>
    {choice&&<><div className="reference-price-picks">{options.filter(o=>o.group===choice.group&&!o.key.includes(':offer-')).map(o=><button key={o.key} type="button" className="secondary" aria-pressed={o.key===selected} disabled={busy} onClick={()=>pick(o.key)}><small>{o.label}</small><strong>{money(o.amount,o.currency)}</strong></button>)}</div>
     <label>Моя ціна ({choice.currency})<input aria-label="Встановити власну ціну" inputMode="decimal" value={amount} disabled={busy} onChange={e=>setAmount(e.target.value)}/></label>
     {group?.match==='similar'&&<small>Схожа деталь: сумісність не підтверджено.</small>}
     {group?.condition!==part.condition&&<small>Стан пропозиції відрізняється від стану вашої деталі.</small>}
     {choice.key.includes(':offer-')&&<small>Ціна окремої пропозиції, не середня ринкова ціна.</small>}
     {part.currency&&choice.currency!==part.currency&&<small>Зміна валюти на {choice.currency}; автоматичного перерахунку немає.</small>}
     <button className="primary reference-apply-button" type="button" disabled={busy||!valid} onClick={()=>void save()}>{busy?'Збереження…':(part.selling_price!=null?'Замінити на ':'Встановити ')+(valid?money(formatCents(value!),choice.currency):'ціну')}</button>
    </>}
   </>}
   {!options.length&&<small>Немає доступного орієнтира для встановлення. Власну ціну можна вказати вручну.</small>}
   <button type="button" className="secondary" disabled={busy} onClick={()=>setManual(v=>!v)}>Редагувати вручну</button>
   {manual&&<SellerPriceEditor part={part} initialOpen onSaved={row=>{setDone(true);setManual(false);onSaved?.(row);}}/>}
  </>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
