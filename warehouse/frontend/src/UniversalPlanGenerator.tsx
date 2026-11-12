import {useContext,useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';
import {useCan,TeamIdentity} from './permissions';
import {CarFront,Check,RefreshCw} from 'lucide-react';
import './universal-generator.css';
export default function UniversalPlanGenerator({vehicle,revision,onSaved,onWorking}:{vehicle:Row;revision:number;onSaved:()=>void;onWorking?:(value:boolean)=>void}){
 const can=useCan(),who=useContext(TeamIdentity),guard=useRef(false),epoch=useRef(0);
 const [saved,setSaved]=useState<Row|null>(null),[phase,setPhase]=useState('loading'),[preview,setPreview]=useState<Row|null>(null),[error,setError]=useState(''),[sources,setSources]=useState<Row|null>(null);
 const storageKey='warehouse.catalogue.generate.2:'+JSON.stringify([who?.id,who?.workspace_account_id,vehicle.id]);
 const pending=useRef<Row|null>(null);
 useEffect(()=>{let active=true;epoch.current++;setPhase('loading');setError('');setPreview(null);setSources(null);onWorking?.(false);
  try{pending.current=JSON.parse(sessionStorage.getItem(storageKey)||'null')}catch{pending.current=null}
  api(`/vehicles/${vehicle.id}/dismantling-v3`).then(r=>{if(active){setSaved(r);setPhase(r.total?'work':'start');onWorking?.(!!r.total)}}).catch(e=>{if(active){setError(e.message);setPhase('start')}});return()=>{active=false;epoch.current++};
 },[vehicle.id,revision,storageKey]);
 const base=`/vehicles/${vehicle.id}/dismantling-v3`;
 async function persist(report:Row){
  const ticket=epoch.current;setPhase('saving');
  const body=pending.current||{facts:[],universal:true,token:report.token,request_key:crypto.randomUUID(),confirm:true};pending.current=body;
  try{sessionStorage.setItem(storageKey,JSON.stringify(body))}catch{/* The same in-memory key remains available for retry. */}
  await api(base+'/save','POST',body);if(ticket!==epoch.current)return;
  pending.current=null;try{sessionStorage.removeItem(storageKey)}catch{}
  const result=await api(base);if(ticket!==epoch.current)return;setSaved(result);setPreview(null);setPhase('result');onWorking?.(false);
 }
 async function generate(){if(guard.current)return;guard.current=true;setError('');const ticket=epoch.current;try{
  if(pending.current){await persist({});return;}
  setPhase('generating');const p=await api(base+'/preview','POST',{facts:[],universal:true});if(ticket!==epoch.current)return;
  if(saved?.total||p.counts.review){setPreview(p);setPhase('review');}else await persist(p);
 }catch(e){if(ticket===epoch.current){setError((e as Error).message);setPhase(saved?.total?'work':'start');onWorking?.(!!saved?.total)}}finally{guard.current=false}}
 async function confirmUpdate(){if(!preview||guard.current)return;guard.current=true;setError('');try{await persist(preview)}catch(e){setError((e as Error).message);setPhase('review')}finally{guard.current=false}}
 function view(){setPhase('work');onWorking?.(true);onSaved();}
 const counts={positions:saved?.total||0,categories:new Set((saved?.items||[]).map((r:Row)=>r.category)).size,review:(saved?.items||[]).filter((r:Row)=>['unknown','possible'].includes(r.applicability)).length+(saved?.pending_count||0)};
 const busy=['loading','generating','saving'].includes(phase);
 return <section className={'universal-generator dv2-'+phase} aria-label="Формування каталогу">
 {error&&<p role="alert">{error}</p>}
 {phase==='start'&&<div className="dv2-start"><CarFront size={72} aria-hidden="true"/><div><h2>{vehicle.manufacturer} {vehicle.model} · {vehicle.year}</h2><p>Сформуйте перелік запчастин для розбору автомобіля</p><small>Точна модифікація не визначена? Доступний базовий каталог CarPot.</small><button className="primary" disabled={vehicle.archived||!can('dismantling.manage')} onClick={()=>void generate()}>{pending.current?'Завершити формування':'Розібрати на запчастини'}</button></div></div>}
 {busy&&<div className="dv2-progress" role="status"><CarFront size={64} className="dv2-scanning" aria-hidden="true"/><h2>{phase==='loading'?'Відкриваємо перелік…':phase==='saving'?'Зберігаємо перелік…':'Підбираємо доступні запчастини…'}</h2><progress aria-label="Очікування відповіді"/></div>}
 {phase==='review'&&preview&&<div className="notice"><h3>Оновлення каталогу</h3><p>Нових: {preview.counts.new} · Наявних: {preview.counts.existing} · Потребують уточнення: {preview.counts.review}</p><p>Наявні складські позиції та ручні рішення збережуться. Неоднозначні зіставлення залишаться для перевірки.</p><button className="primary" onClick={()=>void confirmUpdate()}>Підтвердити оновлення</button><button onClick={()=>{setPreview(null);setPhase(saved?.total?'work':'start')}}>Скасувати</button></div>}
 {phase==='result'&&<div className="dv2-result"><Check size={32}/><h2>Каталог автомобіля готовий</h2><p>{vehicle.manufacturer} {vehicle.model}</p><div className="dv2-summary"><span>Категорій: <b>{counts.categories}</b></span><span>Потенційних позицій: <b>{counts.positions}</b></span>{counts.review>0&&<span>Потребують уточнення: <b>{counts.review}</b></span>}</div><small>Це перелік для перевірки, а не підтверджена фізична наявність.</small><div><button className="primary" onClick={view}>Переглянути результати</button><button onClick={view}>Налаштувати запчастини</button></div></div>}
 {phase==='work'&&<div className="dv2-catalogue-tools"><span><Check size={16}/>Список збережено</span><button disabled={vehicle.archived||!can('dismantling.manage')} onClick={()=>void generate()}><RefreshCw size={15}/>Оновити каталог</button>{saved?.generator_stale&&<small>Характеристики змінилися — перелік потребує перевірки.</small>}</div>}
 {who?.catalogue_platform_admin===true&&saved?.total>0&&<details className="dv2-sources" onToggle={e=>{if(e.currentTarget.open&&!sources)api(base+'/sources').then(setSources).catch(e=>setError(e.message))}}><summary>Джерела підбору</summary>{sources&&<><p>Унікальних позицій: {sources.total}</p>{Object.entries(sources.counts).map(([key,n])=><p key={key}>{({base:'Каталог CarPot',unknown:'Джерело не визначено',multiple_sources:'Кілька джерел'} as Record<string,string>)[key]||key}: {String(n)}</p>)}</>}</details>}
 </section>;
}
