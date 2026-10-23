import {useEffect,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {all} from './api';
import SalesWorkspace from './SalesWorkspace';
import Dismantling from './Dismantling';
import {Empty} from './components';
import {State,useLoad,type Notify} from './shared';

type Preference={mode:'general'|'donors';donor:string};
function read(key:string):Preference {
 try {const p=JSON.parse(localStorage.getItem(key)||'{}');return {mode:p.mode==='donors'?'donors':'general',donor:typeof p.donor==='string'?p.donor:''};}
 catch{return {mode:'general',donor:''};}
}
export default function InventoryWorkspace({accountId,notify}:{accountId:string;notify:Notify}) {
 const key='warehouse-inventory-view:'+accountId;
 const [preference,setPreference]=useState(()=>read(key));
 const [params,setParams]=useSearchParams(),donor=params.get('vehicle_id')||'';
 const {data:vehicles,error,loading,reload}=useLoad(()=>all('/vehicles'),[]);
 useEffect(()=>{window.addEventListener('warehouse:inventory-changed',reload);return()=>window.removeEventListener('warehouse:inventory-changed',reload);},[]);
 const [restored,setRestored]=useState(false);
 const [storageError,setStorageError]=useState(''),[planOpen,setPlanOpen]=useState(false);
 function save(next:Preference){setPreference(next);try{localStorage.setItem(key,JSON.stringify(next));setStorageError('');}catch{setStorageError('Не вдалося запам’ятати режим у цьому браузері.');}}
 useEffect(()=>{
  if(!vehicles||restored)return;
  setRestored(true);
  if(preference.mode==='donors'&&!donor&&vehicles.some(v=>v.id===preference.donor))setParams({vehicle_id:preference.donor},{replace:true});
 },[vehicles,restored]);
 useEffect(()=>{
  if(preference.mode!=='donors'||!vehicles)return;
  if(donor&&!vehicles.some(v=>v.id===donor)){
   save({...preference,donor:''});setParams({},{replace:true});
  }
 },[vehicles,donor,preference.mode]);
 function choose(id:string){setPlanOpen(false);save({mode:'donors',donor:id});setParams(id?{vehicle_id:id}:{});}
 function switchMode(mode:Preference['mode']){
  const remembered=donor||preference.donor;
  save({mode,donor:remembered});
  setParams(mode==='donors'&&vehicles?.some(v=>v.id===remembered)?{vehicle_id:remembered}:{});
 }
 const vehicle=vehicles?.find(v=>v.id===donor);
 return <>
  <nav className="inventory-modes" aria-label="Режим складу">
   <button aria-pressed={preference.mode==='donors'} onClick={()=>switchMode('donors')}>За автомобілями</button>
   <button aria-pressed={preference.mode==='general'} onClick={()=>switchMode('general')}>Загальний склад</button>
  </nav>
  {storageError&&<p role="status">{storageError}</p>}
  {preference.mode==='general'?<SalesWorkspace accountId={accountId} notify={notify}/>:<>
   <State error={error} loading={loading}/>
   {error&&<button onClick={reload}>Спробувати знову</button>}
   {!vehicle&&<><h1>Склад за автомобілями</h1><section className="donor-stock-grid" aria-label="Автомобілі на складі">
    {vehicles?.map(v=><button className="donor-stock-card" key={v.id} onClick={()=>choose(v.id)}><strong>{v.manufacturer} {v.model}</strong><span>{v.year} · №{v.number}</span><small>На складі: {v.stock_positions}</small></button>)}
    {!loading&&!error&&!vehicles?.length&&<Empty title="Автомобілів поки немає">Додайте автомобіль у розділі «Автомобілі».</Empty>}
   </section></>}
   {vehicle&&<>
    <div className="donor-stock-switch"><label>Автомобіль<select aria-label="Автомобіль складу" value={donor} onChange={e=>choose(e.target.value)}>{vehicles?.map(v=><option key={v.id} value={v.id}>{v.manufacturer} {v.model} · {v.year} · №{v.number}</option>)}</select></label><button onClick={()=>choose('')}>Усі автомобілі</button></div>
    <h1>{vehicle.manufacturer} {vehicle.model} · {vehicle.year} · №{vehicle.number}</h1>
    <SalesWorkspace key={vehicle.id} accountId={accountId} notify={notify} grouped/>
    <details className="donor-potential" open={planOpen} onToggle={e=>setPlanOpen(e.currentTarget.open)}><summary>План розбору — потенційні деталі</summary><p>Це план, а не підтверджена наявність. Додавання на склад потребує окремого підтвердження.</p>{planOpen&&<Dismantling key={vehicle.id} vehicle={vehicle} onChange={()=>{reload();window.dispatchEvent(new Event('warehouse:inventory-changed'));}} onInventory={()=>setPlanOpen(false)}/>}</details>
   </>}
  </>}
 </>;
}
