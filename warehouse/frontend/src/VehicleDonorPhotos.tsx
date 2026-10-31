import {useEffect,useRef,useState} from 'react';
import {Camera, ChevronLeft, ChevronRight, Images, Trash2, Upload} from 'lucide-react';
import {api,type Row} from './api';
import {useCan} from './permissions';
import VehicleImage from './VehicleImage';

export default function VehicleDonorPhotos({vehicle,mode='hero',revision=0,onChanged}:{
 vehicle:Row;mode?:'hero'|'gallery';revision?:number;onChanged?:()=>void
}){
 const can=useCan();
 const input=useRef<HTMLInputElement>(null);
 const [photos,setPhotos]=useState<Row[]>([]);
 const [index,setIndex]=useState(0);
 const [enabled,setEnabled]=useState(false);
 const [busy,setBusy]=useState(false);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');
 const editable=can('vehicles.edit')&&!vehicle.archived;
 useEffect(()=>{let live=true;api<Row>('/settings').then(r=>{if(live)setEnabled(r.photos_enabled===true)}).catch(()=>{});return()=>{live=false}},[]);
 useEffect(()=>{let live=true;setLoading(true);api<Row[]>('/vehicles/'+encodeURIComponent(vehicle.id)+'/photos').then(r=>{if(live){setPhotos(r);setIndex(0);}}).catch(e=>{if(live)setError((e as Error).message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[vehicle.id,revision]);
 const current=photos[Math.min(index,photos.length-1)];
 async function upload(file:File){
  if(busy||!editable||!enabled)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){setError('Оберіть JPEG, PNG або WebP');return}
  if(file.size>5*1024*1024){setError('Максимальний розмір — 5 МБ');return}
  setBusy(true);setError('');setMessage('');
  try{const body=new FormData();body.append('file',file);await api('/vehicles/'+vehicle.id+'/photos','POST',body,201);setMessage('Фотографію додано');onChanged?.();}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function remove(){
  if(!current||busy||!editable)return;
  if(!window.confirm('Видалити вибране фото автомобіля?'))return;
  setBusy(true);setError('');
  try{await api('/vehicles/'+vehicle.id+'/photos/'+current.id,'DELETE',undefined,204);setMessage('Фотографію видалено');onChanged?.();}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <section className={'r1144-photos r1144-photos-'+mode} aria-label="Фотографії автомобіля">
  <div className="r1144-photo-frame">
   {current?<img className="r1144-own-photo" src={current.url} alt={vehicle.manufacturer+' '+vehicle.model+' — завантажена фотографія донора'}/>:<><VehicleImage vehicle={vehicle}/><span className="r1144-reference-label">Довідкова ілюстрація, не фото цього донора</span></>}
   {mode==='hero'&&editable&&<button type="button" className="r1144-photo-change" disabled={!enabled||busy} title={!enabled?'Сховище фотографій не підключене':'Змінити фотографію'} onClick={()=>input.current?.click()}><Camera size={15}/> {photos.length?'Додати фото':'Змінити фото'}</button>}
  </div>
  {mode==='gallery'&&<>
   <div className="r1144-gallery-bar"><strong><Images size={17}/> Фото автомобіля · {photos.length} із 12</strong>
    <div className="r1144-gallery-actions">{editable&&<><button type="button" disabled={!enabled||busy||photos.length>=12} onClick={()=>input.current?.click()}><Upload size={15}/> Додати фото</button><button type="button" disabled={!current||busy} onClick={remove}><Trash2 size={15}/> Видалити</button></>}
     <button type="button" disabled={index<=0} onClick={()=>setIndex(i=>Math.max(0,i-1))} aria-label="Попереднє фото"><ChevronLeft size={16}/></button>
     <button type="button" disabled={index>=photos.length-1} onClick={()=>setIndex(i=>Math.min(photos.length-1,i+1))} aria-label="Наступне фото"><ChevronRight size={16}/></button>
    </div>
   </div>
   {photos.length>0&&<div className="r1144-thumbnails">{photos.map((p,i)=><button type="button" className={i===index?'active':''} key={p.id} aria-label={'Вибрати фото '+(i+1)} aria-pressed={i===index} onClick={()=>setIndex(i)}><img src={p.url} alt=""/></button>)}</div>}
  </>}
  <input ref={input} type="file" className="r1144-file-hidden" accept="image/jpeg,image/png,image/webp" onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);e.target.value='';}}/>
  {loading&&mode==='gallery'&&<small>Завантаження фотографій…</small>}
  {!enabled&&editable&&mode==='gallery'&&<p className="r1144-storage-note" role="status">Сховище фото не налаштоване. Завантаження доступне після підключення постійного сховища до Warehouse API.</p>}
  {error&&<p role="alert" className="error">{error}</p>}
  {message&&mode==='gallery'&&<p role="status">{message}</p>}
 </section>;
}
