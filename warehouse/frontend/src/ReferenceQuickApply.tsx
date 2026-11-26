import {useContext,useRef,useState} from 'react';
import {api,ApiError,money,type Row} from './api';
import {TeamIdentity} from './permissions';
import {pricesChanged,SellerPriceEditor} from './MarketPricing';
import {cents} from './priceReferencePolicy';

export function ReferenceQuickApply({part,group,token,onSaved}:{part:Row;group:Row;token:string;onSaved?:(row:Row)=>void}){
 const identity=useContext(TeamIdentity),key='warehouse.reference-single.v1:'+JSON.stringify([identity?.id,identity?.workspace_account_id||identity?.id,part.id]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[manual,setManual]=useState(false),[done,setDone]=useState(false);
 const guard=useRef(false);
 function pending(){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
 const stored=pending(),valid=cents(group.average)!==null&&cents(group.average)!>0n&&['UAH','USD'].includes(group.currency);
 async function save(){
  if(guard.current||!valid)return;guard.current=true;setBusy(true);setError('');
  try{
   const body=pending()||{selling_price:String(group.average),currency:group.currency,expected_token:token,request_key:crypto.randomUUID()};
   // A different cohort must not silently submit an older uncertain request.
   if(body.selling_price!==String(group.average)||body.currency!==group.currency)throw Error('Є непідтверджений запис іншої ціни. Відкрийте відповідний орієнтир.');
   sessionStorage.setItem(key,JSON.stringify(body));
   await api('/parts/'+part.id+'/price','PATCH',body);
   sessionStorage.removeItem(key);setDone(true);pricesChanged();
   if(onSaved){try{onSaved(await api('/parts/'+part.id));}catch{/* confirmed write; refresh event already emitted */}}
  }catch(e){if(e instanceof ApiError&&e.status<500)sessionStorage.removeItem(key);setError((e as Error).message);}
  finally{guard.current=false;setBusy(false);}
 }
 return <div className="reference-quick-actions">
  <button className="primary" type="button" disabled={busy||done||!valid} onClick={()=>void save()}>{done?'Ціну встановлено':stored?'Перевірити запис ціни':part.selling_price!=null?'Замінити на '+money(group.average,group.currency):'Встановити '+money(group.average,group.currency)}</button>
  <button type="button" className="secondary" disabled={busy||!!stored} onClick={()=>setManual(v=>!v)}>Редагувати вручну</button>
  {manual&&<SellerPriceEditor part={part} initialOpen onSaved={onSaved}/>}
  {error&&<p role="alert">{error}</p>}
 </div>;
}
