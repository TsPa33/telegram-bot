import {useEffect,useState} from 'react';
import {api} from './api';

export type Clarifications={answers:Record<string,string|null>;reviewed:boolean;model_correction?:string};
type Candidate={
  kind:'passenger'|'commercial'; manufacturer_id:number; model_id:number;
  source_modification_id:number; model:string; modification:string;
  construction_interval?:string; choice:string; matches:Record<string,string>;
};
type SourceModel=Pick<Candidate,'kind'|'manufacturer_id'|'model_id'|'model'|'construction_interval'>;
type ResolutionPage={
  items:Candidate[]; models:SourceModel[]; next_after:number|null; search_complete:boolean;
  model_cursors?:{maker:string;after:number;kind:string}[];
  questions:{field:string;options:string[]}[]; review:string[]; status:string; automatic:string|null;
};
type Readiness={status:string;source_snapshot_sha:string|null};
export type VinChoice={candidate:Candidate;graph:Readiness};
export const fieldLabels:Record<string,string>={
  manufacturer:'Марка',model:'Модель',year:'Модельний рік',generation:'Покоління',
  vehicle_type:'Тип транспорту',body_class:'Кузов',fuel_type:'Паливо',engine:'Двигун',
  engine_code:'Код двигуна',engine_displacement_l:'Об’єм двигуна, л',
  engine_power_kw:'Потужність, кВт',engine_power_hp:'Потужність, к.с.',
  transmission:'КПП',drive_type:'Привід',transmission_speeds:'Кількість передач',
  doors:'Кількість дверей',engine_cylinders:'Кількість циліндрів',trim:'Комплектація',
};
const readinessLabels:Record<string,string>={
  exact:'Підтверджено граф запчастин. OEM підбирається автоматично з цього джерела.',
  partial:'Доступний частковий план. OEM підбирається для позицій із підтвердженими зв’язками.',
  absent:'Граф запчастин для цієї модифікації ще відсутній. Доступний базовий каталог CarPot.',
  unavailable:'Каталог запчастин тимчасово недоступний. Повторіть перевірку або додайте авто з базовим каталогом.',
  unsupported:'Для цього типу транспорту доступний довідник модифікацій і базовий каталог CarPot.',
  unverified:'Підтверджених зв’язків із запчастинами поки немає. Доступний базовий каталог CarPot.',
  identity_mismatch:'Джерела повернули різні ідентифікатори. Доступний базовий каталог CarPot.',
  attributes_pending:'Дані модифікації завантажилися частково. Доступний базовий каталог CarPot.',
  identity_only:'Модифікацію можна зберегти. Підготовка плану потребує відповідного доступу.',
};
const modelKey=(row:SourceModel)=>[row.kind,row.manufacturer_id,row.model_id].join(':');

