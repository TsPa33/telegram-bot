import { useEffect, useState } from "react";
import { api, type Row } from "./api";
import { Modal } from "./components";
import { PartDetail } from "./pages/Inventory";
import DismantlingBoard from "./DismantlingBoard";
import PlanPartsDonorAnalysis from "./PlanPartsDonorAnalysis";

/** One existing board and ledger, exact Catalogue source IDs separate from K-Type. */
export default function UnifiedCatalogue({vehicle,onSaved,view="operations"}:{vehicle:Row;onSaved:(r:Row)=>void;view?:"operations"|"settings"}) {
  const [detail,setDetail]=useState<Row|null>(null);
  const [revision,setRevision]=useState(0);
  const [state,setState]=useState<Row|null>(null),[model,setModel]=useState(""),[mod,setMod]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  useEffect(()=>{let live=true; setState(null);setModel("");setMod("");api(`/vehicles/${vehicle.id}/unified-catalogue`).then(r=>{if(live)setState(r)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[vehicle.id]);
  async function loadModel(value:string){setModel(value);setMod("");setBusy(true);setError("");try{setState(await api(`/vehicles/${vehicle.id}/unified-catalogue?model_id=${value}`))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  async function create(){setBusy(true);setError("");try{const r=await api(`/vehicles/${vehicle.id}/unified-catalogue`,"POST",{model_id:Number(model),source_modification_id:Number(mod),confirm_exact_modification:true});if(r.saved){const donor=await api(`/vehicles/${vehicle.id}`);onSaved(donor);setState(await api(`/vehicles/${vehicle.id}/unified-catalogue`))}else setError(r.source==="saved_plan_parts"?"Власне покриття неповне. Використовуйте збережений Plan.Parts нижче — без повторної оплати.":"Повний каталог цієї модифікації ще не підтверджено. Доступний стандартний план CarPot або Plan.Parts.")}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  const saved=state?.saved;
  return <>
    {(String(vehicle.manufacturer).trim().toLowerCase()==="volvo"||saved)&&<section className="card" aria-label="Власний каталог Volvo">
      <h3>Каталог CarPot · Volvo</h3>
      {error&&<p role="alert">{error}</p>}{state?.review_required&&<p role="alert">Автомобіль змінився. План збережено; перед складськими діями потрібна звірка модифікації.</p>}
      {saved?<p>Список збережено · {state.type_count} типів · {state.modification?.description || "Стандартний план CarPot"}. Фото деталей — за наявності підтвердженого джерела.</p>:<>
        <label>Модель у власному каталозі<select value={model} disabled={busy} onChange={e=>void loadModel(e.target.value)}><option value="">Виберіть модель явно</option>{/\bXC90\b/i.test(vehicle.model)&&<option value="13084">Volvo XC90 II</option>}{/\bXC60\b/i.test(vehicle.model)&&<option value="37773">Volvo XC60 II</option>}</select></label>
        {model&&<label>Конкретна модифікація<select value={mod} disabled={busy} onChange={e=>setMod(e.target.value)}><option value="">Виберіть модифікацію</option>{state?.items?.map((r:Row)=><option value={r.source_modification_id} key={r.source_modification_id}>{r.modification.description} · {r.modification.constructioninterval} · варіант {r.source_modification_id} · {r.coverage_verified?"повноту підтверджено":"часткове покриття"} · {r.taxonomy_status==="reviewed"?"категоризацію підтверджено":"категоризація на перевірці"}</option>)}</select></label>}
        {model&&!busy&&!state?.items?.length&&<p>Перевірених модифікацій зараз немає. Plan.Parts і стандартний план доступні нижче. Для XC40 власне покриття не підтверджено.</p>}
        <button disabled={busy||!mod} onClick={()=>void create()}>Підтвердити модифікацію та зберегти план</button>
        <p>Модифікація Catalogue не замінює K-Type. Текст назви та OEM-крос не підтверджують VIN-сумісність.</p>
      </>}
    </section>}
    {saved?<DismantlingBoard vehicle={vehicle} view={view} source={state.source==="base"?"base":"catalogue"} controls={null} revision={String(revision)} onOpenPart={id=>{void api("/parts/"+id).then(setDetail).catch(e=>setError(e.message))}}/>:<>
      <PlanPartsDonorAnalysis vehicle={vehicle} onSaved={onSaved} view={view}/>
      <section className="card"><h3>Стандартний план CarPot · без токенів</h3><p>Якщо точний каталог недоступний, сформуйте загальний перелік. Наявність кожної деталі потрібно перевірити на автомобілі.</p><button disabled={busy} onClick={async()=>{setBusy(true);try{await api(`/vehicles/${vehicle.id}/unified-catalogue/base`,"POST");setState(await api(`/vehicles/${vehicle.id}/unified-catalogue`))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Сформувати стандартний план</button>{error&&<p role="alert">{error}</p>}</section>
    </>}
    {detail&&<Modal className="r1-part-dialog" title={detail.name} onClose={()=>setDetail(null)}><PartDetail part={detail} onSaved={r=>{setDetail(r);setRevision(n=>n+1);window.dispatchEvent(new Event("warehouse:inventory-changed"))}} onChanged={()=>{void api("/parts/"+detail.id).then(setDetail);setRevision(n=>n+1);window.dispatchEvent(new Event("warehouse:inventory-changed"))}}/></Modal>}
  </>;
}
