import {useCan} from './permissions';
import type {ReactNode} from 'react';
import {Package} from 'lucide-react';
import {type Row} from './api';
import {PriceSummary} from './CompactParts';
import {SellerPriceEditor} from './MarketPricing';
import {inventoryStockKind} from './inventoryPresentation';
const states:Record<string,string>={available:'В наявності',reserved:'Зарезервована',empty:'Без залишку',excluded:'Виключена',archived:'Архівна'};
export function InventoryTableHead(){return <div className="ui3-table-head" aria-hidden="true"><span>Запчастина</span><span>Автомобіль</span><span>Залишок</span><span>Ринкова ціна</span><span>Моя ціна</span><span>Дії</span></div>;}
export function InventoryPartRow({part:p,categories,vehicle,market,marketError,selected,canSelect,onSelect,onOpen,onSaved,actions}:{part:Row;categories:Row[];vehicle?:Row;market?:Row;marketError?:string;selected:boolean;canSelect:boolean;onSelect:(checked:boolean)=>void;onOpen:()=>void;onSaved:(p:Row)=>void;actions:ReactNode}){
 const can=useCan();
 const category=categories.find(c=>c.id===p.category_id),sub=categories.find(c=>c.id===p.subcategory_id),kind=inventoryStockKind(p);
 return <article className="ui3-part" aria-label={p.name}><div className="ui3-identity">{canSelect&&<input type="checkbox" aria-label={`Вибрати ${p.name}`} checked={selected} onChange={e=>onSelect(e.target.checked)}/>}<span className="ui3-photo" role="img" aria-label="Фото відсутнє"><Package size={22} strokeWidth={1.3}/></span><div><button className="ux1-part-name" title={p.name} onClick={onOpen}>{p.name}</button><small>{category?.name||'Без категорії'} › {sub?.name||'Інші деталі'}</small></div></div><div className="ui3-donor">{vehicle?<><span>{vehicle.manufacturer} {vehicle.model}</span><small>{vehicle.year} · №{vehicle.number}</small></>:<span>{p.vehicle_id?'Автомобіль донора':'Без автомобіля'}</span>}</div><div className="ui3-stock"><span className={'ux1-status '+kind}>{states[kind]}</span><b>{p.quantity} <span>шт.</span></b>{p.quantity_basis==='assumed'&&<small>Кількість потребує перевірки</small>}{p.reserved_quantity>0&&<small>Резерв: {p.reserved_quantity} · Вільно: {p.assortment_enabled===false?0:p.available_quantity}</small>}</div><div className="ui3-market">{!can('catalog.view')?<span className="ux1-muted">Ринкові ціни недоступні</span>:marketError?<span className="ux1-muted">Не вдалося завантажити ціни</span>:<PriceSummary g={market} showRelated/>}</div><div className="ui3-own"><SellerPriceEditor part={p} compact onSaved={onSaved}/></div><div className="ui3-actions">{actions}</div></article>;
}
