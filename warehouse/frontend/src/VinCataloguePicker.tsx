import {useEffect,useState} from 'react';
import {api} from './api';

export type CatalogueCandidate={
  source_modification_id:number;
  model_id:number;
  manufacturer_id:number;
  source_snapshot_sha:string;
  manufacturer:string;
  model:string;
  generation:string;
  modification:string;
  type_count:number;
  coverage:string;
  model_matches:boolean;
  vin_fitment_verified:false;
};

type CandidatePage={items:CatalogueCandidate[];next_after:number|null;search_complete:boolean};
type Props={
  manufacturer:string;
  model:string;
  selectedId:number|null;
  onSelect:(item:CatalogueCandidate|null)=>void;
};

export default function VinCataloguePicker({manufacturer,model,selectedId,onSelect}:Props){
  const [items,setItems]=useState<CatalogueCandidate[]>([]);
  const [cursor,setCursor]=useState<number|null>(null);
  const [choice,setChoice]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [searched,setSearched]=useState(false);
  const normalized=manufacturer.trim();
  useEffect(()=>{
    setItems([]);setCursor(null);setChoice('');setError('');setSearched(false);
    if(normalized.length<2)return;
    let alive=true;
    const timer=window.setTimeout(async()=>{
      setBusy(true);
      try{
        const result=await api<CandidatePage>('/vehicles/vin/catalogue-candidates?manufacturer='+encodeURIComponent(normalized)+'&model='+encodeURIComponent(model));
        if(alive){setItems(result.items);setCursor(result.next_after);setSearched(true)}
      }catch(e){if(alive){setError((e as Error).message);setSearched(true)}}
      finally{if(alive)setBusy(false)}
    },350);
    return()=>{alive=false;window.clearTimeout(timer)};
    // Refresh after a make change, not a model selection; selection may correct
    // VIN's chassis label into an explicit model without resetting the list.
  },[normalized]);
  async function loadMore(){
    if(busy||cursor===null)return;
    setBusy(true);setError('');
    try{
      const result=await api<CandidatePage>('/vehicles/vin/catalogue-candidates?manufacturer='+
        encodeURIComponent(normalized)+'&model='+encodeURIComponent(model)+'&after='+cursor);
      setItems(before=>[...new Map([...before,...result.items].map(v=>[v.source_modification_id,v])).values()]);
      setCursor(result.next_after);
    }catch(e){setError((e as Error).message)}
    finally{setBusy(false)}
  }
  const sorted=[...items].sort((a,b)=>{
    const n=(s:string)=>s.normalize('NFKC').toLocaleLowerCase('uk').replace(/[^\p{L}\p{N}]/gu,'');
    const hint=n(model);
    const aMatch=hint.length>0&&(n(a.model)===hint||n(a.model).startsWith(hint));
    const bMatch=hint.length>0&&(n(b.model)===hint||n(b.model).startsWith(hint));
    return Number(bMatch)-Number(aMatch)||a.model.localeCompare(b.model,'uk')||a.modification.localeCompare(b.modification,'uk');
  });
  const current=items.find(v=>String(v.source_modification_id)===choice);
  const selected=items.find(v=>v.source_modification_id===selectedId);
  return <fieldset className="vin-catalogue-select" aria-label="Точна модифікація з каталогу">
    <legend>Модифікація з каталогу CarPot</legend>
    <p>Оберіть конкретну модифікацію, якщо VIN не визначив її однозначно. Пошук доступний для всіх марок, представлених у каталозі.</p>
    {busy&&<small role="status">Шукаємо модифікації…</small>}
    <label>Доступні модифікації
      <select aria-label="Вибрати каталожну модифікацію" value={choice} disabled={busy||!items.length} onChange={e=>setChoice(e.target.value)}>
        <option value="">Оберіть модель та модифікацію</option>
        {sorted.map(item=><option key={item.source_modification_id} value={item.source_modification_id}>
          {item.manufacturer} {item.model} {item.generation||''} — {item.modification} · {item.type_count} типів
        </option>)}
      </select>
    </label>
    {current&&<p role="status">Обрано: {current.model} — {current.modification}. Каталог: {current.type_count} типів, {current.coverage==='partial'?'часткове покриття':'повноту потрібно перевірити'}. Це вибір за даними користувача, а не підтвердження сумісності за VIN.</p>}
    {current&&<button type="button" disabled={busy} onClick={()=>onSelect(current)}>Підтвердити вибір модифікації</button>}
    {selected&&<p className="vin-catalogue-confirmed" role="status">Вибір збережено у формі: {selected.model} — {selected.modification}. Каталог буде прикріплено після додавання автомобіля.</p>}
    {searched&&!items.length&&!busy&&!error&&<small>У переглянутій частині джерела модифікацій цієї марки немає. Можна продовжити пошук або додати автомобіль із базовим каталогом.</small>}
    {cursor!==null&&<button type="button" disabled={busy} onClick={()=>void loadMore()}>Шукати далі у каталозі</button>}
    {searched&&cursor===null&&<small>Перегляд доступних каталожних записів завершено. Відсутність модифікації не означає, що автомобіль не існує.</small>}
    {error&&<small role="alert">Каталог тимчасово недоступний: {error}. VIN і ручне додавання залишаються доступними.</small>}
  </fieldset>;
}
