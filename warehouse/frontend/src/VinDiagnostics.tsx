import {useState} from 'react';
import {api,type Row} from './api';
import type {VinDecode} from './VehicleVinQuickAdd';

export default function VinDiagnostics({vin,result}:{vin:string;result:VinDecode}){
 const valid=/^[A-HJ-NPR-Z0-9]{17}$/.test(vin);
 const [vinstateReady,setVinstateReady]=useState<Row|null>(null);
 const [vinstateReport,setVinstateReport]=useState<Row|null>(null);
 const [vinstateBusy,setVinstateBusy]=useState(false),[vinstateError,setVinstateError]=useState('');
 const [vinstateApproved,setVinstateApproved]=useState(false);
 const [vincarioBalance,setVincarioBalance]=useState<Row|null>(null);
 const [vincarioTrial,setVincarioTrial]=useState<Row|null>(null);
 const [vinEvidenceRestore,setVinEvidenceRestore]=useState<Row|null>(null);
 async function restoreVinEvidence(){
  setVincarioTrialBusy(true);setVincarioTrialError('');
  try{setVinEvidenceRestore(await api<Row>('/vehicles/vin/vincario/trial/restore-controls','POST'));}
  catch(e){setVincarioTrialError((e as Error).message);}
  finally{setVincarioTrialBusy(false);}
 }
 async function loadSavedVinEvidence(){
  if(!valid)return;
  setVincarioTrialBusy(true);setVincarioTrialError('');
  try{setVincarioTrial(await api<Row>('/vehicles/vin/vincario/trial/saved?vin='+encodeURIComponent(vin)));}
  catch(e){setVincarioTrialError((e as Error).message);}
  finally{setVincarioTrialBusy(false);}
 }

 const [vincarioTrialReady,setVincarioTrialReady]=useState<Row|null>(null);
 const [vincarioTrialConfirmed,setVincarioTrialConfirmed]=useState(false);
 const [vincarioTrialBusy,setVincarioTrialBusy]=useState(false);
 const [vincarioTrialError,setVincarioTrialError]=useState('');
 async function inspectVincarioTrial(){
  setVincarioTrialBusy(true);setVincarioTrialError('');
  try{setVincarioTrialReady(await api<Row>('/vehicles/vin/vincario/trial/readiness'));}
  catch(e){setVincarioTrialError((e as Error).message);}
  finally{setVincarioTrialBusy(false);}
 }
 async function runVincarioTrial(){
  if(!valid||!vincarioTrialConfirmed||vincarioTrialBusy)return;
  setVincarioTrialBusy(true);setVincarioTrialError('');setVincarioTrial(null);
  try{setVincarioTrial(await api<Row>('/vehicles/vin/vincario/trial/preview','POST',
    {vin:vin.toUpperCase(),acknowledge_free_quota:true}));}
  catch(e){setVincarioTrialError((e as Error).message);}
  finally{setVincarioTrialBusy(false);}
 }

 const [vincarioBusy,setVincarioBusy]=useState(false),[vincarioError,setVincarioError]=useState('');
 async function getVincarioBalance(){
  if(vincarioBusy)return;
  setVincarioBusy(true);setVincarioError('');
  try{setVincarioBalance(await api<Row>('/vehicles/vin/vincario/balance','POST'));}
  catch(e){setVincarioError((e as Error).message);}
  finally{setVincarioBusy(false);}
 }

 async function checkVinstate(){
  setVinstateBusy(true);setVinstateError('');
  try{setVinstateReady(await api('/vehicles/vin/vinstate/readiness'));}
  catch(e){setVinstateError((e as Error).message);}
  finally{setVinstateBusy(false);}
 }
 async function previewVinstate(){
  if(!valid||!vinstateApproved||vinstateBusy||!vinstateReady?.diagnostic_enabled)return;
  setVinstateBusy(true);setVinstateError('');setVinstateReport(null);
  try{setVinstateReport(await api('/vehicles/vin/vinstate/preview','POST',{vin,acknowledge_provider_quota:true}));}
  catch(e){setVinstateError((e as Error).message);}
  finally{setVinstateBusy(false);}
 }

 return <details className="vin-source-status"><summary>Технічні деталі</summary>{result.cached&&<p>Нещодавно отримана відповідь з кешу; час спостереження збережено.</p>}{Object.entries(result.provider_status||{}).map(([name,state])=><p key={name}>{name}: {state==='reported'?'дані отримано':state==='not_needed'?'доповнення не потрібне':state==='robots_denied'?'автоматичний доступ заборонено правилами джерела':state==='rate_limited'?'досягнуто обмеження частоти':state==='empty'||state==='no_explicit_vehicle_data'?'потрібних даних немає':state==='not_enabled'||state==='not_enabled_or_no_data'?'вимкнено або даних немає':state==='empty_or_quota_unavailable'?'даних немає або вичерпано квоту':'дані недоступні; повторіть пізніше'}{state==='reported'&&<span> · Прийнято полів: {result.provider_contributions?.[name]?.length??0}{(result.provider_contributions?.[name]?.length??0)>0&&' ('+result.provider_contributions?.[name]?.join(', ')+')'}</span>}</p>)}<div className="vinstate-test">
     <button type="button" disabled={vincarioBusy} onClick={()=>void getVincarioBalance()}>{vincarioBusy?'Перевірка балансу Vincario…':'Vincario: перевірити API-баланс'}</button>
     {vincarioError&&<p role="alert">{vincarioError}</p>}
     {vincarioBalance&&<div role="status"><p>Vincario API: {vincarioBalance.status}</p><p>VIN Decode: {vincarioBalance.decode_balance_status==='available'?String(vincarioBalance.decode_balance):vincarioBalance.decode_balance_status==='not_returned'?'поле відсутнє у відповіді API':'значення не розпізнане'}</p>{Object.entries(vincarioBalance.balances||{}).filter(([k])=>k!=='API Decode').map(([k,v])=><p key={k}>{k}: {String(v)}</p>)}<p>Назви полів відповіді: {(vincarioBalance.provider_balance_fields||[]).map((f:Row)=>String(f.name)+' ['+String(f.type)+']').join(', ')||'немає доступних даних'}</p><p>Платне декодування: вимкнене. Наявність балансу не підтверджує безкоштовну квоту.</p></div>}
    <div className="vinstate-test">
      <button type="button" disabled={vincarioTrialBusy} onClick={()=>void restoreVinEvidence()}>Зберегти 3 попередні результати VIN у базі (без API)</button>
      {vinEvidenceRestore&&<p role="status">Збережено: {(vinEvidenceRestore.created||[]).length} · Уже були: {(vinEvidenceRestore.already_saved||[]).length} · API-запитів: 0</p>}
      <button type="button" disabled={vincarioTrialBusy||!valid} onClick={()=>void loadSavedVinEvidence()}>Переглянути збережені дані VIN</button>
      <button type="button" disabled={vincarioTrialBusy} onClick={()=>void inspectVincarioTrial()}>Vincario: перевірити готовність Free Demo</button>
      {vincarioTrialReady&&<p>Тест: {vincarioTrialReady.credentials_present&&vincarioTrialReady.staging?'готовий':'недоступний'} · Дозволені VIN: 3 · Платежі CarPot: вимкнені</p>}
      {vincarioTrialReady?.credentials_present&&vincarioTrialReady?.staging&&
       (vincarioTrialReady.supported_vins||[]).includes(vin.toUpperCase())&&<>
        <label className="vin-confirm"><input type="checkbox" checked={vincarioTrialConfirmed} onChange={e=>setVincarioTrialConfirmed(e.target.checked)}/>Підтверджую один тестовий запит Vincario Free Demo для цього VIN (витратиться 1 API Decode кредит).</label>
        <button type="button" disabled={!vincarioTrialConfirmed||vincarioTrialBusy||!valid} onClick={()=>void runVincarioTrial()}>{vincarioTrialBusy?'Отримання даних…':'Тест Vincario — один VIN'}</button>
       </>}
      {vincarioTrialError&&<p role="alert">{vincarioTrialError}</p>}
      {vincarioTrial&&<div role="status"><p>Vincario: {vincarioTrial.status} {vincarioTrial.from_cache||vincarioTrial.from_durable_cache?'(збережено)':''} · Джерело: {vincarioTrial.source||'API Free Demo'}</p><p>API Decode до / після: {vincarioTrial.balance_before??'—'} / {vincarioTrial.balance_after??'—'}</p>{vincarioTrial.vehicle&&<p>Дані: {Object.entries(vincarioTrial.vehicle).map(([k,v])=>k+': '+String(v)).join(', ')||'немає'}</p>}{vincarioTrial.missing&&<p>Відсутні: {(vincarioTrial.missing as string[]).join(', ')||'немає'}</p>}{vincarioTrial.logo_field_available&&<p>Логотип: поле існує, права на використання ще не підтверджено.</p>}</div>}
     </div></div><div className="vinstate-test">
     <button type="button" disabled={vinstateBusy} onClick={()=>void checkVinstate()}>VINState: перевірити тестовий режим</button>
     {vinstateReady&&<p>Ключ: {vinstateReady.key_present?'наявний':'не налаштовано'} · Тестування: {vinstateReady.diagnostic_enabled?'доступне':'вимкнено'}</p>}
     {vinstateReady?.diagnostic_enabled&&<>
      <label className="vin-confirm"><input type="checkbox" checked={vinstateApproved} onChange={e=>setVinstateApproved(e.target.checked)}/>Розумію, що запит може витратити квоту VINState або придбані кредити.</label>
      <button type="button" disabled={!valid||!vinstateApproved||vinstateBusy} onClick={()=>void previewVinstate()}>Тест VINState — один запит</button>
     </>}
     {vinstateError&&<p role="alert">{vinstateError}</p>}
     {vinstateReport&&<div role="status"><p>VINState: {vinstateReport.status}</p><p>Явні поля: {Object.entries(vinstateReport.vehicle||{}).map(([k,v])=>k+': '+String(v)).join(', ')||'відсутні'}</p><p>Діагностичний опис: {vinstateReport.vehicle_label||'відсутній'}</p><p>Джерело квоти: {vinstateReport.billing?.funding_source||'невідомо'}, кредити: {vinstateReport.billing?.charged_credits??'невідомо'}</p><p>Секції відповіді: {(vinstateReport.response_shape?.sections||[]).join(', ')||'не виявлено'} · Рядків: {vinstateReport.response_shape?.data_rows??'невідомо'} · Метадані оплати: {vinstateReport.response_shape?.billing_meta_present?'присутні':'відсутні'}</p><p>Структура полів (без значень): {(vinstateReport.response_shape?.fields||[]).map((f:Row)=>String(f.path)+' ['+String(f.type)+(f.populated?', заповнено':'')+']').join(', ')||'відсутня'}</p></div>}
    </div></details>;
}