export default function VinCataloguePicker({
  context,clarifications,disabled,onAnswer,onReview,onSelect,onPending,
}:{
  context:string;clarifications:Clarifications;disabled:boolean;
  onAnswer:(field:string,value:string|null)=>void;
  onReview:()=>void;
  onSelect:(value:VinChoice|null)=>void;
  onPending:(value:boolean)=>void;
}){
  const [models,setModels]=useState<SourceModel[]>([]);
  const [scope,setScope]=useState<SourceModel|null>(null);
  const [cursor,setCursor]=useState(0);
  const [modelPage,setModelPage]=useState<{maker:string;after:number}|null>(null);
  const [retry,setRetry]=useState(0);
  const [page,setPage]=useState<ResolutionPage|null>(null);
  const [busy,setBusy]=useState(true);
  const [error,setError]=useState('');
  const [choice,setChoice]=useState<Candidate|null>(null);
  const [graph,setGraph]=useState<Readiness|null>(null);
  const [graphError,setGraphError]=useState('');
  const [graphRetry,setGraphRetry]=useState(0);
  const clarificationHeader=encodeURIComponent(JSON.stringify(clarifications));

  useEffect(()=>{
    const controller=new AbortController();
    setBusy(true);
    setPage(null);
    setError('');
    const query=new URLSearchParams();
    if(scope){
      query.set('maker',scope.kind+':'+scope.manufacturer_id);
      query.set('model_id',String(scope.model_id));
      query.set('after',String(cursor));
    }else if(modelPage){
      query.set('maker',modelPage.maker);
      query.set('model_after',String(modelPage.after));
    }
    const options={signal:controller.signal,headers:{'X-Vin-Context':context,'X-Vin-Clarifications':clarificationHeader}};
    api<ResolutionPage>('/vehicles/vin/resolution?'+query, 'GET', undefined, undefined, options)
      .then(result=>{
        if(controller.signal.aborted)return;
        setPage(result);
        if(!scope)setModels(previous=>modelPage
          ?[...new Map([...previous,...result.models].map(row=>[modelKey(row),row])).values()]
          :result.models);
        const automatic=result.items.find(item=>item.choice===result.automatic);
        if(automatic){onPending(true);setChoice(automatic)}
      })
      .catch(e=>{if(!controller.signal.aborted)setError((e as Error).message)})
      .finally(()=>{if(!controller.signal.aborted)setBusy(false)});
    return ()=>controller.abort();
  },[context,clarificationHeader,scope,cursor,modelPage,retry,onPending]);

  useEffect(()=>{
    if(!choice||choice.matches.model==='unknown'&&!clarifications.reviewed)return;
    const controller=new AbortController();
    setGraph(null);
    setGraphError('');
    const options={signal:controller.signal,headers:{'X-Vin-Context':context,
      'X-Vin-Clarifications':clarificationHeader,'X-Vin-Choice':choice.choice}};
    api<Readiness>('/vehicles/vin/resolution-graph','GET',undefined,undefined,options)
      .then(result=>{
        if(controller.signal.aborted)return;
        setGraph(result);
        onSelect({candidate:choice,graph:result});
      })
      .catch(e=>{if(!controller.signal.aborted)setGraphError((e as Error).message)});
    return ()=>controller.abort();
  },[context,clarificationHeader,clarifications.reviewed,choice,graphRetry,onSelect]);

  function resetChoice(){
    setChoice(null);
    setGraph(null);
    setGraphError('');
    onSelect(null);
  }
  const items=page?.items||[];
  return <fieldset className="vin-catalogue-select" aria-label="Модифікація та план">
    <legend>Модифікація та план</legend>
    {busy&&<p role="status">Шукаємо сумісні модифікації…</p>}
    {error&&<p role="alert">{error}</p>}
    {(error||page?.status==='unavailable')&&<button type="button" disabled={disabled||busy}
      onClick={()=>{resetChoice();setRetry(n=>n+1)}}>Повторити пошук</button>}
    {page?.status==='manufacturer_required'&&<p role="status">Вкажіть марку для пошуку модифікацій.</p>}
    {page?.status==='unavailable'&&<p role="alert">Довідник модифікацій тимчасово недоступний.</p>}
    {page?.status==='incomplete'&&<p role="status">Пошук неповний. Виберіть модель, щоб перевірити її окремо.</p>}
    {page?.search_complete&&!items.length&&<p role="status">Сумісних модифікацій не знайдено.</p>}
    {models.length>1&&<label>Модель із довідника
      <select value={scope?modelKey(scope):''} disabled={disabled||busy} onChange={e=>{
        resetChoice();
        setScope(models.find(row=>modelKey(row)===e.target.value)||null);
        setCursor(0);
      }}>
        <option value="">Моделі за характеристиками VIN</option>
        {models.map(row=><option key={modelKey(row)} value={modelKey(row)}>
          {row.model} {row.construction_interval||''} · {row.kind==='passenger'?'легкова':'комерційна'}
        </option>)}
      </select>
    </label>}
    {!scope&&page?.model_cursors?.map(cursor=><button type="button" key={cursor.maker}
      disabled={disabled||busy} onClick={()=>{resetChoice();setModelPage(cursor)}}>
      Наступні моделі · {cursor.kind==='passenger'?'легкові':'комерційні'}
    </button>)}
    {page?.questions.map(question=>question.options.length===0?<form className="vin-actions" key={question.field}
      onSubmit={e=>{
        e.preventDefault();
        const value=String(new FormData(e.currentTarget).get('answer')||'').trim();
        if(value)onAnswer(question.field,value);
      }}>
      <label>{fieldLabels[question.field]}<input name="answer" inputMode="numeric"
        pattern="[0-9]{4}" maxLength={4} disabled={disabled} required/></label>
      <button type="submit" disabled={disabled}>Уточнити</button>
      <button type="button" disabled={disabled} onClick={()=>onAnswer(question.field,null)}>Невідомо</button>
    </form>:<label key={question.field}>{fieldLabels[question.field]||question.field}
      <select disabled={disabled||busy} value="" onChange={e=>onAnswer(question.field,e.target.value||null)}>
        <option value="" disabled>Уточніть характеристику</option>
        <option value="unknown">Невідомо</option>
        {question.options.map(value=><option key={value}>{value}</option>)}
      </select>
    </label>)}
    {!!items.length&&<label>Доступні модифікації
      <select value={choice?.choice||''} disabled={disabled||busy} onChange={e=>{
        resetChoice();
        const picked=items.find(item=>item.choice===e.target.value)||null;
        if(picked)onPending(true);
        setChoice(picked);
      }}>
        <option value="">Базовий каталог CarPot</option>
        {items.map(item=><option key={item.choice} value={item.choice}>
          {item.model} · {item.modification} {item.construction_interval||''}
        </option>)}
      </select>
    </label>}
    {page?.next_after!=null&&scope&&<button type="button" disabled={disabled||busy} onClick={()=>{
      resetChoice();setCursor(page.next_after!);
    }}>Наступні модифікації</button>}
    {!scope&&models.length===1&&page&&!page.search_complete&&<button type="button" disabled={disabled||busy}
      onClick={()=>{resetChoice();setScope(models[0]);setCursor(0)}}>Переглянути всі модифікації моделі</button>}
    {choice&&choice.matches.model==='unknown'&&!clarifications.reviewed&&<div>
      <p>Назва моделі в джерелі VIN неоднозначна. Перевірте вибір або уточніть назву моделі.</p>
      <button type="button" disabled={disabled} onClick={onReview}>Назву моделі перевірено</button>
    </div>}
    {choice&&(choice.matches.model!=='unknown'||clarifications.reviewed)&&!graph&&!graphError&&<p role="status">Перевіряємо граф запчастин…</p>}
    {graph&&<p role="status">{readinessLabels[graph.status]||readinessLabels.unavailable}</p>}
    {graph?.status==='unavailable'&&<button type="button" disabled={disabled}
      onClick={()=>{onSelect(null);onPending(true);setGraphRetry(n=>n+1)}}>Перевірити каталог ще раз</button>}
    {graphError&&<><p role="alert">{graphError}</p><button type="button" disabled={disabled} onClick={()=>{
      onSelect(null);onPending(true);setGraphRetry(n=>n+1);
    }}>Повторити перевірку</button></>}
    {!choice&&<p>План за базовим каталогом CarPot.</p>}
  </fieldset>;
}
