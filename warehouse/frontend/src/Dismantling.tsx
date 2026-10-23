import { useEffect, useRef, useState } from "react";
import { api, type Row } from "./api";
import { Confirm, State, useLoad } from "./shared";
import DismantlingCatalogImport from "./DismantlingCatalogImport";

function Selection({label,total,included,disabled,onChange}:{label:string;total:number;included:number;disabled:boolean;onChange:(value:boolean)=>void}) {
  const ref=useRef<HTMLInputElement>(null);
  const [pending,setPending]=useState<boolean|null>(null);
  useEffect(()=>setPending(null),[included,total]);
  useEffect(()=>{if(!disabled)setPending(null);},[disabled]);
  useEffect(()=>{if(ref.current)ref.current.indeterminate=pending===null&&included>0&&included<total;},[included,total,pending]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={pending??(total>0&&included===total)} disabled={disabled||!total} onChange={e=>{setPending(e.target.checked);onChange(e.target.checked);}}/>;
}
export default function Dismantling({vehicle,onChange,onInventory}:{vehicle:Row;onChange:()=>void;onInventory:()=>void}) {
  const path=`/vehicles/${vehicle.id}/dismantling`;
  const [prepared,setPrepared]=useState(false),[initialError,setInitialError]=useState(""),[attempt,setAttempt]=useState(0);
  const [query,setQuery]=useState(""),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const [confirmation,setConfirmation]=useState<{count:number;token:string}|null>(null);
  useEffect(()=>{
    let active=true;setPrepared(false);setInitialError("");
    api(path+'/prepare','POST',{}).then(()=>{if(active)setPrepared(true);}).catch(e=>{if(active)setInitialError(e.message);});
    return ()=>{active=false;};
  },[vehicle.id,attempt]);
  const params=new URLSearchParams({q:query,offset:String(offset),limit:'100'});
  const {data,error,loading,reload}=useLoad<Row|null>(()=>prepared?api(`${path}/workspace?${params}`):Promise.resolve(null),[vehicle.id,prepared,query,offset]);
  const [pendingRows,setPendingRows]=useState<Record<string,boolean>>({});
  useEffect(()=>setPendingRows({}),[data]);
  const canEdit=prepared&&!!data&&!vehicle.archived&&!data.archived&&!busy&&!loading&&!error;
  const hierarchy:Row[]=data?.hierarchy||[], rows:Row[]=data?.items||[];
  const categories=[...new Map(hierarchy.map(g=>[g.source+':'+g.category_key,g])).values()];
  async function plan(included:boolean,selection:Row) {
    setBusy(true);setMessage('');
    if(selection.ids)setPendingRows(values=>({...values,[selection.ids[0]]:included}));
    try {await api(path+'/plan','POST',{...selection,included});reload();}
    catch(e){setMessage((e as Error).message);setPendingRows({});}finally{setBusy(false);}
  }
  const title=(row:Row)=>row.name+(row.position?` · ${row.position}`:'');
  return <section className="dismantling-workspace simple-warehouse" aria-label="Каталог запчастин автомобіля">
    <State error={initialError||error} loading={!initialError&&(!prepared||loading)}/>
    {(initialError||error)&&<button onClick={()=>initialError?setAttempt(x=>x+1):reload()}>Спробувати знову</button>}
    {data&&<>
      <div className="simple-stock-action">
        <div><strong>Запчастини автомобіля</strong><small>У довіднику: {data.counts.total}. Вибрано: {data.counts.included}. На складі / в історії: {data.counts.received}.</small></div>
        <button className="primary" disabled={!canEdit||!data.add_count||data.add_count>10000} onClick={()=>setConfirmation({count:data.add_count,token:data.add_token})}>Додати на склад{data.add_count?` (${data.add_count})`:''}</button>
      </div>
      {data.add_count>10000&&<p role="alert">За одне підтвердження можна додати до 10 000 позицій. Тимчасово зніміть галочки з частини категорій.</p>}
      <p className="simple-catalog-note">Список можливих деталей, а не підтверджена комплектація. Базових типів — 33; решта доступна після імпорту власного довідника. Галочки не змінюють залишки.</p>
      {message&&<p role="status">{message} <button onClick={onInventory}>Відкрити склад</button></p>}
      <label className="simple-search">Пошук деталей<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/></label>
      {categories.map(category=>{
        const groups=hierarchy.filter(g=>g.source===category.source&&g.category_key===category.category_key);
        const categoryRows=rows.filter(r=>r.source===category.source&&r.category_key===category.category_key);
        const total=groups.reduce((n,g)=>n+g.total,0),included=groups.reduce((n,g)=>n+g.included,0);
        const selection={source:category.source,category_key:category.category_key};
        return <details className="simple-category" key={category.source+':'+category.category_key} open>
          <summary className="simple-category-title"><Selection label={`Вибрати категорію ${category.category_name}`} total={total} included={included} disabled={!canEdit} onChange={value=>plan(value,selection)}/><strong>{category.category_name}</strong><small>{included}/{total}</small></summary>
            {groups.map(group=>{
              const items=categoryRows.filter(r=>r.subcategory_key===group.subcategory_key);
              return <section className="simple-subcategory" key={group.subcategory_key}>
                <div className="simple-subcategory-title"><Selection label={`Вибрати підкатегорію ${group.subcategory_name}`} total={group.total} included={group.included} disabled={!canEdit} onChange={value=>plan(value,{...selection,subcategory_key:group.subcategory_key})}/><strong>{group.subcategory_name}</strong><small>{group.included}/{group.total}</small></div>
                {items.map(row=><label className={`simple-part ${row.included?'':'excluded'}`} key={row.id}>
                  <input type="checkbox" aria-label={`Вибрати ${title(row)}`} checked={pendingRows[row.id]??row.included} disabled={!canEdit} onChange={e=>plan(e.target.checked,{ids:[row.id]})}/>
                  <span>{title(row)}</span>{row.received_at&&<small>Додано на склад{row.stock?` · залишок ${row.stock.quantity}`:''}</small>}
                </label>)}
                {!items.length&&<small>Деталі цієї групи — на іншій сторінці або поза пошуком.</small>}
              </section>;
            })}
        </details>;
      })}
      {!rows.length&&<p>За пошуком деталей немає.</p>}
      {(data.total>100||offset>0)&&<div className="modal-actions"><button disabled={!offset||loading} onClick={()=>setOffset(Math.max(0,offset-100))}>Попередні</button><span>{offset+1}–{Math.min(offset+100,data.total)} з {data.total}</span><button disabled={offset+100>=data.total||loading} onClick={()=>setOffset(offset+100)}>Наступні</button></div>}
      {!vehicle.archived&&<DismantlingCatalogImport onImported={()=>setAttempt(x=>x+1)}/>}
    </>}
    {confirmation&&<Confirm title="Додати на склад?" text={`${vehicle.manufacturer} ${vehicle.model} · ${vehicle.year}. Нових позицій: ${confirmation.count}, кількість кожної — 1. Підтверджую фактичне надходження всіх вибраних деталей, включно з іншими сторінками й поза пошуком.`} onClose={()=>setConfirmation(null)} onConfirm={async()=>{
      setBusy(true);
      try {const result=await api(path+'/add-stock','POST',{selection_token:confirmation.token,expected_count:confirmation.count,quantity:1});setConfirmation(null);setMessage(`Додано ${result.updated} запчастин на склад`);reload();onChange();}
      finally{setBusy(false);}
    }}/>}
  </section>;
}
