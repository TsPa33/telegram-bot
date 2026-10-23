import { useEffect, useState } from "react";
import { api, labels, type Row } from "./api";
import { Modal, RecordForm } from "./components";
import { Confirm, State, useLoad } from "./shared";
import DismantlingCatalogImport from "./DismantlingCatalogImport";

type Scope={source?:string;category_key?:string;subcategory_key?:string;q?:string};
export default function Dismantling({vehicle,onChange,onInventory}:{vehicle:Row;onChange:()=>void;onInventory:()=>void}) {
  const path=`/vehicles/${vehicle.id}/dismantling`;
  const [query,setQuery]=useState(""),[active,setActive]=useState<Scope|null>(null),[offset,setOffset]=useState(0),[visibility,setVisibility]=useState("all");
  const [optimistic,setOptimistic]=useState<Record<string,boolean>>({});
  const [busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const [receiving,setReceiving]=useState<{ids?:string[];scope?:Scope;token?:string;count:number;title?:string}|null>(null);
  const [confirming,setConfirming]=useState<{scope:Scope;token:string;count:number}|null>(null);
  const scope:Scope={...active,q:query};
  const params=new URLSearchParams({q:query,offset:String(offset),limit:"100",visibility,...active});
  const {data,error,loading,reload}=useLoad(()=>api(`${path}/workspace?${params}`),[vehicle.id,query,active?.source,active?.category_key,offset,visibility]);
  useEffect(()=>setOptimistic({}),[data]);
  const canEdit=!!data&&!data.archived&&!vehicle.archived&&!busy&&!loading&&!error;
  const rows:Row[]=data?.items||[], hierarchy:Row[]=data?.hierarchy||[];
  const counts=data?.counts||{total:0,included:0,excluded:0,dismantled:0,received:0};
  const candidates=data?.scope_counts||{mark:0,receipt:0};
  const categoryMap=new Map<string,Row>();
  for(const group of hierarchy){const key=group.source+':'+group.category_key;const entry=categoryMap.get(key)||{...group,total:0};entry.total+=group.total;categoryMap.set(key,entry);}
  const categories=[...categoryMap.values()];
  function done(){reload();onChange();}
  async function mutate(url:string,body:Row) {
    setBusy(true);setMessage("");
    try {const result=await api(path+url,"POST",body);done();return result;}
    catch(e){setMessage((e as Error).message);return null;}finally{setBusy(false);}
  }
  async function plan(included:boolean,selection:Scope|{ids:string[]}) {
    if('ids' in selection&&selection.ids.length===1)setOptimistic(values=>({...values,[selection.ids[0]]:included}));
    const result=await mutate('/plan',{...selection,included});if(!result)setOptimistic({});if(result)setMessage(`План оновлено: ${result.updated}. Склад не змінено.`);
  }
  const title=(row:Row)=>row.name+(row.position?` · ${row.position}`:"");
  function renderRow(row:Row) {
    const eligible=row.included&&row.status==='dismantled'&&!row.received_at;
    return <div className={`dismantling-row ${row.included?'':'excluded'}`} key={row.id}>
      <label className="dismantling-plan-toggle"><input type="checkbox" aria-label={`Включити ${title(row)}`} checked={optimistic[row.id]??row.included} disabled={!canEdit} onChange={e=>plan(e.target.checked,{ids:[row.id]})}/></label>
      <div className="dismantling-row-name"><strong>{title(row)}</strong>
        {row.received_at&&<small>Оприбутковано: {row.quantity} · Залишок: {row.stock?.quantity??'див. склад'}</small>}
        {!row.included&&<small>Виключено з плану</small>}
      </div>
      {row.received_at?<span className="dismantling-received">На складі / в історії</span>:<select aria-label={`Статус ${title(row)}`} value={row.status} disabled={!canEdit||!row.included}
        onChange={async e=>{const r=await mutate('/actions',{ids:[row.id],action:e.target.value});if(r)setMessage('Статус збережено. Склад не змінено.');}}>
        {['unchecked','dismantled','absent','damaged'].map(value=><option key={value} value={value}>{labels[value]}</option>)}
      </select>}
      {eligible&&<button className="dismantling-receive" disabled={!canEdit} aria-label={`Оприбуткувати ${title(row)}`} onClick={()=>setReceiving({ids:[row.id],count:1,title:title(row)})}>На склад</button>}
    </div>;
  }
  const renderGroups=(items:Row[])=>[...new Map(items.map(r=>[r.source+':'+r.category_key+':'+r.subcategory_key,r])).values()].map(group=>{
    const subset=items.filter(r=>r.source===group.source&&r.category_key===group.category_key&&r.subcategory_key===group.subcategory_key);
    const selection={source:group.source,category_key:group.category_key,subcategory_key:group.subcategory_key};
    const meta=hierarchy.find(g=>g.source===group.source&&g.category_key===group.category_key&&g.subcategory_key===group.subcategory_key);
    return <section className="dismantling-subcategory" key={group.source+group.category_key+group.subcategory_key}>
      <div className="dismantling-group-head"><h4>{query&&`${group.category_name} / `}{group.subcategory_name} <small>({meta?.total??subset.length})</small></h4>
        <div><button disabled={!canEdit} onClick={()=>plan(false,selection)}>Виключити підкатегорію</button><button disabled={!canEdit} onClick={()=>plan(true,selection)}>Повернути підкатегорію</button></div></div>
      {subset.map(renderRow)}
    </section>;
  });
  return <section className="dismantling-workspace" aria-label="Робочий екран розбору">
    <h3>План розбору</h3><State error={error} loading={loading}/>
    {error&&<button onClick={reload}>Повторити читання</button>}
    {data&&<>
      <div className="dismantling-counts" aria-label="Показники розбору">
        <span>Включено <b>{counts.included}</b></span><span>Виключено <b>{counts.excluded}</b></span>
        <span>Демонтовано <b>{counts.dismantled}</b></span><span>Оприбутковано <b>{counts.received}</b></span>
      </div>
      <div className="modal-actions">
        {!vehicle.archived&&<button disabled={!canEdit} onClick={async()=>{
          const r=await mutate('/start',{});if(r)setMessage(`Нових позицій: ${r.created}. Збережений вибір не змінено.`);
        }}>{counts.total?'Оновити список із довідника':'Почати розбір'}</button>}
        <button onClick={onInventory}>Склад автомобіля</button>
      </div>
      {message&&<p role="status">{message}</p>}
      {counts.total>0&&<>
        <small>Галочка — лише включення до плану. Наявність і залишок не підтверджені.</small>
        <div className="dismantling-search"><label>Пошук деталей<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setActive(null);setOffset(0);}}/></label>
          <label>Показати<select aria-label="Показати план" value={visibility} onChange={e=>{setVisibility(e.target.value);setOffset(0);}}><option value="all">Усі</option><option value="included">Включені</option><option value="excluded">Виключені</option></select></label></div>
        <div className="dismantling-toolbar">
          <small>Область: {query?'поточний пошук':active?'відкрита категорія':'увесь донор'}. Лише включені деталі.</small>
          <div className="modal-actions"><button disabled={!canEdit||!candidates.mark||candidates.mark>1000||visibility==='excluded'} onClick={()=>setConfirming({scope,token:data.scope_tokens.mark,count:candidates.mark})}>Демонтовано включені ({visibility==='excluded'?0:candidates.mark})</button>
            <button className="primary" disabled={!canEdit||!candidates.receipt||candidates.receipt>1000||visibility==='excluded'} onClick={()=>setReceiving({scope,token:data.scope_tokens.receipt,count:candidates.receipt})}>Оприбуткувати вибрані ({visibility==='excluded'?0:candidates.receipt})</button></div>
          {(candidates.mark>1000||candidates.receipt>1000)&&<small>Звузьте пошук або категорію: до 1000 позицій за операцію.</small>}
        </div>
        {query?renderGroups(rows):categories.map(category=>{
          const selected=active?.source===category.source&&active?.category_key===category.category_key;
          const selection={source:category.source,category_key:category.category_key};
          return <details key={category.source+category.category_key} open={selected}>
            <summary onClick={e=>{e.preventDefault();setActive(selected?null:selection);setOffset(0);}}>{category.category_name} <small>· {category.total}</small></summary>
            {selected&&<><div className="dismantling-category-actions"><button disabled={!canEdit} onClick={()=>plan(false,selection)}>Виключити всю категорію</button><button disabled={!canEdit} onClick={()=>plan(true,selection)}>Повернути всю категорію</button></div>{renderGroups(rows)}</>}
          </details>;
        })}
        {(query||active)&&<><p>Позицій за фільтром: {data.total}.</p>{(data.total>100||offset>0)&&<div className="modal-actions"><button disabled={!offset||loading} onClick={()=>setOffset(Math.max(0,offset-100))}>Попередні</button><button disabled={offset+100>=data.total||loading} onClick={()=>setOffset(offset+100)}>Наступні</button></div>}</>}
      </>}
      {!vehicle.archived&&<DismantlingCatalogImport onImported={reload}/>}
    </>}
    {confirming&&<Confirm title="Підтвердити демонтаж" text={`Позицій: ${confirming.count}. Підтверджуєте фактичний демонтаж усіх включених деталей у цій області? Склад поки не зміниться.`} onClose={()=>setConfirming(null)} onConfirm={async()=>{
      const r=await api(path+'/batch','POST',{...confirming.scope,action:'dismantled',selection_token:confirming.token,expected_count:confirming.count});done();setConfirming(null);setMessage(`Демонтовано: ${r.updated}. Склад не змінено.`);
    }}/>}
    {receiving&&<Modal title="Підтвердити оприбуткування" onClose={()=>setReceiving(null)}>
      <p>Позицій: {receiving.count}. Усі включені та підтверджені демонтованими.</p>{receiving.title&&<p>{receiving.title}</p>}
      <RecordForm submit="Оприбуткувати на склад" initial={{quantity:1,condition:''}} fields={[
        {key:'quantity',label:'Кількість для кожної позиції',type:'number',required:true,min:1,max:1000000,step:1},
        {key:'condition',label:'Стан',options:[{value:'',label:'Зберегти стан / типово вживана'},...['used','new','damaged','refurbished'].map(value=>({value,label:labels[value]}))]},
        {key:'location',label:'Місце на складі'},{key:'selling_price',label:'Ціна одиниці, ₴',type:'number',min:0},
      ]} onSave={async values=>{
        const url=receiving.ids?'/actions':'/batch';
        const result=await api(path+url,'POST',{...values,condition:values.condition||null,action:'receipt',...(receiving.ids?{ids:receiving.ids}:{...receiving.scope,selection_token:receiving.token,expected_count:receiving.count})});
        setReceiving(null);setMessage(`Оприбутковано: ${result.updated}. Уже оброблено: ${result.skipped}.`);done();
      }}/>
    </Modal>}
  </section>;
}
