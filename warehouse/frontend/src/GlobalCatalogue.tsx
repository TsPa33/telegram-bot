import {useState} from 'react';
import {api,type Row} from './api';
import {State,useLoad} from './shared';

export default function GlobalCatalogue(){
 const [open,setOpen]=useState(false);
 return <details className="panel padded" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Спільний каталог CarPot v2</summary>{open&&<Contents/>}</details>;
}
function Contents(){
 const [model,setModel]=useState(''),[category,setCategory]=useState(''),[sub,setSub]=useState(''),[q,setQ]=useState(''),[offset,setOffset]=useState(0);
 const models=useLoad(()=>api('/catalogue/entities?kind=model&limit=200'),[]),categories=useLoad(()=>api('/catalogue/entities?kind=category&limit=200'),[]);
 const subs=useLoad(()=>category?api(`/catalogue/entities?kind=subcategory&parent_id=${category}&limit=200`):Promise.resolve({items:[]}),[category]);
 const rows=useLoad(()=>api(`/catalogue?offset=${offset}&limit=50&model_id=${model}&category_id=${category}&subcategory_id=${sub}&q=${encodeURIComponent(q)}`),[model,category,sub,q,offset]);
 return <><p>Глобальний довідник усіх складів. Ринкові пропозиції відокремлені від вашої ціни продажу. Сумісність за роком, VIN та комплектацією не підтверджена.</p>
  <div className="form-grid"><label>Модель глобального каталогу<select aria-label="Модель глобального каталогу" value={model} onChange={e=>{setModel(e.target.value);setOffset(0);}}><option value="">Усі моделі</option>{models.data?.items.map((m:Row)=><option key={m.id} value={m.id}>{m.parent_name} {m.name} {m.details.generation}</option>)}</select></label>
   <label>Категорія глобального каталогу<select aria-label="Категорія глобального каталогу" value={category} onChange={e=>{setCategory(e.target.value);setSub('');setOffset(0);}}><option value="">Усі категорії</option>{categories.data?.items.map((m:Row)=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
   <label>Підкатегорія глобального каталогу<select aria-label="Підкатегорія глобального каталогу" disabled={!category} value={sub} onChange={e=>{setSub(e.target.value);setOffset(0);}}><option value="">Усі підкатегорії</option>{subs.data?.items.map((m:Row)=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
   <label>Назва, OEM або артикул<input value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label></div>
  <State error={rows.error||models.error||categories.error||subs.error} loading={rows.loading}/>
  {rows.data&&!rows.loading&&<><p>Пропозицій: {rows.data.total}</p><div className="table-wrap"><table><thead><tr><th>Джерело / артикул</th><th>Пропозиція / OEM</th><th>Ринкова ціна</th><th>Спостереження</th></tr></thead><tbody>{rows.data.items.map((r:Row)=><tr key={r.id}><td>{r.source} · {r.source_article}</td><td><a href={r.source_url} target="_blank" rel="noopener noreferrer">{r.part_name}</a><br/>{r.oem||'OEM не вказано'}<br/><small>{r.condition}</small></td><td>{r.price_uah==null?'Не вказано':`${r.price_uah} ₴`}{r.price_usd!=null&&` · ${r.price_usd} USD`}</td><td>{new Date(r.observed_at).toLocaleString('uk-UA')}</td></tr>)}</tbody></table></div><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>Назад</button><button disabled={offset+50>=rows.data.total} onClick={()=>setOffset(offset+50)}>Далі</button></>}
 </>;
}
