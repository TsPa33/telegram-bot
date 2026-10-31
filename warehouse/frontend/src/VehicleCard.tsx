import {ArrowRight, CarFront, ClipboardList} from 'lucide-react';
import {Link} from 'react-router-dom';
import type {Row} from './api';
import PowertrainEditor from './PowertrainEditor';
import VehicleImage from './VehicleImage';
import VehicleQuickPowertrain from './VehicleQuickPowertrain';

type Props={vehicle:Row;context:'vehicles'|'inventory';onParts:()=>void;onData?:()=>void;onSaved:(row:Row)=>void};
export default function VehicleCard({vehicle:v,context,onParts,onData,onSaved}:Props) {
 const name=`${v.manufacturer} ${v.model}`;
 if(context==='vehicles')return <article className="vehicle-card vehicle-summary-card r1141-card">
  <div className="r1141-card-top"><div className="r1141-car-photo"><VehicleImage vehicle={v}/><span>Довідкова ілюстрація</span></div>
   <div className="r1141-car-main"><div className="r1141-car-title"><button type="button" className="text-button vehicle-card-name" onClick={onData||onParts}>{name}</button><span className="r1141-status">{v.archived?'Архів':v.status==='completed'?'Розбір завершено':v.status==='planned'?'Заплановано':'На розборі'}</span></div>
    <p>{v.year} · Донор №{v.number??'—'}</p>
    {v.vin&&<small className="r1143-vin">VIN: {v.vin}</small>}
   </div>
  </div>
  <VehicleQuickPowertrain vehicle={v} onSaved={onSaved}/>
  <div className="r1141-car-bottom"><div className="r1141-stock"><CarFront size={17}/><strong>{v.stock_positions??'—'}</strong><span>позицій на складі</span></div>
   <div className="r1141-car-actions"><button type="button" className="secondary" onClick={onData||onParts}><ClipboardList size={15}/> Картка авто</button><button type="button" className="primary" onClick={onParts}>Розбір <ArrowRight size={15}/></button></div>
  </div>
 </article>;
 return <article className="vehicle-card donor-stock-card">
  <div className="vehicle-card-heading">
   <div className="vehicle-card-identity"><button className="text-button strong vehicle-card-name" onClick={onParts}>{name}</button><p>{v.year} · №{v.number??'—'}{v.archived?' · архів':''}</p></div>
   <span className="vehicle-stock-count">На складі <b>{v.stock_positions??'…'}</b></span>
  </div>
  <VehicleImage vehicle={v}/>
  <PowertrainEditor compact vehicle={v} onSaved={onSaved}/>
  <div className="vehicle-card-footer">
   {onData?<button className="text-button vehicle-data-action" onClick={onData}>Дані автомобіля</button>:<Link className="button text-button vehicle-data-action" to={'/vehicles?donor='+v.id+'&info=1'}>Дані автомобіля</Link>}
   <button className="secondary vehicle-parts-action" aria-label={`Відкрити склад ${name} · ${v.year} · №${v.number} · Запчастини`} onClick={onParts}>Запчастини <ArrowRight size={15} aria-hidden="true"/></button>
  </div>
 </article>;
}
