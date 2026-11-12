import {ArrowRight, CarFront, ClipboardList, Package} from 'lucide-react';
import {Link} from 'react-router-dom';
import type {Row} from './api';
import VehicleImage from './VehicleImage';
import VehicleQuickPowertrain from './VehicleQuickPowertrain';

type Props={vehicle:Row;context:'vehicles'|'inventory';onParts:()=>void;onData?:()=>void;onSaved:(row:Row)=>void};
export default function VehicleCard({vehicle:v,context,onParts,onData,onSaved}:Props) {
 const name=`${v.manufacturer} ${v.model}`;
 return <article className="vehicle-card vehicle-summary-card r1141-card r1146-card corporate-donor-card">
  <div className="r1146-card-intro">
   <div className="r1146-card-photo"><VehicleImage vehicle={v}/><small className="donor-image-caption">Довідкова ілюстрація</small></div>
   <div className="r1146-card-summary">
    <div className="r1146-card-heading">
     <div><button type="button" className="text-button vehicle-card-name" onClick={onData||onParts}>{name}</button><p>{v.year} · Донор №{v.number??'—'}</p></div>
     <span className="r1141-status">{v.archived?'Архів':v.status==='completed'?'Завершено':v.status==='planned'?'Заплановано':'На розборі'}</span>
    </div>
    {v.dismantling_v3?.global_selection&&<p><strong>Модифікація:</strong> {v.dismantling_v3.global_selection.modification_description||"Немає даних"}</p>}
    {v.ktype&&<p><strong>Модифікація:</strong> {v.engine||"Вибрана"}</p>}
    <VehicleQuickPowertrain vehicle={v} onSaved={onSaved}/>
   </div>
  </div>
  <div className="r1146-card-footer">
   <div className="r1141-stock"><Package size={18} aria-hidden="true"/><strong>{v.registered_parts??'—'}</strong><span>запчастин у картці</span><span style={{marginLeft:8,color:"var(--muted,#60746c)"}}>· На складі: <b>{v.stock_positions??'—'}</b></span></div>
   <div className="r1141-car-actions">{context==='inventory'&&!onData?<Link className="button secondary" to={'/vehicles?donor='+v.id+'&info=1'}><ClipboardList size={15}/> Картка авто</Link>:<button type="button" className="secondary" onClick={onData||onParts}><ClipboardList size={15}/> Картка авто</button>}<button type="button" className="primary" aria-label={context==='inventory'?'Відкрити склад '+name+' · '+v.year+' · №'+v.number+' · Запчастини':undefined} onClick={onParts}>{context==='inventory'?'Запчастини':'Розбір'} <ArrowRight size={16}/></button></div>
  </div>
 </article>;
}
