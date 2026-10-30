import {useEffect,useRef,useState,type ReactNode} from 'react';
import {api,labels,physicalLocation,type Row} from './api';
import {useCan} from './permissions';
import {State,useLoad} from './shared';
import {useMarketPrices,SellerPriceEditor,pricesChanged} from './MarketPricing';
import {PriceSummary} from './CompactParts';
import {inventoryStockKind} from './inventoryPresentation';
import PowertrainEditor from './PowertrainEditor';
import PartCharacteristicsEditor from './PartCharacteristicsEditor';
import './part-card-r1.css';
import MarketCheck from './MarketCheck';
export default function PartCard({part,onSaved,tools,actions,initialEdit,editVersion}:{part:Row;onSaved?:(row:Row)=>void;tools?:ReactNode;actions?:ReactNode;initialEdit?:'oem'|'color';editVersion?:number}){
 const localSaved=useRef(false);useEffect(()=>{localSaved.current=false;},[part.id]);
 const can=useCan(),[row,setRow]=useState(part),[editing,setEditing]=useState<'oem'|'color'|null>(initialEdit||null),[donorOverride,setDonor]=useState<Row|null>(null);
 useEffect(()=>setRow(part),[part]);useEffect(()=>setEditing(initialEdit||null),[initialEdit,editVersion]);
 const fresh=useLoad(()=>api('/parts/'+part.id),[part.id]);useEffect(()=>{if(fresh.data&&fresh.data.id===part.id&&!localSaved.current)setRow(fresh.data);},[fresh.data]);
 const donor=useLoad(()=>row.vehicle_id&&can('vehicles.view')?api('/vehicles/'+row.vehicle_id):Promise.resolve(null),[row.vehicle_id]),vehicle=donorOverride||donor.data;
 const market=useMarketPrices([row.id]),enabled=can('inventory.edit')&&!row.archived&&!fresh.error&&'color_name'in row;
 function saved(value:Row){localSaved.current=true;setRow(value);setEditing(null);onSaved?.(value);pricesChanged();}
 const kind=inventoryStockKind(row),state:Record<string,string>={available:'В наявності',reserved:'Зарезервована',empty:'Без залишку',excluded:'Виключена',archived:'Архівна'};
 return <section className="r1-part-card" aria-label="Картка запчастини"><State error={fresh.error||donor.error} loading={fresh.loading}/><header className="r1-part-summary"><p>{vehicle?`${vehicle.manufacturer} ${vehicle.model} · ${vehicle.year} · №${vehicle.number}`:row.vehicle_id?'Дані донора недоступні':'Без автомобіля'}</p><div><span className={'ux1-status '+kind}>{state[kind]}</span><strong>{row.quantity} шт.</strong>{row.quantity_basis==='assumed'&&<small>Облікова кількість потребує перевірки</small>}{row.reserved_quantity>0&&<small>Резерв: {row.reserved_quantity} · Вільно: {row.assortment_enabled===false?0:row.available_quantity}</small>}</div></header>
 {actions&&<div className="r1-card-actions">{actions}</div>}
 <section className="r1-characteristics" aria-label="Характеристики деталі"><div className="r1-section-heading"><h3>Характеристики</h3>{enabled&&<div><button onClick={()=>setEditing(editing==='oem'?null:'oem')}>Змінити OEM / код</button><button onClick={()=>setEditing(editing==='color'?null:'color')}>Колір деталі</button></div>}</div><dl>{[['OEM / код',row.oem_number],['Колір',row.color_name],['Код фарби',row.paint_code],['Стан',labels[row.condition]],['Перевірка наявності',labels[row.availability]],['Розташування',row.location||physicalLocation(row)]].map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value||'Не вказано'}</dd></div>)}</dl>{editing&&enabled&&<PartCharacteristicsEditor key={editing} part={row} kind={editing} onSaved={saved} onClose={()=>setEditing(null)}/>}</section>
 <section className="r1-donor-data" aria-label="Двигун та КПП донора"><h3>Двигун та КПП донора</h3>{vehicle?<PowertrainEditor vehicle={vehicle} compact inline onSaved={v=>{setDonor(v);pricesChanged();}}/>:<p>Не вказано</p>}<small>Характеристики автомобіля, не підтвердження сумісності деталі. Оновлення переліку можливих деталей — окрема дія.</small></section>
 <section className="r1-card-prices" aria-label="Ціни деталі"><h3>Ціни</h3>{market.error?<p role="alert">{market.error}</p>:can('catalog.view')?<PriceSummary g={market.rows[row.id]} showRelated/>:<p>Ринкові дані недоступні</p>}<MarketCheck part={row} vehicle={vehicle}/><div className="r1-own-price"><span>Моя ціна</span><SellerPriceEditor part={row} onSaved={saved}/></div></section>
 {row.internal_notes&&<section><h3>Примітки</h3><p className="r1-note">{row.internal_notes}</p></section>}{tools&&<details className="r1-secondary"><summary>Додаткова інформація та інструменти</summary>{row.article_number&&<p>Внутрішній артикул: {row.article_number}</p>}{can('parts.view_cost')&&row.unit_cost!=null&&<p>Собівартість: {row.unit_cost}</p>}{tools}</details>}
 </section>;
}
