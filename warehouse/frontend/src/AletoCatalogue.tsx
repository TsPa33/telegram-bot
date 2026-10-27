import {useState} from 'react';
import {api, type Row} from './api';
import {State, useLoad} from './shared';

export default function AletoCatalogue({vehicleId}:{vehicleId:string}) {
  const [open,setOpen]=useState(false);
  return <details className="vehicle-secondary" onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>Aleto — довідник пропозицій</summary>
    {open&&<CatalogueContent vehicleId={vehicleId}/>}
  </details>;
}

function CatalogueContent({vehicleId}:{vehicleId:string}) {
  const [category,setCategory]=useState(''),[subcategory,setSubcategory]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0);
  const {data,error,loading,reload}=useLoad(()=>api<Row>(`/vehicles/${vehicleId}/aleto-catalog?limit=50&offset=${offset}&q=${encodeURIComponent(q)}&category_id=${encodeURIComponent(category)}&subcategory_id=${encodeURIComponent(subcategory)}`),[vehicleId,category,subcategory,q,offset]);
  const nodes:Row[]=data?.categories||[];
  const roots=[...new Map(nodes.map(n=>[n.category_id,n])).values()];
  const subs=nodes.filter(n=>n.category_id===category&&n.subcategory_id);
  return <div>
    <p>Довідкові пропозиції для моделі. Сумісність за роком, VIN і комплектацією не перевірена. Каталог неповний.</p>
    <div className="form-grid">
      <label>Категорія Aleto<select aria-label="Категорія Aleto" value={category} onChange={e=>{setCategory(e.target.value);setSubcategory('');setOffset(0);}}><option value="">Усі категорії</option>{roots.map(n=><option key={n.category_id} value={n.category_id}>{n.category_name}</option>)}</select></label>
      <label>Підкатегорія Aleto<select aria-label="Підкатегорія Aleto" disabled={!category} value={subcategory} onChange={e=>{setSubcategory(e.target.value);setOffset(0);}}><option value="">Усі підкатегорії</option>{subs.map(n=><option key={n.subcategory_id} value={n.subcategory_id}>{n.subcategory_name}</option>)}</select></label>
      <label>Пошук назви, артикулу або OEM<input value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label>
    </div>
    <State error={error} loading={loading}/>
    {error&&<button onClick={reload}>Повторити</button>}
    {data&&!loading&&<><p>Пропозицій: {data.total}. Ціна Aleto (орієнтир) — окремо від вашої ціни продажу.</p>
      <div className="table-scroll"><table><thead><tr><th>Пропозиція</th><th>Артикул / OEM</th><th>Ціна Aleto (орієнтир)</th><th>Перевірено</th></tr></thead><tbody>
        {data.items.map((r:Row)=><tr key={r.id}><td><a href={r.source_url} target="_blank" rel="noopener noreferrer">{r.title}</a></td><td>{r.article}<br/>{r.oem||'OEM не вказано'}</td><td>{r.price_uah==null?'Не вказано':`${r.price_uah} ₴`}{r.price_usd!=null&&<small> · {r.price_usd} USD (джерело)</small>}</td><td>{new Date(r.observed_at).toLocaleString('uk-UA')}</td></tr>)}
      </tbody></table></div>
      <div className="modal-actions"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Назад</button><button disabled={offset+50>=data.total} onClick={()=>setOffset(offset+50)}>Далі</button></div>
    </>}
  </div>;
}
