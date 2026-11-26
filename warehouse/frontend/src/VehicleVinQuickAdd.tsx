import {useCallback,useContext,useEffect,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {Permit,TeamIdentity,useCan} from './permissions';
import VinCataloguePicker,{fieldLabels,type Clarifications,type VinChoice} from './VinCataloguePicker';
import VinDiagnostics from './VinDiagnostics';
import OracleVehiclePicker,{type OracleVehicle} from './OracleVehiclePicker';
import {DonorSummary, IntakeDisclosure, IntakeFeedback, ModelYearOptions, PlanReady, displacement, measurement, modificationName} from './DonorIntakePresentation';
import './vin-intake.css';

export type VinDecode={
  vin:string;source:string;vehicle:Row;message:string;resolution_context:string;
  field_sources?:Row;conflicts?:Row;consistency_issues?:Row;additional?:Row;
  provider_status?:Row;provider_contributions?:Record<string,string[]>;cached?:boolean;
};
const emptyClarifications:Clarifications={answers:{},reviewed:false};
const reviewable=new Set(Object.keys(fieldLabels).filter(field=>field!=='trim'));
const manualFields=['manufacturer','model','year','generation','engine','engine_code','engine_displacement_l','fuel_type','transmission','drive_type'];

export default function VehicleVinQuickAdd({mode,onBack,onCreated,onOpenExisting,saving,onSavingChange}:{
  mode:'vin'|'manual';onBack:()=>void;onCreated:(row:Row)=>void;onOpenExisting:(row:Row)=>void;
  saving:boolean;onSavingChange:(saving:boolean)=>void;
}){
  const identity=useContext(TeamIdentity);
  const can=useCan();
  const [vin,setVin]=useState('');
  const [result,setResult]=useState<VinDecode|null>(null);
  const [draft,setDraft]=useState<Row>({});
  const [clarifications,setClarifications]=useState<Clarifications>(emptyClarifications);
  const [choice,setChoice]=useState<VinChoice|null>(null);
  const [checkingChoice,setCheckingChoice]=useState(false);
  const [acceptBase,setAcceptBase]=useState(false);
  const [manualSearch,setManualSearch]=useState<string|null>(null);
  const [manualSelection,setManualSelection]=useState<OracleVehicle|null>(null);
  const requestKey=useRef<string|null>(null);
  const [error,setError]=useState('');
  const [existing,setExisting]=useState<Row|null>(null);
  const [loading,setLoading]=useState(false);
  const decodeRequest=useRef<AbortController|null>(null);
  const writing=useRef(false);
  const valid=/^[A-HJ-NPR-Z0-9]{17}$/.test(vin);
  const manual=mode==='manual';
  const reviewFields=[...new Set([...Object.keys(result?.conflicts||{}),...Object.keys(result?.consistency_issues||{})])].filter(field=>reviewable.has(field));

  useEffect(()=>()=>decodeRequest.current?.abort(),[]);

  const select=useCallback((value:VinChoice|null)=>{
    setChoice(value);
    setAcceptBase(false);
    setCheckingChoice(false);
  },[]);

  function setAnswer(field:string,value:string|null){
    select(null);
    setClarifications(before=>({...before,answers:{...before.answers,[field]:value}}));
  }
  function clearResult(){
    decodeRequest.current?.abort();
    setLoading(false);
    setResult(null);
    setDraft({});
    setClarifications(emptyClarifications);
    setError('');
    setExisting(null);
    select(null);
  }
  async function decode(){
    if(!valid||loading)return;
    clearResult();
    const controller=new AbortController();
    decodeRequest.current=controller;
    setLoading(true);
    try{
      const decoded=await api<VinDecode>('/vehicles/vin/decode?vin='+encodeURIComponent(vin),
        'GET',undefined,undefined,{signal:controller.signal});
      if(!controller.signal.aborted)setResult(decoded);
    }catch(e){
      if(!controller.signal.aborted)setError((e as Error).message);
    }finally{
      if(!controller.signal.aborted)setLoading(false);
    }
  }

  const characteristics=manual?draft:{
    ...result?.vehicle,
    ...Object.fromEntries(reviewFields.filter(key=>!(key in clarifications.answers)).map(key=>[key,null])),
    ...clarifications.answers,
    ...(clarifications.model_correction?{model:clarifications.model_correction}:{}),
  };
  const hasGraph=choice?.graph.status==='exact'||choice?.graph.status==='partial';
  const ready=(manual||result)&&(!vin||valid)&&!!String(manualSelection?.manufacturer||characteristics.manufacturer||'').trim()
    &&!!String(manualSelection?.model||characteristics.model||choice?.candidate.model||'').trim()&&!checkingChoice&&
    (manual?!!manualSelection||acceptBase:hasGraph||acceptBase);

  async function create(){
    if(!ready||writing.current)return;
    const year=String(characteristics.year||'').trim();
    if(year&&!/^\d{4}$/.test(year)){
      setError('Вкажіть модельний рік чотирма цифрами.');
      return;
    }
    requestKey.current ||= crypto.randomUUID();
    const values:Row={
      intake_request_key:requestKey.current,
      manufacturer:manualSelection?.manufacturer||characteristics.manufacturer,
      model:manualSelection?.model||characteristics.model||choice?.candidate.model,
      year:year?Number(year):null,status:'planned',
    };
    if(valid)values.vin=vin;
    if(manual){
      values.vin_intake_mode='manual';
      if(!manualSelection)values.accept_base_catalogue=acceptBase;
      if(manualSelection){
        values.source_identity=manualSelection.identity;
        values.catalogue_graph_sha=manualSelection.graph.source_snapshot_sha;
      }
    }
    for(const field of ['generation','engine','engine_code','fuel_type','transmission','drive_type']){
      if(characteristics[field])values[field]=characteristics[field];
    }
    if(characteristics.engine_displacement_l){
      const raw=String(characteristics.engine_displacement_l).normalize('NFKC').replace(',','.');
      const amount=Number(raw.match(/^\s*(\d+(?:\.\d+)?)/)?.[1]);
      const liters=amount>=100||/(?:cc|cm3|см3)/i.test(raw)?amount/1000:amount;
      if(Number.isFinite(liters)&&liters>=0.05&&liters<=99.9)values.engine_displacement_l=Math.round(liters*10)/10;
    }
    if(!manual&&result?.resolution_context){
      values.vin_resolution={context:result.resolution_context,clarifications,accept_base_catalogue:acceptBase,
        ...(choice?{choice:choice.candidate.choice,graph_sha:choice.graph.source_snapshot_sha}:{})};
    }
    writing.current=true;
    onSavingChange(true);
    setError('');
    setExisting(null);
    try{
      onCreated(await api('/vehicles','POST',values));
    }catch(e){
      setError((e as Error).message);
      const detail=e instanceof ApiError&&e.detail&&typeof e.detail==='object'?e.detail as Row:null;
      if(e instanceof ApiError&&e.status===409&&typeof detail?.vehicle_id==='string'){
        try{
          const found=await api<Row>('/vehicles/'+encodeURIComponent(detail.vehicle_id));
          if(found.id===detail.vehicle_id&&found.vin?.trim().toUpperCase()===vin)setExisting(found);
        }catch{/* Keep the duplicate message if the donor is no longer visible. */}
      }
    }finally{
      writing.current=false;
      onSavingChange(false);
    }
  }

  return <section className="vin-intake" aria-label={manual?'Ручне додавання автомобіля':'Додавання автомобіля за VIN'}>
    <div className="vin-content">
    <div className={!manual?'vin-actions vin-decode-row':'vin-actions'}>
      <label>{manual?'VIN (необов’язково)':'VIN'}<input aria-label="VIN" autoCapitalize="characters"
        placeholder={manual?undefined:'17 символів VIN'}
        value={vin} maxLength={17} spellCheck={false} disabled={saving} onChange={e=>{
          const value=e.target.value.trim().toUpperCase();
          setVin(value);
          requestKey.current=null;
          if(!manual)clearResult();
          else {setError('');setExisting(null)}
        }}/></label>
      {!manual&&<button className="vin-decode-button" type="button" disabled={!valid||loading||saving} onClick={()=>void decode()}>
        {loading?'Визначаємо…':'Визначити автомобіль'}
      </button>}
    </div>
    {vin&&!valid&&<IntakeFeedback>Введіть 17 символів без I, O, Q.</IntakeFeedback>}
    {loading&&<IntakeFeedback kind="loading">Декодуємо VIN та завантажуємо характеристики</IntakeFeedback>}
    {manual&&<div className="vin-fields vin-manual-fields">
      {manualFields.slice(0,3).map(field=><label key={field}>{fieldLabels[field]}
        {field==='drive_type'?<select disabled={saving} value={draft[field]||''} onChange={e=>{
          setDraft(before=>({...before,[field]:e.target.value}));
        }}><option value="">Невідомо</option><option>FWD</option><option>RWD</option><option>AWD</option><option>4WD</option></select>:
        <input disabled={saving} value={draft[field]||''} maxLength={field==='year'?4:100}
          onChange={e=>{setDraft(before=>({...before,[field]:e.target.value}))}}/>}
      </label>)}
    </div>}
    {manual&&<>
      {can('catalog.view')&&can('dismantling.manage')&&<button type="button" disabled={saving||!draft.manufacturer}
        onClick={()=>{setManualSelection(null);setManualSearch(String(draft.manufacturer));}}>
        Знайти модифікацію в каталозі
      </button>}
      {manualSearch!==null&&<OracleVehiclePicker key={manualSearch} year={String(draft.year||'')}
        initialManufacturer={manualSearch} disabled={saving} onChange={setManualSelection}/>}
      <details className="vin-details"><summary>Додаткові характеристики</summary>
        <div className="vin-fields">{manualFields.slice(3).map(field=><label key={field}>{fieldLabels[field]}
          {field==='drive_type'?<select disabled={saving} value={draft[field]||''}
            onChange={e=>setDraft(before=>({...before,[field]:e.target.value}))}>
            <option value="">Невідомо</option><option>FWD</option><option>RWD</option><option>AWD</option><option>4WD</option>
          </select>:<input disabled={saving} value={draft[field]||''} maxLength={100}
            onChange={e=>setDraft(before=>({...before,[field]:e.target.value}))}/>}
        </label>)}</div>
      </details>
      {!manualSelection&&<label className="vin-confirm"><input type="checkbox" checked={acceptBase}
        disabled={saving} onChange={e=>setAcceptBase(e.target.checked)}/>Додати з базовим каталогом CarPot</label>}
    </>}
    {result&&<>
      {!Object.keys(result.vehicle).length&&<IntakeFeedback>{result.message}</IntakeFeedback>}
      <DonorSummary title={[characteristics.manufacturer,characteristics.model,characteristics.year].filter(Boolean).join(' · ')
        ||'Характеристики потребують уточнення'} facts={[
          ['Паливо', characteristics.fuel_type],
          ['Привід', characteristics.drive_type],
          ['Модифікація', choice && modificationName(choice.candidate.modification, choice.candidate.model)],
          ['Об’єм', displacement(characteristics.engine_displacement_l)],
          ['Потужність', measurement(characteristics.engine_power_kw,'кВт') || measurement(characteristics.engine_power_hp,'к.с.')],
          ['Тип', characteristics.vehicle_type || (choice ? choice.candidate.kind==='commercial'?'Комерційний':'Легковий' : null)],
        ]}/>
      <IntakeDisclosure label="Виправити характеристики" variant="link">
        <form className="vin-fields vin-corrections" onSubmit={e=>{
          e.preventDefault();
          const form=new FormData(e.currentTarget);
          const answers={...clarifications.answers};
          for(const field of manualFields){
            const value=String(form.get(field)||'').trim()||null;
            if((value||'')!==String(characteristics[field]||'').trim()){
              answers[field]=value;
            }
          }
          select(null);
          setClarifications(before=>({...before,answers}));
        }}>
          {manualFields.map(field=><label key={field}>{fieldLabels[field]}
            {field==='year'?<select name={field} defaultValue={characteristics[field]||''} disabled={saving}>
              <ModelYearOptions current={String(characteristics[field]||'')}/>
            </select>:<input name={field} maxLength={100} defaultValue={characteristics[field]||''} disabled={saving}/>}
          </label>)}
          <button type="submit" disabled={saving}>Застосувати зміни</button>
        </form>
      </IntakeDisclosure>
      {(!characteristics.manufacturer||!characteristics.model)&&<IntakeFeedback>Укажіть марку й модель у розділі «Виправити характеристики».</IntakeFeedback>}
      {characteristics.manufacturer&&can('catalog.view')&&<VinCataloguePicker
        key={JSON.stringify([result.resolution_context,clarifications.reviewed,clarifications.model_correction,
          clarifications.answers.manufacturer,clarifications.answers.model,clarifications.answers.vehicle_type])}
        context={result.resolution_context} clarifications={clarifications} disabled={saving}
        onAnswer={(field,value)=>setAnswer(field,value==='unknown'?null:value)} onSelect={select} onPending={setCheckingChoice}/>}
      {hasGraph&&<PlanReady counts={choice?.graph.counts}/>}
      {!hasGraph&&<label className="vin-confirm"><input type="checkbox" checked={acceptBase}
        disabled={saving||checkingChoice} onChange={e=>{setAcceptBase(e.target.checked)}}/>
        Додати з базовим каталогом без підтвердженого переліку запчастин</label>}
      <IntakeDisclosure label="Усі характеристики">
        <dl>{Object.entries(result.vehicle).filter(([,value])=>value!=null&&String(value).trim()).map(([key,value])=><div key={key}>
          <dt>{fieldLabels[key]||key}</dt><dd>{String(value)}</dd>
        </div>)}
        {Object.entries(result.additional||{}).map(([key,item])=><div key={key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
      </IntakeDisclosure>
      {identity?.catalogue_platform_admin===true&&result.provider_status&&<VinDiagnostics key={vin} vin={vin} result={result}/>}
    </>}
    {error&&<IntakeFeedback kind="error">
      <p>{error}</p>
      {existing&&<button type="button" disabled={saving} onClick={()=>onOpenExisting(existing)}>Відкрити наявний автомобіль</button>}
    </IntakeFeedback>}
    </div>
    <div className="vin-footer">
      <div className="vin-actions">
        <button type="button" disabled={saving} onClick={onBack}>Скасувати</button>
        <Permit permission="vehicles.create"><button className="vin-submit" type="button" disabled={saving||!ready}
          onClick={()=>void create()}>{saving?'Зберігаємо…':'Додати автомобіль'}</button></Permit>
      </div>
    </div>
  </section>;
}
