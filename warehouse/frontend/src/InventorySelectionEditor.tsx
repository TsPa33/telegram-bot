import {useEffect,useState} from 'react';
import {api,type Row} from './api';
import {Modal,RecordForm} from './components';
import {partFields} from './pages/Inventory';
import InventoryQuantity from './InventoryQuantity';
import {SellerPriceEditor} from './MarketPricing';
export default function InventorySelectionEditor({ids,mode,vehicles,categories,onClose,onSaved}:{ids:string[];mode:string;vehicles:Row[];categories:Row[];onClose:()=>void;onSaved:()=>void}){
 const [index,setIndex]=useState(0),[part,setPart]=useState<Row|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;setPart(null);setError('');api('/parts/'+ids[index]).then(p=>{if(active)setPart(p);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[index]);
 const next=()=>{onSaved();if(index+1===ids.length)onClose();else setIndex(n=>n+1);};
 const labels:Record<string,string>={quantity:'Змінити кількість',price:'Оновити ціну',numbers:'Призначити OEM / артикул',category:'Змінити категорію'};
 const keys=mode==='numbers'?['oem_number','article_number']:['category_id','subcategory_id'];
 return <Modal title={labels[mode]+' · '+(index+1)+' із '+ids.length} onClose={onClose}>{error&&<p role="alert">{error}</p>}{!part&&!error&&<p role="status">Завантаження…</p>}{part&&<><h3>{part.name}</h3>{mode==='quantity'?<><InventoryQuantity key={part.id} part={part} onSaved={p=>{setPart(p);onSaved();}}/><button onClick={next}>Далі</button></>:mode==='price'?<SellerPriceEditor key={part.id} part={part} initialOpen onSaved={next}/>:<RecordForm key={part.id} fields={partFields(vehicles,categories).filter(f=>keys.includes(f.key))} initial={part} onSave={async body=>{
 const current=await api('/parts/'+part.id);
 const fields=['name','category_id','subcategory_id','vehicle_id','color_name','paint_code','oem_number','article_number','condition','unit_cost','selling_price','currency','location','compatibility_notes','description','internal_notes','availability','individually_tracked','serial_number'];
 const payload=Object.fromEntries(fields.filter(k=>k in current).map(k=>[k,current[k]]));
 await api('/parts/'+part.id,'PUT',{...payload,...body});next();
 }}/>}<button className="secondary" onClick={next}>Пропустити позицію</button></>}</Modal>;
}
