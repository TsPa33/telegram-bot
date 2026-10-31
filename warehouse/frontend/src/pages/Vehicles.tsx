import {Permit,useCan} from '../permissions';
import { ArrowLeft, CarFront, Pencil, Plus, Search, LayoutGrid, List, ClipboardCheck, History, Package, Wrench, Info, Images, Coins } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, labels, money, when, type Page, type Row } from "../api";
import { Empty, Modal, Pager, RecordForm, type Field } from "../components";
import VehicleForm from "../VehicleForm";
import AletoCatalogue from "../AletoCatalogue";
import DismantlingCatalogImport from "../DismantlingCatalogImport";
import VehicleChecklist from "../VehicleChecklist";
import Dismantling from "../Dismantling";
import ManagedDismantling from "../ManagedDismantling";
import PowertrainEditor from "../PowertrainEditor";
import VehicleCard from "../VehicleCard";
import "../warehouse-ux1.css";
import "../vehicles-r114.css";
import "../vehicles-r1144.css";
import VehicleImage from "../VehicleImage";
import VehicleDonorPhotos from "../VehicleDonorPhotos";
import VehicleIdentityForm from "../VehicleIdentityForm";
import VehicleSpecificationsForm from "../VehicleSpecificationsForm";
import VehicleFinance from "../VehicleFinance";
import {choices, Confirm, Heading, option, State, useLoad, type Notify} from "../shared";
const vehicleFields: Field[] = [
  { key: "manufacturer", label: "Виробник", required: true },
  { key: "model", label: "Модель", required: true },
  { key: "generation", label: "Покоління" },
  {
    key: "year",
    label: "Рік",
    type: "number",
    required: true,
    min: 1886,
    max: 2100,
  },
  { key: "engine", label: "Двигун" },
  {
    key: "fuel_type",
    label: "Тип палива",
    options: ["", "Бензин", "Дизель", "Гібрид", "Електро", "Газ"].map((x) =>
      option(x, x || "Не вказано"),
    ),
  },
  { key: "transmission", label: "КПП" },
  { key: "vin", label: "VIN", hint: "17 символів, необов’язково" },
  {
    key: "acquisition_date",
    label: "Дата придбання",
    type: "date",
    required: false,
  },
  {
    key: "acquisition_cost",
    label: "Вартість придбання, ₴",
    type: "number",
    min: 0,
  },
  {
    key: "status",
    label: "Статус",
    options: choices(["planned", "dismantling", "completed"]),
  },
  { key: "notes", label: "Примітки", type: "textarea", wide: true },
];
export default function Vehicles({notify}:{notify:Notify}) {
  const can=useCan();
  const [view,setView]=useState<'cards'|'table'>('cards'),[statusFilter,setStatusFilter]=useState(''),[q,setQ]=useState(''),[page,setPage]=useState(0),[edit,setEdit]=useState<Row|null>(null),[created,setCreated]=useState<Row|null>(null),[detail,setDetail]=useState<Row|null>(null),[confirm,setConfirm]=useState<Row|null>(null),[showInfo,setShowInfo]=useState(false);
  const {data,error,loading,reload}=useLoad(()=>api<Page>(`/vehicles?q=${encodeURIComponent(q)}&limit=50&offset=${page*50}`),[q,page]);
  const navigate=useNavigate(),[params,setParams]=useSearchParams(),donorId=params.get('donor');
  function openDetail(row:Row,info=false){setShowInfo(info);setDetail(row);setParams({donor:row.id,...(info?{info:'1'}:{})});}
  function closeDetail(){setDetail(null);setParams({});}
  function saved(row:Row){setDetail(current=>current?.id===row.id?row:current);setCreated(current=>current?.id===row.id?row:current);reload();}
  async function refresh(){reload();if(detail){try{setDetail(await api(`/vehicles/${detail.id}`));}catch(e){notify((e as Error).message);}}}
  useEffect(()=>{
    if(!donorId){setDetail(null);return;}setShowInfo(params.get('info')==='1');if(detail?.id===donorId)return;
    let active=true;api(`/vehicles/${encodeURIComponent(donorId)}`).then(row=>{if(active)setDetail(row);}).catch(e=>{if(active)notify(e.message);});
    return ()=>{active=false;};
  },[donorId,params.get('info')]);
  return <>
    {!detail&&<><Heading eyebrow="АВТОМОБІЛІ" title="Автомобілі" description="Керуйте автомобілями-донорами, їхніми характеристиками та процесом розбору.">
      <Permit permission="vehicles.create"><button className="secondary" onClick={()=>setEdit({status:'dismantling'})}><Plus size={17}/>Додати автомобіль</button></Permit>
    </Heading>
    {created&&<p role="status">Додано: {created.manufacturer} {created.model} · {created.year}. <button onClick={()=>openDetail(created)}>Відкрити картку</button></p>}
    <div className="r114-toolbar">
      <label className="search vehicle-search"><Search size={17}/><input aria-label="Пошук автомобілів" placeholder="Марка, модель, номер або VIN" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}}/></label>
      <select aria-label="Фільтр статусу автомобіля" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="">Усі статуси</option><option value="planned">Заплановано</option><option value="dismantling">На розборі</option><option value="completed">Завершено</option></select>
      <div className="r114-view-toggle" role="group" aria-label="Режим відображення"><button type="button" aria-pressed={view==='cards'} onClick={()=>setView('cards')}><LayoutGrid size={15}/> Плитка</button><button type="button" aria-pressed={view==='table'} onClick={()=>setView('table')}><List size={15}/> Таблиця</button></div>
    </div>
    <State error={error} loading={loading}/>
    {data&&<div className="r114-summary" aria-label="Автомобілі на поточній сторінці"><div><CarFront size={18}/><span><strong>{data.total}</strong><small>Усього автомобілів</small></span></div><div><Wrench size={18}/><span><strong>{data.items.filter(v=>v.status==='dismantling').length}</strong><small>На розборі (ця сторінка)</small></span></div><div><Package size={18}/><span><strong>{data.items.reduce((n,v)=>n+(Number(v.stock_positions)||0),0).toLocaleString('uk-UA')}</strong><small>Позицій на складі (ця сторінка)</small></span></div><div><ClipboardCheck size={18}/><span><strong>{data.items.filter(v=>v.status==='completed').length}</strong><small>Завершено (ця сторінка)</small></span></div></div>}
    {(()=>{const items=(data?.items||[]).filter(v=>!statusFilter||v.status===statusFilter);return view==='cards'?<section className="vehicle-grid r114-grid" aria-label="Список автомобілів">
      {items.map(v=><VehicleCard key={v.id} vehicle={v} context="vehicles" onParts={()=>openDetail(v)} onData={()=>openDetail(v,true)} onSaved={saved}/>)}
      {!loading&&!items.length&&<Empty title={q||statusFilter?'Автомобілів не знайдено':'Додайте перший автомобіль'}>Змініть пошук або фільтр.</Empty>}
    </section>:<section className="r114-table-wrap" aria-label="Таблиця автомобілів"><table><thead><tr><th>Автомобіль</th><th>Рік / №</th><th>Статус</th><th>Позицій</th><th>Дії</th></tr></thead><tbody>{items.map(v=><tr key={v.id}><td><strong>{v.manufacturer} {v.model}</strong><small>{v.vin?'VIN: '+v.vin:'VIN не вказано'}</small></td><td>{v.year} · №{v.number??'—'}</td><td>{labels[v.status]||'Не уточнено'}</td><td>{v.stock_positions??'—'}</td><td><button onClick={()=>openDetail(v,true)}>Картка авто</button><button onClick={()=>openDetail(v)}>Розбір</button></td></tr>)}</tbody></table>{!loading&&!items.length&&<p>Автомобілів не знайдено.</p>}</section>})()}
    {data&&<Pager total={data.total} page={page} setPage={setPage}/>}</>}
    {edit&&<Modal title={edit.id?'Редагувати автомобіль':'Новий автомобіль-донор'} onClose={()=>setEdit(null)}>
      {edit.id?<RecordForm initial={edit} fields={vehicleFields.filter(f=>f.key!=='acquisition_cost'||can('parts.view_cost'))} submit="Зберегти зміни" onSave={async values=>{
        const row=await api('/vehicles/'+edit.id,'PUT',values);
        saved(row);setEdit(null);notify('Дані автомобіля збережено');
      }}/>:<VehicleForm initial={edit} fields={vehicleFields.filter(f=>f.key!=='acquisition_cost'||can('parts.view_cost'))} onSave={async values=>{
        const row=await api('/vehicles'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',values);
        if(!edit.id){setCreated(row);setQ('');setPage(0);}saved(row);setEdit(null);notify('Дані автомобіля збережено');
      }}/>} 
    </Modal>}
    {detail&&<section className="ux1-workspace" aria-label="Автомобіль і запчастини"><button className="ux1-back" onClick={closeDetail}><ArrowLeft size={16}/>Автомобілі</button>
      <VehicleDetail key={detail.id} vehicle={detail} showInfo={showInfo} onSaved={saved} onArchive={()=>{setConfirm(detail);}} onEdit={async()=>{try{const row=await api(`/vehicles/${detail.id}`);setEdit(row);}catch(e){notify((e as Error).message);}}} onRefresh={refresh} notify={notify} onInventory={()=>navigate(`/inventory?vehicle_id=${detail.id}`)}/>
    </section>}
    {confirm&&<Confirm destructive title="Архівувати автомобіль?" text="Автомобіль залишиться в історії. Його запчастини залишаться на складі." onClose={()=>setConfirm(null)} onConfirm={async()=>{await api('/archive/vehicles/'+confirm.id,'POST');setConfirm(null);closeDetail();reload();notify('Автомобіль переміщено в архів');}}/>}
  </>;
}
function VehicleDetail({
  vehicle: v,
  onEdit,
  onRefresh,
  notify,
  onInventory,
  onSaved,
  onArchive,
  showInfo,
}: {
  vehicle: Row;
  onSaved: (row:Row)=>void;
  onArchive: ()=>void;
  showInfo: boolean;
  onEdit: () => void;
  onRefresh: () => void;
  notify: Notify;
  onInventory: () => void;
}) {
  const can=useCan();
  const canCatalog=['dismantling.manage','vehicles.view','catalog.view'].every(can);
  const canReceipt=canCatalog&&can('inventory.create')&&can('inventory.adjust_quantity');
  const {
    data: d,
    error,
    loading,
    reload: reloadAnalytics,
  } = useLoad(() => can('analytics.view')?api(`/vehicles/${v.id}/analytics`):Promise.resolve(null), [v.id]);
  const [busy, setBusy] = useState(false);
  const [photoRevision,setPhotoRevision]=useState(0);
  const [legacyVehicle,setLegacyVehicle]=useState('');
  const [tab,setTab]=useState(showInfo?'info':'parts');
  useEffect(()=>setTab(showInfo?'info':'parts'),[showInfo]);
  const history=useLoad(()=>tab==='history'&&can('audit.view')?api(`/audit?vehicle_id=${v.id}&limit=50`):Promise.resolve(null),[v.id,tab]);
  return (
    <>
      <header className="r1144-donor-header">
       <VehicleDonorPhotos vehicle={v} mode="hero" revision={photoRevision} onChanged={()=>setPhotoRevision(i=>i+1)}/>
       <div className="r1144-donor-main">
        <div className="r1144-donor-title"><h1>{v.manufacturer} {v.model} · {v.year} · №{v.number??'—'}</h1><span className="r1144-status">{labels[v.status]||'Не уточнено'}</span></div>
        <div className="r1144-donor-spec-line">
         <span><Wrench size={16}/>{[v.fuel_type,v.engine_displacement_l?v.engine_displacement_l+' л':null,v.engine_variant||v.engine].filter(Boolean).join(' · ')||'Двигун не уточнено'}</span>
         <span><Cog size={16}/>{[v.transmission,v.drive_type].filter(Boolean).join(' · ')||'КПП не уточнено'}</span>
         <span><ClipboardCheck size={16}/> VIN: {v.vin||'Не вказано'}</span>
        </div>
        <div className="r1144-donor-actions">
         <button type="button" className="primary" onClick={onInventory}><Package size={16}/> Склад запчастин</button>
         <button type="button" onClick={()=>setTab('info')}><Info size={15}/> Картка авто</button>
         <button type="button" onClick={()=>setTab('photos')}><Images size={15}/> Фото</button>
         {can('parts.view_cost')&&<button type="button" onClick={()=>setTab('finance')}><Coins size={15}/> Фінанси</button>}
         {!v.archived&&<Permit permission="vehicles.edit"><button type="button" onClick={onEdit}><Pencil size={15}/> Редагувати авто</button></Permit>}
        </div>
       </div>
      </header>
      <nav className="r1144-tabs" aria-label="Розділи автомобіля">
       {[
        ['info','Основне'],['parts','Розбір і запчастини'],['photos','Фото'],
        ...(can('parts.view_cost')?[['finance','Фінанси']]:[]),
        ...(can('audit.view')?[['history','Історія операцій']]:[])
       ].map(([key,label])=><button type="button" key={key} className={tab===key?'active':''} aria-current={tab===key?'page':undefined} onClick={()=>setTab(key)}>{label}</button>)}
      </nav>
      <div hidden={tab!=='parts'}>
      {legacyVehicle!==v.id&&can('catalog.view')&&can('vehicles.view')&&<ManagedDismantling key={v.id} vehicle={v} onSaved={onSaved}/>}
      <details className="vehicle-secondary"><summary>Попередній довідник та джерела</summary>{can('catalog.view')&&can('vehicles.view')&&<AletoCatalogue key={v.id} vehicleId={v.id}/>}{canCatalog&&<DismantlingCatalogImport onImported={()=>{onRefresh();}}/>}
      {canCatalog&&(legacyVehicle===v.id?<><button onClick={()=>setLegacyVehicle('')}>До основного списку деталей</button><Dismantling vehicle={v} onChange={() => {reloadAnalytics();onRefresh();}} onInventory={onInventory} /></>:!v.dismantling_v3?.revision&&<button className="secondary" onClick={()=>setLegacyVehicle(v.id)}>Відкрити попередній план</button>)}
      </details>
      </div>
      {tab==='history'&&<section className="ux1-history" aria-label="Історія автомобіля"><State error={history.error} loading={history.loading}/>{history.data?.items.map((r:Row)=><article key={r.id}><strong>{labels[r.type]||'Складська операція'}</strong><span>{when(r.created_at)}</span><p>{r.reason}</p></article>)}{history.data?.items.length===0&&<p>Операцій ще немає.</p>}{history.data?.total>50&&<p>Показано останні 50 операцій.</p>}</section>}
      <div hidden={tab!=='info'}>
       <div className="r1144-profile-grid">
        <VehicleIdentityForm vehicle={v} onSaved={onSaved} onArchive={onArchive}/>
        <VehicleSpecificationsForm vehicle={v} onSaved={onSaved}/>
       </div>
       <div className="r1144-donor-meta">
        <div><small>Придбання</small><strong>{v.acquisition_date||'Не вказано'}</strong></div>
        {can('parts.view_cost')&&<div><small>Вартість придбання</small><strong>{v.acquisition_cost==null?'Не вказано':money(v.acquisition_cost)}</strong></div>}
        <div><small>Позицій на складі</small><strong>{d?.positions??v.stock_positions??'—'}</strong></div>
        <div><small>Дані двигуна</small><strong>{v.engine_code||'Код не вказано'}</strong></div>
       </div>
       <details className="r1144-advanced"><summary>Додаткові інструменти каталогу та чекліста</summary>
        {canReceipt&&<VehicleChecklist vehicle={v}/>}
        <p className="notice">Стандартний чекліст містить можливі запчастини, а не підтверджений OEM-каталог. Нові позиції створюються з нульовим залишком.</p>
        <button type="button" disabled={busy||!canReceipt} onClick={async()=>{setBusy(true);try{const r=await api(`/vehicles/${v.id}/checklist`,'POST');notify(`Додано: ${r.created}. Уже існує: ${r.existing}`);}catch(e){notify((e as Error).message)}finally{setBusy(false)}}}>Сформувати ручний список запчастин</button>
       </details>
      </div>
      {tab==='photos'&&<VehicleDonorPhotos vehicle={v} mode="gallery" revision={photoRevision} onChanged={()=>setPhotoRevision(i=>i+1)}/>}
      {tab==='finance'&&can('parts.view_cost')&&<VehicleFinance vehicle={v} analytics={d} onSaved={onSaved}/>}

    </>
  );
}
