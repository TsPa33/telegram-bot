import {useMemo} from 'react';
import {Boxes,CheckCircle2,BookmarkCheck,Tag,MapPin,Layers,Plus,ClipboardCheck,History,Archive as ArchiveIcon} from 'lucide-react';
import type {Row} from './api';

type Props={
 rows:Row[];categories:Row[];busy:boolean;
 onCategory:(id:string)=>void;onLocation:(name:string)=>void;
 onAdd:()=>void;onAudit:()=>void;onArchive:()=>void;onInspect:()=>void;
 canAdd:boolean;canAudit:boolean;canArchive:boolean;canInspect:boolean
};
const format=(n:number)=>n.toLocaleString('uk-UA');
export function InventorySummary({rows,busy}:{rows:Row[];busy:boolean}){
 const total=rows.length;
 const available=rows.filter(p=>p.assortment_enabled!==false&&Number(p.available_quantity)>0).length;
 const reserved=rows.filter(p=>Number(p.reserved_quantity)>0).length;
 const unpriced=rows.filter(p=>p.selling_price===null||p.selling_price===undefined).length;
 const cells=[{label:'Позицій у відборі',value:total,Icon:Boxes},{label:'Мають вільний залишок',value:available,Icon:CheckCircle2},{label:'Мають резерв',value:reserved,Icon:BookmarkCheck},{label:'Без власної ціни',value:unpriced,Icon:Tag}];
 return <section className="r115-kpis" aria-label="Показники поточного відбору">
  {cells.map(({label,value,Icon})=><div key={label} className="r115-kpi"><Icon size={21} aria-hidden="true"/><div><strong>{busy?'—':format(value)}</strong><span>{label}</span></div></div>)}
 </section>;
}
export default function InventoryInsights({rows,categories,busy,onCategory,onLocation,onAdd,onAudit,onArchive,onInspect,canAdd,canAudit,canArchive,canInspect}:Props){
 const {topCategories,topLocations,available}=useMemo(()=>{
  const counts=new Map<string,number>(),places=new Map<string,number>();
  let available=0;
  for(const p of rows){
   counts.set(String(p.category_id||''),(counts.get(String(p.category_id||''))||0)+1);
   const loc=String(p.location||'').trim();
   places.set(loc,(places.get(loc)||0)+1);
   if(p.assortment_enabled!==false&&Number(p.available_quantity)>0)available++;
  }
  const name=new Map(categories.map(x=>[String(x.id),String(x.name)]));
  return {
   topCategories:[...counts].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([id,count])=>({id,label:name.get(id)||'Без категорії',count})),
   topLocations:[...places].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([location,count])=>({location,label:location||'Не вказано',count})),
   available
  };
 },[rows,categories]);
 const total=rows.length;
 return <aside className="r115-rail" aria-label="Огляд поточного складського відбору">
  <section className="r115-rail-card"><h3>Залишки за відбором</h3>
   <div className="r115-donut" style={{'--share':(total?Math.round(100*available/total):0)+'%'} as React.CSSProperties}><div><strong>{busy?'—':format(total)}</strong><small>позицій</small></div></div>
   <div className="r115-donut-legend"><span><i className="r115-dot green"/>Є вільний залишок</span><strong>{busy?'—':format(available)}</strong><span><i className="r115-dot grey"/>Без вільного залишку</span><strong>{busy?'—':format(total-available)}</strong></div>
   <p className="r115-hint">Кількість позицій, не одиниць. Резерв може бути частковим.</p>
  </section>
  <section className="r115-rail-card"><h3><Layers size={17}/> Топ категорій</h3>
   {topCategories.map(x=><button type="button" className="r115-rank" key={x.id} onClick={()=>onCategory(x.id)} title={'Показати: '+x.label}><span>{x.label}</span><strong>{x.count}</strong><i><b style={{width:(total?x.count/total*100:0)+'%'}}/></i></button>)}
   {!busy&&!topCategories.length&&<p className="r115-hint">Категорій у відборі немає</p>}
  </section>
  <section className="r115-rail-card"><h3><MapPin size={17}/> Локації</h3>
   {topLocations.map(x=><button className="r115-location" type="button" key={x.location} onClick={()=>onLocation(x.location)}><span>{x.label}</span><strong>{x.count}</strong></button>)}
   {!busy&&!topLocations.length&&<p className="r115-hint">Локаціїв не знайдено</p>}
  </section>
  <section className="r115-rail-card"><h3>Швидкі дії</h3><div className="r115-action-grid">
   {canAdd&&<button type="button" onClick={onAdd}><Plus size={18}/>Додати запчастину</button>}
   {canInspect&&<button type="button" onClick={onInspect}><ClipboardCheck size={18}/>Перевірити стан</button>}
   {canAudit&&<button type="button" onClick={onAudit}><History size={18}/>Історія операцій</button>}
   {canArchive&&<button type="button" onClick={onArchive}><ArchiveIcon size={18}/>Архів запчастин</button>}
   </div></section>
 </aside>;
}
