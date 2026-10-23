import {useEffect,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {all} from './api';
import SalesWorkspace from './SalesWorkspace';
import Dismantling from './Dismantling';
import StockHistory from './StockHistory';
import {Empty} from './components';
import {State,useLoad,type Notify} from './shared';

type Preference={mode:'general'|'donors';donor:string;remember:boolean};
function read(key:string):Preference {
 try {const p=JSON.parse(localStorage.getItem(key)||'{}');return {mode:p.mode==='donors'?'donors':'general',donor:typeof p.donor==='string'?p.donor:'',remember:p.remember===true};}
 catch{return {mode:'general',donor:'',remember:false};}
}
export default function InventoryWorkspace({accountId,notify}:{accountId:string;notify:Notify}) {
 const key='warehouse-inventory-view:'+accountId;
 const [preference,setPreference]=useState(()=>read(key));
 const [history,setHistory]=useState(false);
 const [params,setParams]=useSearchParams(),donor=params.get('vehicle_id')||'';
 const {data:vehicles,error,loading,reload}=useLoad(()=>Promise.all([all('/vehicles'),all('/vehicles?archived=true')]).then(groups=>groups.flat()),[]);
 useEffect(()=>{window.addEventListener('warehouse:inventory-changed',reload);return()=>window.removeEventListener('warehouse:inventory-changed',reload);},[]);
 const [restored,setRestored]=useState(false);
 const [storageError,setStorageError]=useState(''),[planOpen,setPlanOpen]=useState(false);
 function save(next:Preference){setPreference(next);try{localStorage.setItem(key,JSON.stringify(next));setStorageError('');}catch{setStorageError('Не вдалося запам’ятати режим у цьому браузері.');}}
 useEffect(()=>{
  if(!vehicles||restored)return;
  setRestored(true);
  if(preference.mode==='donors'&&preference.remember&&!donor&&vehicles.some(v=>v.id===preference.donor))setParams({vehicle_id:preference.donor},{replace:true});
 },[vehicles,restored]);
 useEffect(()=>{
  if(preference.mode!=='donors'||!vehicles)return;
  if(donor&&!vehicles.some(v=>v.id===donor)){
   save({...preference,donor:'',remember:false});setParams({},{replace:true});
  }
 },[vehicles,donor,preference.mode]);
 function choose(id:string){setHistory(false);setPlanOpen(false);save({mode:'donors',donor:id,remember:!!id&&preference.remember});setParams(id?{vehicle_id:id}:{});}
 function switchMode(mode:Preference['mode']){
  if(mode===preference.mode)return;
  setHistory(false);setPlanOpen(false);
  save({...preference,mode});
  setParams(mode==='donors'&&preference.remember&&vehicles?.some(v=>v.id===preference.donor)?{vehicle_id:preference.donor}:{});
 }
 const vehicle=vehicles?.find(v=>v.id===donor);
 return <>
  <nav className="inventory-modes" aria-label="Режим складу">
   <button aria-pressed={preference.mode==='donors'} onClick={()=>switchMode('donors')}>За автомобілями</button>
   <button aria-pressed={preference.mode==='general'} onClick={()=>switchMode('general')}>Загальний склад</button>
  </nav>
  <nav className="stock-section-tabs" aria-label="Розділ складу"><button aria-pressed={!history} onClick={()=>setHistory(false)}>Запчастини</button><button aria-pressed={history} onClick={()=>setHistory(true)}>Історія операцій</button></nav>
  {history?<StockHistory key={preference.mode==='donors'?donor:'all'} vehicleId={preference.mode==='donors'?donor:''}/>:<>
  {storageError&&<p role="status">{storageError}</p>}
  {preference.mode==='general'?<SalesWorkspace accountId={accountId} notify={notify}/>:<>
   <State error={error} loading={loading}/>
   {error&&<button onClick={reload}>Спробувати знову</button>}
   {!vehicle&&<><h1>Склад за автомобілями</h1><section className="donor-stock-grid" aria-label="Автомобілі на складі">
    {vehicles?.map(v=><article className="donor-stock-card" key={v.id}><strong>{v.manufacturer} {v.model}</strong><span>{v.year} · №{v.number}{v.archived?' · архів':''}</span>{v.stock_positions!=null&&<small>Облікованих запчастин: {v.stock_positions}</small>}<button aria-label={`Відкрити склад ${v.manufacturer} ${v.model} · ${v.year} · №${v.number}`} onClick={()=>choose(v.id)}>Відкрити склад</button></article>)}
    {!loading&&!error&&!vehicles?.length&&<Empty title="Автомобілів поки немає">Додайте автомобіль у розділі «Автомобілі».</Empty>}
   </section></>}
   {vehicle&&<>
    <header className="donor-stock-header"><h1>{vehicle.manufacturer} {vehicle.model} · {vehicle.year} · №{vehicle.number}</h1><button onClick={()=>choose('')}>Усі автомобілі</button></header>
    <div className="donor-stock-switch"><label>Автомобіль<select aria-label="Автомобіль складу" value={donor} onChange={e=>choose(e.target.value)}>{vehicles?.map(v=><option key={v.id} value={v.id}>{v.manufacturer} {v.model} · {v.year} · №{v.number}</option>)}</select></label><label className="check-inline donor-remember"><input type="checkbox" checked={preference.remember} onChange={e=>save({...preference,donor,remember:e.target.checked})}/>Запам’ятати цей автомобіль</label></div>
    <SalesWorkspace key={vehicle.id} accountId={accountId} notify={notify} grouped/>
    <details className="donor-potential" open={planOpen} onToggle={e=>setPlanOpen(e.currentTarget.open)}><summary>Каталог деталей автомобіля</summary><p>Виберіть деталі, які є на автомобілі, та додайте їх до обліку. Каталог не підтверджує товарний залишок; додавання потребує вашого підтвердження.</p>{planOpen&&<Dismantling key={vehicle.id} vehicle={vehicle} onChange={()=>{reload();window.dispatchEvent(new Event('warehouse:inventory-changed'));}} onInventory={()=>setPlanOpen(false)}/>}</details>
   </>}
  </>}
  </>}
 </>;
}
