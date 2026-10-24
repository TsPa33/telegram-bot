import {ArrowRight} from 'lucide-react';
import {Link} from 'react-router-dom';
import type {Row} from './api';
import PowertrainEditor from './PowertrainEditor';
import VehicleImage from './VehicleImage';

type Props={vehicle:Row;context:'vehicles'|'inventory';onParts:()=>void;onData?:()=>void;onSaved:(row:Row)=>void};
export default function VehicleCard({vehicle:v,context,onParts,onData,onSaved}:Props) {
 const name=`${v.manufacturer} ${v.model}`;
 return <article className={`vehicle-card ${context==='vehicles'?'vehicle-summary-card':'donor-stock-card'}`}>
  <div className="vehicle-card-heading">
   <div className="vehicle-card-identity"><button className="text-button strong vehicle-card-name" onClick={onParts}>{name}</button><p>{v.year} · №{v.number??'—'}{v.archived?' · архів':''}</p></div>
   <span className="vehicle-stock-count">На складі <b>{v.stock_positions??'…'}</b></span>
  </div>
  <VehicleImage vehicle={v}/>
  <PowertrainEditor compact vehicle={v} onSaved={onSaved}/>
  <div className="vehicle-card-footer">
   {onData?<button className="text-button vehicle-data-action" onClick={onData}>Дані автомобіля</button>:<Link className="button text-button vehicle-data-action" to={'/vehicles?donor='+v.id+'&info=1'}>Дані автомобіля</Link>}
   <button className="secondary vehicle-parts-action" aria-label={context==='vehicles'?`Запчастини ${name}`:`Відкрити склад ${name} · ${v.year} · №${v.number} · Запчастини`} onClick={onParts}>Запчастини <ArrowRight size={15} aria-hidden="true"/></button>
  </div>
 </article>;
}
