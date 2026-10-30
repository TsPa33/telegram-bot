import {Permit,useCan} from '../permissions';
import { ArrowLeft, CarFront, Pencil, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, labels, money, when, type Page, type Row } from "../api";
import { Empty, Modal, Pager, type Field } from "../components";
import VehicleForm from "../VehicleForm";
import AletoCatalogue from "../AletoCatalogue";
import DismantlingCatalogImport from "../DismantlingCatalogImport";
import VehicleChecklist from "../VehicleChecklist";
import Dismantling from "../Dismantling";
import ManagedDismantling from "../ManagedDismantling";
import PowertrainEditor from "../PowertrainEditor";
import VehicleCard from "../VehicleCard";
import "../warehouse-ux1.css";
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
  const [q,setQ]=useState(''),[page,setPage]=useState(0),[edit,setEdit]=useState<Row|null>(null),[created,setCreated]=useState<Row|null>(null),[detail,setDetail]=useState<Row|null>(null),[confirm,setConfirm]=useState<Row|null>(null),[showInfo,setShowInfo]=useState(false);
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
    {!detail&&<><Heading eyebrow="АВТОМОБІЛІ" title="Автомобілі" description="Відкрийте автомобіль, щоб вибрати запчастини або перейти до складу.">
      <Permit permission="vehicles.create"><button className="secondary" onClick={()=>setEdit({status:'dismantling'})}><Plus size={17}/>Додати автомобіль</button></Permit>
    </Heading>
    {created&&<p role="status">Додано: {created.manufacturer} {created.model} · {created.year}. <button onClick={()=>openDetail(created)}>Відкрити картку</button></p>}
    <label className="search vehicle-search"><Search size={17}/><input aria-label="Пошук автомобілів" placeholder="Марка, модель або номер авто" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}}/></label>
    <State error={error} loading={loading}/>
    <section className="vehicle-grid" aria-label="Список автомобілів">
      {data?.items.map(v=><VehicleCard key={v.id} vehicle={v} context="vehicles" onParts={()=>openDetail(v)} onData={()=>openDetail(v,true)} onSaved={saved}/>)}
      {!loading&&!data?.items.length&&<Empty title={q?'Автомобілів не знайдено':'Додайте перший автомобіль'}>Пов’яжіть запчастини з автомобілем, щоб швидко знаходити їх на складі.</Empty>}
    </section>
    {data&&<Pager total={data.total} page={page} setPage={setPage}/>}</>}
    {edit&&<Modal title={edit.id?'Редагувати автомобіль':'Новий автомобіль-донор'} onClose={()=>setEdit(null)}>
      <VehicleForm initial={edit} fields={vehicleFields.filter(f=>f.key!=='acquisition_cost'||can('parts.view_cost'))} onSave={async values=>{
        const row=await api('/vehicles'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',values);
        if(!edit.id){setCreated(row);setQ('');setPage(0);}saved(row);setEdit(null);notify('Дані автомобіля збережено');
      }}/>
    </Modal>}
    {detail&&<section className="ux1-workspace" aria-label="Автомобіль і запчастини"><button className="ux1-back" onClick={closeDetail}><ArrowLeft size={16}/>Автомобілі</button>
      <VehicleDetail key={detail.id} vehicle={detail} showInfo={showInfo} onSaved={saved} onArchive={()=>{setConfirm(detail);}} onEdit={async()=>{try{const row=await api(`/vehicles/${detail.id}`);closeDetail();setEdit(row);}catch(e){notify((e as Error).message);}}} onRefresh={refresh} notify={notify} onInventory={()=>navigate(`/inventory?vehicle_id=${detail.id}`)}/>
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
  const [legacyVehicle,setLegacyVehicle]=useState('');
  const [tab,setTab]=useState(showInfo?'info':'parts');
  useEffect(()=>setTab(showInfo?'info':'parts'),[showInfo]);
  const history=useLoad(()=>tab==='history'&&can('audit.view')?api(`/audit?vehicle_id=${v.id}&limit=50`):Promise.resolve(null),[v.id,tab]);
  return (
    <>
      <header className="ux1-vehicle-header"><div className="ux1-vehicle-placeholder" role="img" aria-label="Фото автомобіля відсутнє"><CarFront size={44} strokeWidth={1.2}/><span>Фото відсутнє</span></div><div className="ux1-vehicle-identity"><h1>{v.manufacturer} {v.model} · {v.year} · №{v.number??'—'}</h1><div className="ux1-vehicle-tags">{[v.fuel_type,v.engine,v.transmission,v.dismantling_v3?.configuration?.values?.drive].filter(Boolean).map((value,index)=><span key={index}>{value}</span>)}{!v.engine&&!v.fuel_type&&<span>Двигун не уточнено</span>}</div>{v.vin&&<small>VIN: {v.vin}</small>}</div>{!v.archived&&<Permit permission="vehicles.edit"><button className="secondary" onClick={onEdit}><Pencil size={14}/>Редагувати авто</button></Permit>}</header>
      <nav className="ux1-tabs" aria-label="Розділи автомобіля">{[['parts','Запчастини'],['info','Загальна інформація'],...(can('audit.view')?[['history','Історія операцій']]:[])].map(([key,label])=><button key={key} aria-current={tab===key?'page':undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      <div hidden={tab!=='parts'}>
      {legacyVehicle!==v.id&&can('catalog.view')&&can('vehicles.view')&&<ManagedDismantling key={v.id} vehicle={v} onSaved={onSaved}/>}
      <details className="vehicle-secondary"><summary>Попередній довідник та джерела</summary>{can('catalog.view')&&can('vehicles.view')&&<AletoCatalogue key={v.id} vehicleId={v.id}/>}{canCatalog&&<DismantlingCatalogImport onImported={()=>{onRefresh();}}/>}
      {canCatalog&&(legacyVehicle===v.id?<><button onClick={()=>setLegacyVehicle('')}>До основного списку деталей</button><Dismantling vehicle={v} onChange={() => {reloadAnalytics();onRefresh();}} onInventory={onInventory} /></>:!v.dismantling_v3?.revision&&<button className="secondary" onClick={()=>setLegacyVehicle(v.id)}>Відкрити попередній план</button>)}
      </details>
      </div>
      {tab==='history'&&<section className="ux1-history" aria-label="Історія автомобіля"><State error={history.error} loading={history.loading}/>{history.data?.items.map((r:Row)=><article key={r.id}><strong>{labels[r.type]||'Складська операція'}</strong><span>{when(r.created_at)}</span><p>{r.reason}</p></article>)}{history.data?.items.length===0&&<p>Операцій ще немає.</p>}{history.data?.total>50&&<p>Показано останні 50 операцій.</p>}</section>}
      <div hidden={tab!=='info'}><details className="vehicle-secondary" open><summary>Дані автомобіля</summary>
      {!v.archived&&<div className="modal-actions"><Permit permission="vehicles.edit"><button onClick={onEdit}>Редагувати дані</button></Permit><Permit permission="inventory.archive"><button onClick={onArchive}>Архівувати автомобіль</button></Permit></div>}
      <dl className="details">
        {[
          ["Номер автомобіля", `№ ${v.number ?? "—"}`],
          ["Рік", v.year],
          ["Двигун", v.engine || "Не вказано"],
          ["КПП", v.transmission || "Не вказано"],
          ["VIN", v.vin || "Не вказано"],
          [
            "Придбання",
            v.acquisition_cost != null ? money(v.acquisition_cost) : "Не вказано",
          ],
          ["Дата придбання", v.acquisition_date || "Не вказано"],
          ["Примітки", v.notes || "—"],
        ].filter(([k])=>k!=='Придбання'||can('parts.view_cost')).map(([k, val]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{val}</dd>
          </div>
        ))}
      </dl>
      <State error={error} loading={loading} />
      {d && (
        <div className="detail-stats">
          <span>
            Позицій<strong>{d.positions}</strong>
          </span>
          <span>
            Одиниць<strong>{d.stock_units}</strong>
          </span>
          {can('analytics.financial')&&<span>
            Оцінка продажу<strong>{money(d.estimated_sales_value)}</strong>
          </span>}
          {can('analytics.financial')&&can('parts.view_cost')&&<span>
            Потенційна маржа<strong>{money(d.potential_gross_margin)}</strong>
          </span>}
        </div>
      )}
      <details><summary>Додатковий каталог</summary>{canReceipt&&<VehicleChecklist vehicle={v} />}</details>
      <details><summary>Ручний список зі власних категорій</summary>
      <p className="notice">
        Стандартний чекліст — перелік можливих деталей, а не точний OEM-каталог.
        Усі нові позиції мають нульовий залишок. Повторне формування зберігає
        вашу роботу.
      </p>
      <div className="modal-actions">
        <button onClick={onInventory}>Відкрити запчастини</button>
        <button
          disabled={busy||!canReceipt}
          className="primary"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api(`/vehicles/${v.id}/checklist`, "POST");
              notify(`Додано позицій: ${r.created}. Уже існує: ${r.existing}`);
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Сформувати ручний список запчастин
        </button>
      </div>
      </details>
      </details></div>
    </>
  );
}
