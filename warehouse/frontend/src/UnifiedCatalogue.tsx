import GlobalCatalogueFlow from './GlobalCatalogueFlow';
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, type Row } from "./api";
import { Modal } from "./components";
import { PartDetail } from "./pages/Inventory";
import DismantlingBoard from "./DismantlingBoard";
import PlanPartsDonorAnalysis, { type DismantlingFlow } from "./PlanPartsDonorAnalysis";
import { TeamIdentity, useCan } from "./permissions";
import { flowStep, modificationTitle, nextChoice, supportedModel, userMessage, vehicleFacts, verifiedOption, type PlanChoice } from "./dismantlingFlow";
import "./unified-dismantling.css";

/** One coordinator; existing provider handlers and board remain the sole write paths. */
export function LegacyUnifiedCatalogue({ vehicle, onSaved, onModify, view = "operations" }: {
  vehicle: Row; onSaved: (r: Row) => void; onModify?: () => void; view?: "operations" | "settings";
}) {
  const can = useCan(), who = useContext(TeamIdentity);
  const scope = JSON.stringify([who?.id, who?.workspace_account_id, vehicle.id]);
  const basis=JSON.stringify([vehicle.ktype,vehicle.manufacturer,vehicle.model,vehicle.year,vehicle.engine,vehicle.fuel_type,vehicle.transmission]);
  const generation = useRef(0), directoryEpoch=useRef(0), writing = useRef(false);
  const [directoryLoading,setDirectoryLoading]=useState(false);
  const [own, setOwn] = useState<Row | null>(null), [loading, setLoading] = useState(true);
  const [model, setModel] = useState(supportedModel(vehicle)), [picked, setPicked] = useState("");
  const [prepared, setPrepared] = useState(!!vehicle.ktype), [choice, setChoice] = useState<PlanChoice>("base");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [inProgress,setInProgress]=useState(false);
  const onBoardProgress=useCallback((active:boolean)=>setInProgress(active),[]);
  const [detail, setDetail] = useState<Row | null>(null), [revision, setRevision] = useState(0);
  const editable = can("dismantling.manage") && !vehicle.archived;
  const mayModify = editable && can("vehicles.edit");
  const mayUseProfessional=can("vehicles.create");
  const mayRequest = editable && can("vehicles.create") && who?.role === "DIRECTOR";

  const loadDirectory = useCallback(async (id: string, ticket = generation.current) => {
    if (!id) return;
    const request=++directoryEpoch.current;
    setDirectoryLoading(true);
    try {
      const result = await api(`/vehicles/${vehicle.id}/unified-catalogue?model_id=${id}`);
      if (ticket === generation.current && request===directoryEpoch.current) setOwn(result);
    } catch {
      if (ticket === generation.current && request===directoryEpoch.current) setOwn({saved:false,available:false,items:[]});
    } finally {if(ticket===generation.current && request===directoryEpoch.current)setDirectoryLoading(false);}
  }, [vehicle.id]);
  useEffect(() => {
    const ticket = ++generation.current;
    directoryEpoch.current++; writing.current=false;
    setDirectoryLoading(false); setBusy(false);
    setLoading(true); setOwn(null); setPicked(""); setPrepared(!!vehicle.ktype);
    setChoice("base"); setError(""); setDetail(null); setInProgress(false);
    const initialModel = supportedModel(vehicle); setModel(initialModel);
    api(`/vehicles/${vehicle.id}/unified-catalogue`).then(async result => {
      if (ticket !== generation.current) return;
      setOwn(result);
      if(!result.saved&&vehicle.ktype){
        const stored=await api(`/vehicles/${vehicle.id}/plan-parts-checklist?limit=1`);
        if(ticket!==generation.current)return;
        if(stored.total>0){
          if(!mayUseProfessional)setOwn({saved:true,source:"professional",type_count:stored.total,modification:{description:vehicle.engine||"Збережена комплектація"}});
          return; // A saved working plan opens without any remote source lookup.
        }
      }
      if (!result.saved && initialModel) await loadDirectory(initialModel, ticket);
    }).catch(() => {
      if (ticket === generation.current) {
        setOwn({saved:false,available:false,items:[]});
        setError("Не вдалося перевірити збережений список. Доступні дані додаткового каталогу можна відкрити нижче.");
      }
    }).finally(() => {if (ticket === generation.current) setLoading(false);});
    return () => {generation.current++;};
  }, [scope, basis, loadDirectory,mayUseProfessional]);

  async function savePlan() {
    if (writing.current || !editable) return;
    writing.current = true; setBusy(true); setError(""); const ticket = generation.current;
    try {
      const result = choice === "catalogue"
        ? await api(`/vehicles/${vehicle.id}/unified-catalogue`, "POST", {
          model_id:Number(model),source_modification_id:Number(picked.split(":")[1]),confirm_exact_modification:true,
        })
        : await api(`/vehicles/${vehicle.id}/unified-catalogue/base`, "POST");
      if (ticket !== generation.current) return;
      if (!result.saved) {
        setError("Цей перелік ще потребує перевірки. Відкрийте збережений список або виберіть стандартний план."); return;
      }
      const status=await api(`/vehicles/${vehicle.id}/unified-catalogue`);
      const donor=await api(`/vehicles/${vehicle.id}`);
      if(ticket!==generation.current)return;
      setOwn(status); onSaved(donor);
    } catch (e) {if (ticket === generation.current) setError(userMessage((e as Error).message));}
    finally {if (ticket === generation.current) {writing.current=false;setBusy(false);}}
  }
  function render(flow?: DismantlingFlow) {
    const saved = !!own?.saved || !!flow?.saved;
    const step = flowStep(saved, prepared), locked = busy || directoryLoading || !!flow?.busy || !!flow?.confirmation;
    const ownPicked = picked.startsWith("catalogue:") ? own?.items?.find((r:Row) => String(r.source_modification_id) === picked.split(":")[1]) : undefined;
    const partial = !saved && !!ownPicked && ownPicked.coverage_verified !== true;
    const taxonomyPending = !saved && !!ownPicked && ownPicked.coverage_verified === true && ownPicked.taxonomy_status !== "reviewed";
    const modification = own?.saved ? own.modification?.description || "Стандартний перелік" :
      ownPicked ? modificationTitle(ownPicked, own?.items?.indexOf(ownPicked) || 0) : vehicle.ktype ? flow?.modification.label || vehicle.engine || "Комплектацію збережено" : "Без уточнення комплектації";
    return <section className="uf-flow" aria-label="Розбір автомобіля">
      <header className="uf-heading"><div><h2>Розбір автомобіля</h2><p>{vehicleFacts(vehicle)}</p></div>
        <span className="uf-status">{loading || flow?.loading ? "Підготовка" : saved ? inProgress ? "У процесі розбору" : "План сформовано" : prepared ? "Підготовка" : "Не розпочато"}</span>
      </header>
      {!saved && <ol className="uf-steps" aria-label="Етапи розбору">{["Комплектація","План запчастин","Робота з деталями"].map((label,i)=><li key={label} aria-current={step===i+1?"step":undefined}><span>{i+1}</span>{label}</li>)}</ol>}
      {(error || flow?.error) && <p className="uf-feedback" role="alert">{userMessage(error || flow?.error || "")}</p>}
      {flow?.notice && !saved && <p role="status" className="uf-feedback">{userMessage(flow.notice)}</p>}
      {loading || flow?.loading ? <p role="status">Перевіряємо збережені дані…</p> : <>
        {own?.review_required && <p role="alert" className="uf-feedback">Характеристики автомобіля змінилися. План збережено; перед складськими діями потрібно звірити комплектацію.{mayModify&&onModify&&<button className="secondary" onClick={onModify}>Перевірити автомобіль</button>}</p>}
        {saved ? <>
          <div className="uf-summary"><div><strong>{modification}</strong><span>Список збережено · повторне відкриття без оплати</span></div>
            <div className="uf-summary-actions">{flow?.saved&&mayRequest&&<button className="secondary" disabled={locked} onClick={()=>void flow.start()}>Оновити список</button>}{mayModify&&onModify&&!own?.review_required&&<button className="secondary" onClick={onModify}>Змінити комплектацію</button>}</div>
          </div>
          {flow?.confirmation&&<div className="uf-confirm">{flow.confirmation}</div>}
          {!can("inventory.view")?<p>Для перегляду деталей потрібне право перегляду складу. Зверніться до керівника.</p>:own?.saved ? <DismantlingBoard vehicle={vehicle} source={own.source==="base"?"base":own.source==="professional"?"professional":"catalogue"} blockedReason={own.review_required?"Спочатку звірте комплектацію автомобіля":""} integrated onProgress={onBoardProgress} view={view} controls={null} revision={String(revision)} onOpenPart={id=>{void api("/parts/"+id).then(setDetail).catch(e=>setError(e.message));}}/> : flow?.board}
        </> : <div className="uf-stage">
          {!editable && <p>Ви можете переглядати збережений план. Для підготовки розбору зверніться до керівника.</p>}
          {step===1 ? <>
            <div className="uf-stage-title"><div><h3>Оберіть комплектацію автомобіля</h3><p>Уточніть двигун і модифікацію для точнішого переліку запчастин.</p></div>{mayModify&&onModify&&<button className="text-button" disabled={locked} onClick={onModify}>Уточнити дані авто</button>}</div>
            <div className="uf-fields">
              {String(vehicle.manufacturer).trim().toLowerCase()==="volvo" && !supportedModel(vehicle) && /XC90|XC60/i.test(vehicle.model) && <label>Покоління<select disabled={locked||!mayModify} value={model} onChange={e=>{setModel(e.target.value);setPicked("");setOwn(old=>({...old,saved:false,items:[]}));void loadDirectory(e.target.value);}}><option value="">Оберіть покоління</option>{/XC90/i.test(vehicle.model)&&<option value="13084">XC90 II</option>}{/XC60/i.test(vehicle.model)&&<option value="37773">XC60 II</option>}</select></label>}
              <label>Модифікація<select aria-label="Модифікація" disabled={locked||!mayModify} value={picked} onChange={e=>setPicked(e.target.value)}>
                <option value="">Оберіть комплектацію</option>
                {own?.items?.map((r:Row,i:number)=><option key={"c"+r.source_modification_id} value={"catalogue:"+r.source_modification_id}>{modificationTitle(r,i)}</option>)}
                {flow?.matches.map((r:Row,i:number)=><option key={"p"+r.ktype} value={"professional:"+r.ktype}>{modificationTitle(r,i)}</option>)}
              </select></label>
              {mayRequest&&flow&&<button className="secondary" disabled={locked} onClick={flow.find}>Знайти інші комплектації</button>}
            </div>
            {directoryLoading&&<p role="status">Перевіряємо доступні комплектації…</p>}
            {flow?.confirmation ? <div className="uf-confirm">{flow.confirmation}</div> : <div className="uf-footer">
              <button className="primary" disabled={locked||!editable||!picked} onClick={async()=>{if(picked.startsWith("professional:")){await flow?.choose(Number(picked.split(":")[1]));return;}setChoice(nextChoice(ownPicked));setPrepared(true);}}>Продовжити</button>
              <button className="text-button" disabled={locked||!editable} onClick={()=>{setChoice("base");setPrepared(true);}}>Продовжити без уточнення</button>
            </div>}
          </> : <>
            <div className="uf-stage-title"><div><h3>Підготуйте план запчастин</h3><p>{modification}</p></div><button className="text-button" disabled={locked||!mayModify} onClick={()=>setPrepared(false)}>Змінити</button></div>
            {taxonomyPending ? <p className="uf-explanation">Перелік для комплектації знайдено, але українські категорії ще потребують перевірки. Поки виберіть додаткові дані або стандартний план.</p> : partial ? <p className="uf-explanation">Частину запчастин знайдено у каталозі CarPot. Для детальнішого переліку можна використати додатковий каталог. Неперевірений перелік поки не додається до плану.</p> : !verifiedOption(ownPicked)&&<p className="uf-explanation">Точного перевіреного переліку зараз немає. Можна отримати додаткові дані або використати безкоштовний стандартний план.</p>}
            {!vehicle.ktype&&mayRequest&&flow&&<button className="text-button" disabled={locked} onClick={()=>{setPrepared(false);flow.find();}}>Знайти комплектацію для детальнішого переліку</button>}
            <label>Перелік запчастин<select aria-label="Варіант плану" disabled={locked||!editable} value={choice} onChange={e=>setChoice(e.target.value as PlanChoice)}>
              {verifiedOption(ownPicked)&&<option value="catalogue">Перевірений перелік для обраної комплектації · безкоштовно</option>}
              {!!vehicle.ktype&&mayRequest&&<option value="professional">Детальніший перелік · за підтвердженою вартістю</option>}
              <option value="base">Стандартний план CarPot · безкоштовно</option>
            </select></label>
            <p className="uf-explanation">{choice==="base"?"Загальний перелік: наявність кожної деталі потрібно перевірити на автомобілі.":choice==="professional"?"Спочатку перевіримо раніше збережені дані. Новий запит можливий тільки після підтвердження вартості.":"Зберігаємо перевірений перелік. Фізичні залишки автоматично не створюються."}</p>
            {flow?.confirmation ? <div className="uf-confirm">{flow.confirmation}</div> : <div className="uf-footer"><button className="primary" disabled={locked||!editable} onClick={()=>choice==="professional"?void flow?.start():void savePlan()}>Сформувати план розбору</button></div>}
          </>}
        </div>}
        {!!flow?.workspace?.saved_plan_ktypes?.filter((id:number)=>id!==Number(vehicle.ktype)).length&&mayModify&&<details className="uf-history"><summary>Відкрити раніше збережений список</summary><label>Збережений список<select aria-label="Збережений список" disabled={locked} value="" onChange={e=>{if(e.target.value)void flow.choose(Number(e.target.value));}}><option value="">Оберіть список</option>{flow.workspace.saved_plan_ktypes.filter((id:number)=>id!==Number(vehicle.ktype)).map((id:number,i:number)=><option key={id} value={id}>{flow.workspace?.saved_modifications?.find((r:Row)=>r.ktype===id)?.modification||`Збережений список ${i+1}`}</option>)}</select></label></details>}
        <details className="uf-diagnostics"><summary>Технічні деталі</summary><dl><dt>Джерело</dt><dd>{own?.saved?own.source:flow?.saved?"Збережений Plan.Parts":"Не вибрано"}</dd><dt>K-Type</dt><dd>{vehicle.ktype||"—"}</dd><dt>Модифікація джерела</dt><dd>{own?.source_modification_id||ownPicked?.source_modification_id||"—"}</dd></dl></details>
      </>}
    </section>;
  }
  return <>
    {own?.saved || loading || !mayUseProfessional ? render() : <PlanPartsDonorAnalysis vehicle={vehicle} onSaved={row=>{setPrepared(!!row.ktype);onSaved(row);}} view={view} onBoardProgress={onBoardProgress} renderFlow={render}/>}
    {detail&&<Modal className="r1-part-dialog" title={detail.name} onClose={()=>setDetail(null)}><PartDetail part={detail} onSaved={r=>{setDetail(r);setRevision(n=>n+1);window.dispatchEvent(new Event("warehouse:inventory-changed"));}} onChanged={()=>{void api("/parts/"+detail.id).then(setDetail);setRevision(n=>n+1);window.dispatchEvent(new Event("warehouse:inventory-changed"));}}/></Modal>}
  </>;
}


export default function UnifiedCatalogue(props: Parameters<typeof LegacyUnifiedCatalogue>[0]) {
 return <GlobalCatalogueFlow vehicle={props.vehicle} onSaved={props.onSaved}/>;
}
