import {useContext,useRef,useState} from 'react';
import {api,ApiError,money,labels,type Row} from './api';
import {TeamIdentity} from './permissions';
import {pricesChanged,SellerPriceEditor} from './MarketPricing';
import {cents} from './priceReferencePolicy';

export function ReferenceQuickApply({part,groups,token,onSaved}:{part:Row;groups:Row[];token?:string;onSaved?:(row:Row)=>void}){
 const identity=useContext(TeamIdentity),key='warehouse.reference-single.v1:'+JSON.stringify([identity?.id,identity?.workspace_account_id||identity?.id,part.id]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[manual,setManual]=useState(false),[done,setDone]=useState(false);
 const guard=useRef(false);
 function pending(){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
 const stored=pending();
 const choices=token?groups.filter(g=>g.offer_count>=3&&(cents(g.average)??0n)>0n&&['UAH','USD'].includes(g.currency)):[];
 async function save(group?:Row){
  if(guard.current||(!group&&!pending()))return;guard.current=true;setBusy(true);setError('');
  try{
   const body=pending()||{selling_price:String(group!.average),currency:group!.currency,expected_token:token,request_key:crypto.randomUUID()};
   sessionStorage.setItem(key,JSON.stringify(body));
   const saved=await api('/parts/'+part.id+'/price','PATCH',body);
   sessionStorage.removeItem(key);setDone(true);pricesChanged();onSaved?.({...part,...saved});
  }catch(e){if(e instanceof ApiError&&e.status<500&&![401,403].includes(e.status))sessionStorage.removeItem(key);setError((e as Error).message);}
  finally{guard.current=false;setBusy(false);}
 }
 if(!choices.length&&!stored&&!done)return null;
 return <div className="reference-quick-actions">
  {done?<strong>Ціну встановлено</strong>:stored?<button className="primary" type="button" disabled={busy} onClick={()=>void save()}>Перевірити запис {money(stored.selling_price,stored.currency)}</button>:choices.map((g,i)=><button key={i} className="primary" type="button" disabled={busy} onClick={()=>void save(g)}>{part.selling_price!=null?'Замінити на ':'Встановити '}{money(g.average,g.currency)} · {labels[g.condition]||'Стан невідомий'}{g.match==='similar'?' · схожі деталі':''}</button>)}
  {!done&&<button type="button" className="secondary" disabled={busy||!!stored} onClick={()=>setManual(v=>!v)}>Редагувати вручну</button>}
  {manual&&<SellerPriceEditor part={part} initialOpen onSaved={onSaved}/>}
  {error&&<p role="alert">{error}</p>}
 </div>;
}
