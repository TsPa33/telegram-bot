import {Link} from "react-router-dom";
import QuickPreviewFrame from "./QuickPreviewFrame";
import type {ReactNode} from "react";
import "./part-corporate.css";
import {useEffect,useRef,useState} from 'react';
import {Package,MapPin,FileSearch,ShoppingCart,ExternalLink,X,ChevronLeft,ChevronRight,Camera,Pencil,ImagePlus} from 'lucide-react';
import {api,money,labels,type Row} from './api';
import {useCan} from './permissions';

import {categoryLabelUk} from './PartsQuickCategories';
import {SellerPriceEditor} from './MarketPricing';
import PartCharacteristicsEditor from './PartCharacteristicsEditor';
import {StockOemField,oemOptions} from './OemField';

type Props={
 part:Row|null;vehicle?:Row;category?:Row;subcategory?:Row;canSell:boolean;
 onOpen:()=>void;onSell:()=>void;onEdit:()=>void;onSaved:(row:Row)=>void;
 open:boolean;onClose:()=>void;
 position:number;total:number;onPrevious:()=>void;onNext:()=>void;
 onNotes?:()=>void;onInspection?:()=>void;contextActions?:ReactNode;
 photoRevision:number;onPhotoSaved:(id:string)=>void;
};
export default function SearchPartPreview({part,vehicle,category,subcategory,canSell,onOpen,onSell,onEdit,onSaved,open,onClose,position,total,onPrevious,onNext,photoRevision,onPhotoSaved,onNotes,onInspection,contextActions}:Props){
 const can=useCan(),pricePanel=useRef<HTMLDetailsElement>(null);
 const [editingOem,setEditingOem]=useState(false);
 const [photoEnabled,setPhotoEnabled]=useState<boolean|null>(null);
 const [photoBusy,setPhotoBusy]=useState(false),[photoError,setPhotoError]=useState('');
 const [photos,setPhotos]=useState<Row[]>([]),[activePhoto,setActivePhoto]=useState(0),[photoLoading,setPhotoLoading]=useState(false);
 const photoGuard=useRef(false);
 useEffect(()=>{setEditingOem(false);setPhotoError('');setActivePhoto(0);if(pricePanel.current)pricePanel.current.open=false;},[part?.id]);
 useEffect(()=>{if(!part?.id){setPhotos([]);return;}let active=true;setPhotoLoading(true);setPhotos([]);api<Row[]>('/parts/'+part.id+'/photos').then(rows=>{if(active){setPhotos(rows);setActivePhoto(0);}}).catch(()=>{if(active)setPhotos([]);}).finally(()=>{if(active)setPhotoLoading(false);});return()=>{active=false;};},[part?.id,photoRevision]);
 useEffect(()=>{let active=true;api<Row>('/settings').then(r=>{if(active)setPhotoEnabled(r.photos_enabled===true);}).catch(()=>{if(active)setPhotoEnabled(false);});return()=>{active=false;};},[]);
 async function upload(file:File){
  if(!part||photoGuard.current)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){setPhotoError('Оберіть JPEG, PNG або WebP.');return;}
  if(file.size>5*1024*1024){setPhotoError('Максимальний розмір фото — 5 МБ.');return;}
  photoGuard.current=true;setPhotoBusy(true);setPhotoError('');
  try{
   const data=new FormData();data.append('file',file);
   await api('/parts/'+part.id+'/photos','POST',data,201);
   onPhotoSaved(part.id);
  }catch(e){setPhotoError((e as Error).message);}
  finally{photoGuard.current=false;setPhotoBusy(false);}
 }
 if(!part||!open)return null;
 return <QuickPreviewFrame onClose={onClose}><aside id="search-part-preview" className="ui11-preview part-quick-preview open" aria-label="Дані запчастини">
  {!part?<div className="ui11-preview-empty"><Package size={32} strokeWidth={1.2}/><strong>Оберіть запчастину</strong><p>Інформація про деталь з’явиться тут.</p></div>:<>
   <div className="ui11-preview-heading">
    <div className="ui11-preview-topline"><span className="ui11-eyebrow">Швидкий перегляд</span>
     <div className="ui11-preview-navigation" aria-label="Перехід між результатами">
      <button type="button" onClick={onPrevious} disabled={position<=1} aria-label="Попередня запчастина"><ChevronLeft size={16}/></button>
      <span aria-live="polite">{position} із {total}</span>
      <button type="button" onClick={onNext} disabled={position>=total} aria-label="Наступна запчастина"><ChevronRight size={16}/></button>
     </div>
    <button type="button" className="ui11-preview-close" aria-label="Закрити швидкий перегляд" onClick={onClose}><X size={18}/></button>
    </div>
    <h2>{part.name}</h2>
    {(part.original_name||part.original)&&(part.original_name||part.original)!==part.name&&<p>{part.original_name||part.original}</p>}
   </div>
   <div className="stock-primary-action">{canSell&&part.available_quantity>0&&part.assortment_enabled!==false&&!part.archived&&<button type="button" className="primary" onClick={onSell}><ShoppingCart size={16}/> Оформити замовлення</button>}</div><div className="ui11-preview-image ui12-photo-stage">
    {photos[activePhoto]?.url?<img src={photos[activePhoto].url} alt={part.name+' — фото '+(activePhoto+1)} loading="lazy"/>:<div className="ui12-photo-placeholder"><Package size={38}/><span>{photoLoading?'Завантаження фото…':'Фото ще немає'}</span></div>}
    {photos.length>1&&<><button type="button" className="ui12-photo-arrow prev" aria-label="Попереднє фото" onClick={()=>setActivePhoto(i=>(i+photos.length-1)%photos.length)}><ChevronLeft size={18}/></button><button type="button" className="ui12-photo-arrow next" aria-label="Наступне фото" onClick={()=>setActivePhoto(i=>(i+1)%photos.length)}><ChevronRight size={18}/></button><span className="ui12-photo-counter">{activePhoto+1} / {photos.length}</span></>}
   </div>
   {photos.length>0&&<div className="ui12-photo-thumbs" aria-label="Фотографії запчастини">{photos.map((photo,i)=><button type="button" key={photo.id||i} className={i===activePhoto?'active':''} aria-label={'Фото '+(i+1)} aria-pressed={i===activePhoto} onClick={()=>setActivePhoto(i)}><img src={photo.url} alt="" loading="lazy"/></button>)}</div>}
   {part.id&&can('inventory.edit')&&!part.archived&&<div className="ui11-photo-actions">
    {photoEnabled===true?<label className="ui11-upload-photo"><ImagePlus size={15}/>{photoBusy?'Завантаження…':'Додати фото'}
     <input type="file" aria-label="Додати фото запчастини" accept="image/jpeg,image/png,image/webp" disabled={photoBusy}
      onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.currentTarget.value='';}}/>
    </label>:<span className="ui11-photo-disabled" title="Додавання фото недоступне"><Camera size={14}/> {photoEnabled===null?'Перевірка фото…':'Додавання фото недоступне'}</span>}
    {photoError&&<p role="alert" className="ui11-inline-error">{photoError}</p>}
   </div>}
   <dl className="ui11-preview-facts">
    <div><dt>Автомобіль / донор</dt><dd>{vehicle?<Link className="part-donor-link" to={'/vehicles?donor='+vehicle.id}>{vehicle.manufacturer} {vehicle.model} · {vehicle.year} · №{vehicle.number||'—'}</Link>:'Не вказано'}</dd></div>
    <div><dt>Категорія</dt><dd>{category?categoryLabelUk(category.name):'Без категорії'}{subcategory?' · '+categoryLabelUk(subcategory.name):''}</dd></div>
    <div><dt>Статус</dt><dd>{part.catalogue_only?(part.plan_status||'У плані розбору'):part.archived?'Архівна':part.reserved_quantity>0?'Зарезервована':part.quantity>0?'В наявності':'Без залишку'}</dd></div>
    <div><dt>Залишок</dt><dd>{part.catalogue_only?'Не на складі':`${part.quantity??0} шт.`}{part.reserved_quantity>0&&<small>Резерв: {part.reserved_quantity} · Вільно: {part.available_quantity}</small>}</dd></div>
    <div><dt>OEM</dt><dd data-field="oem" data-number-present={!!part.oem_number}><StockOemField part={part} editable={can('inventory.edit')&&!part.archived} onSaved={onSaved}/></dd></div>
    <div><dt>Артикул</dt><dd data-field="article" data-number-present={!!part.article_number}>{part.article_number||'Не встановлено'}{part.article_number&&part.article_brand&&<small>{part.article_brand}</small>}</dd></div>
    <div><dt>Моя ціна</dt><dd data-price-state={part.selling_price==null?"missing":"set"}>{part.selling_price!=null?money(part.selling_price,part.currency||'UAH'):'Не встановлено'}</dd></div>
   </dl>
   {editingOem&&<button type="button" onClick={onEdit}>Змінити артикул у картці</button>}
   {editingOem&&oemOptions(part).length===0&&can('inventory.edit')&&'color_name' in part&&<div className="ui11-oem-editor">
    <PartCharacteristicsEditor key={part.id} part={part} kind="oem" onSaved={row=>{setEditingOem(false);onSaved(row);}} onClose={()=>setEditingOem(false)}/>
   </div>}
   <div className="ui11-preview-buttons">
    
    {part.id&&can('parts.change_price')&&!part.archived&&<details ref={pricePanel} className="part-preview-price-edit"><summary>Змінити ціну</summary><SellerPriceEditor key={part.id} part={part} initialOpen onSaved={row=>{if(pricePanel.current)pricePanel.current.open=false;onSaved(row);}}/></details>}
    {part.id&&can('inventory.edit')&&!part.archived&&<>{oemOptions(part).length===0&&<button type="button" className="secondary" onClick={()=>setEditingOem(v=>!v)}><Pencil size={14}/> OEM / артикул</button>}<button type="button" className="secondary" onClick={onEdit}><Pencil size={14}/> Редагувати дані</button></>}
    {onNotes&&can('parts.notes')&&part.id&&<button type="button" onClick={onNotes}>Додати нотатку</button>}
    {onInspection&&can('parts.inspect')&&part.id&&<button type="button" onClick={onInspection}>Стан і перевірка</button>}
    {contextActions}
    {part.id&&<button type="button" className="secondary" onClick={onOpen}><FileSearch size={16}/> Відкрити картку <ExternalLink size={14}/></button>}
   </div>
  </>}
 </aside></QuickPreviewFrame>;
}
