import {useCallback,useContext,useEffect,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {Permit,TeamIdentity,useCan} from './permissions';
import VinCataloguePicker,{fieldLabels,type Clarifications,type VinChoice} from './VinCataloguePicker';
import VinDiagnostics from './VinDiagnostics';
import './vin-intake.css';

export type VinDecode={
  vin:string;source:string;vehicle:Row;message:string;resolution_context:string;
  field_sources?:Row;conflicts?:Row;consistency_issues?:Row;additional?:Row;
  provider_status?:Row;provider_contributions?:Record<string,string[]>;cached?:boolean;
};
const emptyClarifications:Clarifications={answers:{},reviewed:false};
const summaryFields=['body_class','engine','engine_code','engine_displacement_l','fuel_type','transmission','drive_type'];
const reviewable=new Set(Object.keys(fieldLabels).filter(field=>field!=='trim'));
const manualFields=['manufacturer','model','year','generation','engine','engine_code','engine_displacement_l','fuel_type','transmission','drive_type'];

export default function VehicleVinQuickAdd({mode,onBack,onCreated}:{
  mode:'vin'|'manual';onBack:()=>void;onCreated:(row:Row)=>void;
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
  const [error,setError]=useState('');
  const [existing,setExisting]=useState<Row|null>(null);
  const [loading,setLoading]=useState(false);
  const [saving,setSaving]=useState(false);
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
  const ready=(manual||result)&&(!vin||valid)&&!!String(characteristics.manufacturer||'').trim()
    &&!!String(characteristics.model||choice?.candidate.model||'').trim()&&!checkingChoice&&(manual||hasGraph||acceptBase);

  async function create(){
    if(!ready||writing.current)return;
    const year=String(characteristics.year||'').trim();
    if(year&&!/^\d{4}$/.test(year)){
      setError('Вкажіть модельний рік чотирма цифрами.');
      return;
    }
    const values:Row={
      manufacturer:characteristics.manufacturer,model:characteristics.model||choice?.candidate.model,
      year:year?Number(year):null,status:'planned',
    };
    if(valid)values.vin=vin;
    if(manual)values.vin_intake_mode='manual';
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
    setSaving(true);
    setError('');
    try{
      onCreated(await api('/vehicles','POST',values));
    }catch(e){
      setError((e as Error).message);
      const detail=e instanceof ApiError&&e.detail&&typeof e.detail==='object'?e.detail as Row:null;
      if(e instanceof ApiError&&e.status===409&&typeof detail?.vehicle_id==='string'){
        try{
          const found=await api<Row>('/vehicles/'+encodeURIComponent(detail.vehicle_id));
          if(found.vin?.trim().toUpperCase()===vin)setExisting(found);
        }catch{/* Keep the duplicate message if the donor is no longer visible. */}
      }
    }finally{
      writing.current=false;
      setSaving(false);
    }
  }

  return <section className="vin-intake" aria-label={manual?'Ручне додавання автомобіля':'Додавання автомобіля за VIN'}>
    <div className="vin-actions">
      <label>{manual?'VIN (необов’язково)':'VIN'}<input aria-label="VIN" autoCapitalize="characters"
        value={vin} maxLength={17} spellCheck={false} disabled={saving} onChange={e=>{
          setVin(e.target.value.trim().toUpperCase());
          if(!manual)clearResult();
          else {setError('');setExisting(null)}
        }}/></label>
      {!manual&&<button type="button" disabled={!valid||loading||saving} onClick={()=>void decode()}>
        {loading?'Визначаємо…':'Визначити автомобіль'}
      </button>}
    </div>
    {vin&&!valid&&<p role="status">Введіть 17 символів без I, O, Q.</p>}
    {manual&&<div className="vin-fields vin-manual-fields">
      {manualFields.map(field=><label key={field}>{fieldLabels[field]}
        {field==='drive_type'?<select disabled={saving} value={draft[field]||''} onChange={e=>{
          setDraft(before=>({...before,[field]:e.target.value}));
        }}><option value="">Невідомо</option><option>FWD</option><option>RWD</option><option>AWD</option><option>4WD</option></select>:
        <input disabled={saving} value={draft[field]||''} maxLength={field==='year'?4:100}
          onChange={e=>{setDraft(before=>({...before,[field]:e.target.value}))}}/>}
      </label>)}
      <p>План за базовим каталогом CarPot.</p>
    </div>}
    {result&&<>
      {!Object.keys(result.vehicle).length&&<p role="status">{result.message}</p>}
      <div className="vin-summary" role="region" aria-label="Зведення автомобіля">
        <strong>{[characteristics.manufacturer,characteristics.model,characteristics.year].filter(Boolean).join(' · ')
          ||'Характеристики потребують уточнення'}</strong>
        <dl>{summaryFields.filter(key=>characteristics[key]).map(key=><div key={key}>
          <dt>{fieldLabels[key]}</dt><dd>{String(characteristics[key])}</dd>
        </div>)}</dl>
      </div>
      <details>
        <summary>Виправити характеристики</summary>
        <form className="vin-fields" onSubmit={e=>{
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
            <input name={field} maxLength={100} defaultValue={characteristics[field]||''} disabled={saving}/>
          </label>)}
          <button type="submit" disabled={saving}>Застосувати зміни</button>
        </form>
      </details>
      {(!characteristics.manufacturer||!characteristics.model)&&<p role="status">Укажіть марку й модель у розділі «Виправити характеристики».</p>}
      {characteristics.manufacturer&&can('catalog.view')&&<VinCataloguePicker
        key={JSON.stringify([result.resolution_context,clarifications.reviewed,clarifications.model_correction,
          clarifications.answers.manufacturer,clarifications.answers.model,clarifications.answers.vehicle_type])}
        context={result.resolution_context} clarifications={clarifications} disabled={saving}
        onAnswer={(field,value)=>setAnswer(field,value==='unknown'?null:value)} onSelect={select} onPending={setCheckingChoice}/>}
      {!hasGraph&&<label className="vin-confirm"><input type="checkbox" checked={acceptBase}
        disabled={saving||checkingChoice} onChange={e=>{setAcceptBase(e.target.checked)}}/>
        Додати з базовим каталогом без підтвердженого переліку запчастин</label>}
      <details className="vin-details">
        <summary>Усі характеристики</summary>
        <dl>{Object.entries(result.vehicle).filter(([,value])=>value!=null&&String(value).trim()).map(([key,value])=><div key={key}>
          <dt>{fieldLabels[key]||key}</dt><dd>{String(value)}</dd>
        </div>)}
        {Object.entries(result.additional||{}).map(([key,item])=><div key={key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
      </details>
      {identity?.catalogue_platform_admin===true&&result.provider_status&&<VinDiagnostics key={vin} vin={vin} result={result}/>}
    </>}
    {error&&<p role="alert">{error}</p>}
    {existing&&<button type="button" className="primary" onClick={()=>onCreated(existing)}>Відкрити наявний автомобіль</button>}
    <div className="vin-footer">
      <div className="vin-actions">
        <Permit permission="vehicles.create"><button className="primary" type="button" disabled={saving||!ready}
          onClick={()=>void create()}>{saving?'Зберігаємо…':'Додати автомобіль'}</button></Permit>
        <button type="button" disabled={saving} onClick={onBack}>Скасувати</button>
      </div>
    </div>
  </section>;
}
