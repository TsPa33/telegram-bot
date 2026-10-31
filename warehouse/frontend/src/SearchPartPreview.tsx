import {useEffect,useRef,useState} from 'react';
import {Package,MapPin,FileSearch,ShoppingCart,ExternalLink,X,ChevronLeft,ChevronRight,Camera,Pencil,Save} from 'lucide-react';
import {api,money,labels,type Row} from './api';
import {useCan} from './permissions';
import SearchPartPhoto from './SearchPartPhoto';
import {categoryLabelUk} from './PartsQuickCategories';
import {SellerPriceEditor} from './MarketPricing';
import PartCharacteristicsEditor from './PartCharacteristicsEditor';

type Props={
 part:Row|null;vehicle?:Row;category?:Row;subcategory?:Row;canSell:boolean;
 onOpen:()=>void;onSell:()=>void;onEdit:()=>void;onSaved:(row:Row)=>void;
 open:boolean;onClose:()=>void;
 position:number;total:number;onPrevious:()=>void;onNext:()=>void;
 photoRevision:number;onPhotoSaved:(id:string)=>void;
};
export default function SearchPartPreview({part,vehicle,category,subcategory,canSell,onOpen,onSell,onEdit,onSaved,open,onClose,position,total,onPrevious,onNext,photoRevision,onPhotoSaved}:Props){
 const can=useCan();
 const [editingOem,setEditingOem]=useState(false);
 const [photoEnabled,setPhotoEnabled]=useState<boolean|null>(null);
 const [photoBusy,setPhotoBusy]=useState(false),[photoError,setPhotoError]=useState('');
 const photoGuard=useRef(false);
 useEffect(()=>{setEditingOem(false);setPhotoError('');},[part?.id]);
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
 return <aside id="search-part-preview" className={'ui11-preview'+(open?' open':'')} aria-label="Швидкий перегляд запчастини">
  {!part?<div className="ui11-preview-empty"><Package size={32} strokeWidth={1.2}/><strong>Оберіть запчастину</strong><p>Інформація про деталь з’явиться тут.</p></div>:<>
   <div className="ui11-preview-heading">
    <button type="button" className="ui11-preview-close" aria-label="Закрити швидкий перегляд" onClick={onClose}><X size={18}/></button>
    <div className="ui11-preview-topline"><span className="ui11-eyebrow">Швидкий перегляд</span>
     <div className="ui11-preview-navigation" aria-label="Перехід між результатами">
      <button type="button" onClick={onPrevious} disabled={position<=1} aria-label="Попередня запчастина"><ChevronLeft size={16}/></button>
      <span aria-live="polite">{position} із {total}</span>
      <button type="button" onClick={onNext} disabled={position>=total} aria-label="Наступна запчастина"><ChevronRight size={16}/></button>
     </div>
    </div>
    <h2>{part.name}</h2>
    <p>{category?categoryLabelUk(category.name):'Без категорії'} › {subcategory?categoryLabelUk(subcategory.name):'Інші деталі'}</p>
   </div>
   <div className="ui11-preview-image"><SearchPartPhoto key={part.id+':'+photoRevision} id={part.id} name={part.name}/></div>
   {can('inventory.edit')&&!part.archived&&<div className="ui11-photo-actions">
    {photoEnabled===true?<label className="ui11-upload-photo"><Camera size={15}/>{photoBusy?'Завантаження…':'Додати фото'}
     <input type="file" aria-label="Додати фото запчастини" accept="image/jpeg,image/png,image/webp" disabled={photoBusy}
      onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.currentTarget.value='';}}/>
    </label>:<span className="ui11-photo-disabled" title="Фото потребують постійного сховища на сервері"><Camera size={14}/> {photoEnabled===null?'Перевірка сховища…':'Сховище фото не підключене'}</span>}
    {photoError&&<p role="alert" className="ui11-inline-error">{photoError}</p>}
   </div>}
   <dl className="ui11-preview-facts">
    <div><dt>Автомобіль</dt><dd>{vehicle?`${vehicle.manufacturer} ${vehicle.model} · ${vehicle.year}`:'Не вказано'}</dd></div>
    <div><dt>OEM</dt><dd>{part.oem_number||'Не вказано'}</dd></div>
    <div><dt>Артикул</dt><dd>{part.article_number||'Не вказано'}</dd></div>
    <div><dt>Стан</dt><dd>{labels[part.condition]||'Не уточнено'}</dd></div>
    <div><dt>Залишок</dt><dd>{part.available_quantity??part.quantity??0} шт.</dd></div>
    <div><dt>Локація</dt><dd><MapPin size={13} aria-hidden="true"/>{part.location||'Не вказано'}</dd></div>
   </dl>
   {can('inventory.edit')&&!part.archived&&<div className="ui11-data-actions">
    <button type="button" className="secondary" onClick={()=>setEditingOem(v=>!v)}><Pencil size={14}/> {editingOem?'Згорнути OEM':'Змінити OEM'}</button>
    <button type="button" className="secondary" onClick={onEdit}><Pencil size={14}/> Редагувати дані</button>
   </div>}
   {editingOem&&can('inventory.edit')&&'color_name' in part&&<div className="ui11-oem-editor">
    <PartCharacteristicsEditor key={part.id} part={part} kind="oem" onSaved={row=>{setEditingOem(false);onSaved(row);}} onClose={()=>setEditingOem(false)}/>
   </div>}
   <div className="ui11-preview-price"><span>Моя ціна</span>
    {can('parts.change_price')&&!part.archived
     ?<SellerPriceEditor key={part.id} part={part} onSaved={onSaved}/>
     :<strong>{part.selling_price!=null?money(part.selling_price,part.currency||'UAH'):'Не встановлено'}</strong>}
    {part.selling_price==null&&<small>Ціна продажу не зазначена</small>}
   </div>
   <div className="ui11-preview-buttons">
    <button type="button" className="primary" onClick={onOpen}><FileSearch size={16}/> Відкрити картку <ExternalLink size={14}/></button>
    {canSell&&<button type="button" className="secondary" disabled={!(part.available_quantity>0)||part.assortment_enabled===false} onClick={onSell}><ShoppingCart size={16}/> Продати</button>}
   </div>
  </>}
 </aside>;
}
