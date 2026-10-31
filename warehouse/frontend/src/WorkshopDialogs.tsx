import {useRef,useState,type ReactNode} from 'react';
import {useLoad} from './shared';
import {api,type Row} from './api';
import {Modal} from './components';
export function NotesDialog({part,onClose,onSaved}:{part:Row;onClose:()=>void;onSaved:(row:Row)=>void}){
 const [notes,setNotes]=useState(part.internal_notes||''),[error,setError]=useState(''),[busy,setBusy]=useState(false),guard=useRef(false);
 return <Modal title={`Нотатка: ${part.name}`} onClose={onClose}><form onSubmit={async e=>{e.preventDefault();if(guard.current)return;guard.current=true;setBusy(true);setError('');try{onSaved(await api(`/parts/${part.id}/notes`,'PATCH',{internal_notes:notes,expected_notes:part.internal_notes||''}));}catch(e){setError((e as Error).message);}finally{guard.current=false;setBusy(false);}}}><label>Внутрішня нотатка<textarea aria-label="Внутрішня нотатка" maxLength={10000} value={notes} onChange={e=>setNotes(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}<div className="modal-actions"><button className="primary" disabled={busy}>Зберегти нотатку</button></div></form></Modal>;
}
export function InspectionDialog({part,onClose,onSaved}:{part:Row;onClose:()=>void;onSaved:(row:Row)=>void}){
 const [condition,setCondition]=useState(part.condition),[availability,setAvailability]=useState(part.availability),[busy,setBusy]=useState(false),[error,setError]=useState('');
 return <Modal title={`Стан і перевірка: ${part.name}`} onClose={onClose}><form onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);try{onSaved(await api(`/parts/${part.id}/inspection`,'PATCH',{condition,availability}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
 <label>Фізичний стан<select aria-label="Фізичний стан" value={condition} onChange={e=>setCondition(e.target.value)}><option value="unknown">Не уточнено</option><option value="used">Вживана</option><option value="new">Нова</option><option value="damaged">Пошкоджена</option><option value="refurbished">Відновлена</option></select></label>
 <label>Перевірка наявності<select aria-label="Перевірка наявності" value={availability} onChange={e=>setAvailability(e.target.value)}><option value="unchecked">Потребує перевірки</option><option value="present">Наявність підтверджено</option><option value="absent">Наявність не підтверджено</option><option value="damaged">Пошкодження (попередня позначка)</option></select></label><p>Ці позначки не змінюють кількість. Пошкоджену деталь можна продати за наявності доступного залишку.</p>{error&&<p role="alert">{error}</p>}<div className="modal-actions"><button className="primary" disabled={busy}>Зберегти стан</button></div></form></Modal>;
}

// A shared commit may finish frontend Auto Deploy first. New mutations stay
// unavailable until the server explicitly confirms every Workshop capability.
export function WorkshopGate({children}:{children:ReactNode}) {
 const {data,error,loading,reload}=useLoad(async()=>{
  const result=await api('/workshop/readiness');
  const features=['actual_quick_sale_price','ledger_sales_projection','notes_compare_and_set','inspection_patch'];
  // required_revision is the v7 minimum schema, not the installed Alembic head.
  const revisions=result?.database_revisions;
  const allowedHeads=['d86f21a90b34','a73e05b9c842','b94f62d18e07','b8716962f6b8','021e8f6f220c','41f9a2c87d10','5c7d9e1a320f','76af12de4b90','84d2c6fa190b','95c3e7b12a04','a6d94c72e310','b7e14d90c2f6','c8f21d6e903a','d3a82f1c904b','e4b93a2d715c','f5c84d31a620','c7e49f2a118d'];
  const singleKnownHead=Array.isArray(revisions)&&revisions.length===1&&allowedHeads.includes(revisions[0]);
  if(result?.status!=='ready'||result.contract_version!==7||result.required_revision!=='d86f21a90b34'||!singleKnownHead||!Array.isArray(result.features)||!features.every(f=>result.features.includes(f)))throw Error('Backend майстерні ще не підтвердив готовність.');
  return result;
 },[]);
 if(loading||error||!data)return <section className="panel padded" aria-label="Оновлення майстерні"><p role="status">Оновлення майстерні. Нові дії стануть доступними після готовності сервера.</p>{error&&<p>Сервер ще не готовий або недоступний.</p>}<button disabled={loading} onClick={reload}>Перевірити готовність</button></section>;
 return children;
}
