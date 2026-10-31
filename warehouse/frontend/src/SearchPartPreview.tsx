import {Package,MapPin,FileSearch,ShoppingCart,ExternalLink,X} from 'lucide-react';
import {money,labels,type Row} from './api';
import SearchPartPhoto from './SearchPartPhoto';
import {categoryLabelUk} from './PartsQuickCategories';

export default function SearchPartPreview({part,vehicle,category,subcategory,canSell,onOpen,onSell,open,onClose}:{
 part:Row|null;vehicle?:Row;category?:Row;subcategory?:Row;canSell:boolean;onOpen:()=>void;onSell:()=>void;open:boolean;onClose:()=>void
}){
 return <aside id="search-part-preview" className={'ui11-preview'+(open?' open':'')} aria-label="Швидкий перегляд запчастини">
  {!part?<div className="ui11-preview-empty"><Package size={32} strokeWidth={1.2}/><strong>Оберіть запчастину</strong><p>Інформація про деталь з’явиться тут.</p></div>:<>
   <div className="ui11-preview-heading"><button type="button" className="ui11-preview-close" aria-label="Закрити швидкий перегляд" onClick={onClose}><X size={18}/></button><div><span className="ui11-eyebrow">Швидкий перегляд</span><h2>{part.name}</h2><p>{category?categoryLabelUk(category.name):'Без категорії'} › {subcategory?categoryLabelUk(subcategory.name):'Інші деталі'}</p></div></div>
   <div className="ui11-preview-image"><SearchPartPhoto key={part.id} id={part.id} name={part.name}/></div>
   <dl className="ui11-preview-facts">
    <div><dt>Автомобіль</dt><dd>{vehicle?`${vehicle.manufacturer} ${vehicle.model} · ${vehicle.year}`:'Не вказано'}</dd></div>
    <div><dt>OEM</dt><dd>{part.oem_number||'Не вказано'}</dd></div>
    <div><dt>Артикул</dt><dd>{part.article_number||'Не вказано'}</dd></div>
    <div><dt>Стан</dt><dd>{labels[part.condition]||'Не уточнено'}</dd></div>
    <div><dt>Залишок</dt><dd>{part.available_quantity??part.quantity??0} шт.</dd></div>
    <div><dt>Локація</dt><dd><MapPin size={13} aria-hidden="true"/>{part.location||'Не вказано'}</dd></div>
   </dl>
   <div className="ui11-preview-price"><span>Моя ціна</span>
    <strong>{part.selling_price!=null?money(part.selling_price,part.currency||'UAH'):'Не встановлено'}</strong>
    {part.selling_price==null&&<small>Ціна продажу не зазначена</small>}
   </div>
   <div className="ui11-preview-buttons">
    <button type="button" className="primary" onClick={onOpen}><FileSearch size={16}/> Відкрити картку <ExternalLink size={14}/></button>
    {canSell&&<button type="button" className="secondary" disabled={!(part.available_quantity>0)||part.assortment_enabled===false} onClick={onSell}><ShoppingCart size={16}/> Продати</button>}
   </div>
  </>}
 </aside>;
}
