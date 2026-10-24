import { ArrowRight, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, money, type Page, type Row } from "../api";
import { Empty, Modal, Pager, type Field } from "../components";
import VehicleForm from "../VehicleForm";
import VehicleChecklist from "../VehicleChecklist";
import Dismantling from "../Dismantling";
import PowertrainEditor from "../PowertrainEditor";
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
  const [q,setQ]=useState(''),[page,setPage]=useState(0),[edit,setEdit]=useState<Row|null>(null),[created,setCreated]=useState<Row|null>(null),[detail,setDetail]=useState<Row|null>(null),[confirm,setConfirm]=useState<Row|null>(null),[showInfo,setShowInfo]=useState(false);
  const {data,error,loading,reload}=useLoad(()=>api<Page>(`/vehicles?q=${encodeURIComponent(q)}&limit=50&offset=${page*50}`),[q,page]);
  const navigate=useNavigate(),[params,setParams]=useSearchParams(),donorId=params.get('donor');
  function openDetail(row:Row,info=false){setShowInfo(info);setDetail(row);setParams({donor:row.id});}
  function closeDetail(){setDetail(null);setParams({});}
  function saved(row:Row){setDetail(current=>current?.id===row.id?row:current);setCreated(current=>current?.id===row.id?row:current);reload();}
  async function refresh(){reload();if(detail){try{setDetail(await api(`/vehicles/${detail.id}`));}catch(e){notify((e as Error).message);}}}
  useEffect(()=>{
    if(!donorId){setDetail(null);return;}if(detail?.id===donorId)return;
    let active=true;api(`/vehicles/${encodeURIComponent(donorId)}`).then(row=>{if(active)setDetail(row);}).catch(e=>{if(active)notify(e.message);});
    return ()=>{active=false;};
  },[donorId]);
  return <>
    <Heading eyebrow="АВТОМОБІЛІ" title="Автомобілі" description="Відкрийте автомобіль, щоб вибрати запчастини або перейти до складу.">
      <button className="secondary" onClick={()=>setEdit({status:'dismantling'})}><Plus size={17}/>Додати автомобіль</button>
    </Heading>
    {created&&<p role="status">Додано: {created.manufacturer} {created.model} · {created.year}. <button onClick={()=>openDetail(created)}>Відкрити картку</button></p>}
    <label className="search vehicle-search"><Search size={17}/><input aria-label="Пошук автомобілів" placeholder="Марка, модель або номер авто" value={q} onChange={e=>{setQ(e.target.value);setPage(0);}}/></label>
    <State error={error} loading={loading}/>
    <section className="vehicle-grid" aria-label="Список автомобілів">
      {data?.items.map(v=><article className="vehicle-summary-card" key={v.id}>
        <div className="vehicle-summary-head"><div><button className="text-button strong" onClick={()=>openDetail(v)}>{v.manufacturer} {v.model}</button><p>{v.year} · №{v.number??'—'}</p></div><span className="vehicle-stock-count">На складі <b>{v.stock_positions??'…'}</b></span></div>
        <button className="secondary vehicle-parts-action" aria-label={`Запчастини ${v.manufacturer} ${v.model}`} onClick={()=>openDetail(v)}>Запчастини <ArrowRight size={15} aria-hidden="true"/></button>
        <PowertrainEditor vehicle={v} onSaved={saved}/>
        <button className="text-button vehicle-data-action" onClick={()=>openDetail(v,true)}>Дані автомобіля</button>
      </article>)}
      {!loading&&!data?.items.length&&<Empty title={q?'Автомобілів не знайдено':'Додайте перший автомобіль'}>Пов’яжіть запчастини з автомобілем, щоб швидко знаходити їх на складі.</Empty>}
    </section>
    {data&&<Pager total={data.total} page={page} setPage={setPage}/>}
    {edit&&<Modal title={edit.id?'Редагувати автомобіль':'Новий автомобіль-донор'} onClose={()=>setEdit(null)}>
      <VehicleForm initial={edit} fields={vehicleFields} onSave={async values=>{
        const row=await api('/vehicles'+(edit.id?'/'+edit.id:''),edit.id?'PUT':'POST',values);
        if(!edit.id){setCreated(row);setQ('');setPage(0);}saved(row);setEdit(null);notify('Дані автомобіля збережено');
      }}/>
    </Modal>}
    {detail&&<Modal title={`${detail.manufacturer} ${detail.model} · ${detail.year} · №${detail.number??'—'}`} onClose={closeDetail}>
      <VehicleDetail key={detail.id} vehicle={detail} showInfo={showInfo} onSaved={saved} onArchive={()=>{setConfirm(detail);}} onEdit={async()=>{try{const row=await api(`/vehicles/${detail.id}`);closeDetail();setEdit(row);}catch(e){notify((e as Error).message);}}} onRefresh={refresh} notify={notify} onInventory={()=>navigate(`/inventory?vehicle_id=${detail.id}`)}/>
    </Modal>}
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
  const {
    data: d,
    error,
    loading,
    reload: reloadAnalytics,
  } = useLoad(() => api(`/vehicles/${v.id}/analytics`), [v.id]);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <PowertrainEditor vehicle={v} onSaved={onSaved}/>
      <Dismantling vehicle={v} onChange={() => {reloadAnalytics();onRefresh();}} onInventory={onInventory} />
      <details className="vehicle-secondary" open={showInfo}><summary>Дані автомобіля</summary>
      {!v.archived&&<div className="modal-actions"><button onClick={onEdit}>Редагувати дані</button><button onClick={onArchive}>Архівувати автомобіль</button></div>}
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
        ].map(([k, val]) => (
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
          <span>
            Оцінка продажу<strong>{money(d.estimated_sales_value)}</strong>
          </span>
          <span>
            Потенційна маржа<strong>{money(d.potential_gross_margin)}</strong>
          </span>
        </div>
      )}
      <details><summary>Додатковий каталог</summary><VehicleChecklist vehicle={v} /></details>
      <details><summary>Ручний список зі власних категорій</summary>
      <p className="notice">
        Стандартний чекліст — перелік можливих деталей, а не точний OEM-каталог.
        Усі нові позиції мають нульовий залишок. Повторне формування зберігає
        вашу роботу.
      </p>
      <div className="modal-actions">
        <button onClick={onInventory}>Відкрити запчастини</button>
        <button
          disabled={busy}
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
      </details>
    </>
  );
}
