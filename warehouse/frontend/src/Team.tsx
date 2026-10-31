import {Link} from 'react-router-dom';
import {Users,UserPlus,ShieldCheck,LockKeyhole,Activity,Download,BarChart3} from 'lucide-react';
import {useEffect,useRef,useState} from 'react';
import {api,type Row} from './api';
import {State,useLoad,type Notify} from './shared';
import {Empty,Modal} from './components';
import {useCan,roleLabel} from './permissions';
import {isTeamReady} from './teamReadiness';
import './team.css';

const descriptions:Record<string,string>={
 'Склад':'Перегляд запасів і окремі дозволи на зміну даних та кількості.',
 'Фінанси':'Собівартість і фактичні суми продажів приховуються без цих дозволів.',
 'Продажі':'Перегляд історії та проведення продажу — окремі можливості.',
 'Замовлення':'Робота з покупцями, замовленнями, резервами та виконанням.',
 'Автомобілі':'Донори, робочий каталог деталей і контрольований імпорт.',
 'Аналітика':'Статистика, фінансові показники та журнал дій.',
 'Команда':'Перегляд працівників і делеговане керування менеджерами.',
 'Налаштування':'Лише наявні можливості налаштування робочого простору.',
};
export default function Team({user,notify}:{user:Row;notify:Notify}){
 const can=useCan(),guard=useRef(false);
 const [edit,setEdit]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[page,setPage]=useState(0);
 const [q,setQ]=useState(''),[role,setRole]=useState(''),[status,setStatus]=useState('');
 const readiness=useLoad(async()=>{
  const r=await api('/team/readiness','GET',undefined,200);
  if(!isTeamReady(r))throw Error('Керування командою тимчасово недоступне. Спробуйте ще раз.');
  return r;
 },[]);
 useEffect(()=>{
  const refresh=()=>readiness.reload();
  const timer=window.setInterval(refresh,30000);
  window.addEventListener('focus',refresh);
  return ()=>{window.clearInterval(timer);window.removeEventListener('focus',refresh);};
 },[]);
 const summary=useLoad(()=>api('/team/summary'),[]);
 const data=useLoad(()=>readiness.data&&!readiness.error?Promise.all([
  api('/team?offset='+page*50+'&limit=50'),api('/team/permissions'),
 ]):Promise.resolve(null),[readiness.data,readiness.error,page]);
 const teamEvents=useLoad(()=>user.role==='DIRECTOR'?api('/team/events?offset=0&limit=100'):Promise.resolve(null),[user.role]);
 const recentEvents:Row[]=teamEvents.data?.items||[];
 const dailyActivity=Array.from({length:7},(_,i)=>{
  const date=new Date();date.setHours(0,0,0,0);date.setDate(date.getDate()-(6-i));
  const key=date.toLocaleDateString('en-CA');
  return {label:date.toLocaleDateString('uk-UA',{day:'2-digit',month:'2-digit'}),value:recentEvents.filter((ev:Row)=>ev.created_at&&new Date(ev.created_at).toLocaleDateString('en-CA')===key).length};
 });
 const peak=Math.max(1,...dailyActivity.map(d=>d.value));
 function exportVisible(){
  const headers=['Ім’я','Email','Роль','Статус','Останній вхід'];
  const cells=visible.map(u=>[u.name,u.email,roleLabel(u.role),u.is_active?'Активний':'Заблокований',u.last_login_at||'']);
  const csv='\uFEFF'+[headers,...cells].map(row=>row.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(';')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='carpot-team-current-page.csv';a.click();URL.revokeObjectURL(url);
 }
 const groups=data.data?.[1]?.groups||{},grantable:string[]=data.data?.[1]?.grantable||[];
 const members:Row[]=data.data?.[0]?.items||[];
 const visible=members.filter(u=>(!role||u.role===role)&&(!status||(status==='active')===u.is_active)&&`${u.name} ${u.email}`.toLocaleLowerCase('uk-UA').includes(q.trim().toLocaleLowerCase('uk-UA')));
 const manageable=(u:Row)=>can('team.manage_managers')&&u.id!==user.id&&u.role!=='DIRECTOR'&&(user.role==='DIRECTOR'||(user.role==='ADMIN'&&u.role==='MANAGER'));
 const resettable=(u:Row)=>manageable(u)&&(user.role==='DIRECTOR'||u.permissions.every((p:string)=>grantable.includes(p)));
 function open(u:Row){setError('');setEdit({...u,permissions:[...u.permissions],original_active:u.is_active});}
 const activationBlocked=!!edit?.id&&!edit.original_active&&edit.is_active&&user.role!=='DIRECTOR'&&edit.permissions.some((p:string)=>!grantable.includes(p));
 async function save(e:React.FormEvent){
  e.preventDefault();if(guard.current||!edit||activationBlocked)return;
  guard.current=true;setBusy(true);setError('');
  try{
   if(edit.reset){
    await api('/team/'+edit.id+'/reset-password','POST',{password:edit.password});
    notify('Усі сесії завершено. Передайте новий тимчасовий пароль особисто');
   }else{
    const body={name:edit.name,role:edit.role,permissions:edit.permissions,...(edit.id?{is_active:edit.is_active}:{email:edit.email,password:edit.password})};
    await api('/team'+(edit.id?'/'+edit.id:''),edit.id?'PATCH':'POST',body);
    notify('Дані працівника збережено');
   }
   setEdit(null);data.reload();summary.reload();readiness.reload();
  }catch(e){setError((e as Error).message);data.reload();}
  finally{guard.current=false;setBusy(false);}
 }
 if(readiness.error||(!readiness.data&&readiness.loading))return <section className="panel padded"><h1>Команда</h1><State error={readiness.error} loading={readiness.loading}/><button disabled={readiness.loading} onClick={readiness.reload}>Перевірити готовність команди</button></section>;
 return <>
  <div className="page-heading"><div><h1>Команда</h1><p>{user.workspace_name} · особисті облікові записи працівників</p></div>
   {can('team.manage_managers')&&readiness.data?.employee_creation_enabled&&<button disabled={!data.data||data.loading||!!data.error} onClick={()=>open({name:'',email:'',password:'',role:'MANAGER',permissions:['inventory.view','vehicles.view','catalog.view'].filter(p=>grantable.includes(p)),is_active:true})}>Додати працівника</button>}
  </div>
  {!readiness.data?.employee_creation_enabled&&<p className="notice" role="status">Створення співробітників ще не ввімкнено. Для додавання працівників директору потрібно погодити активацію модуля. Наявними обліковими записами можна керувати.</p>}
  <button className="secondary" onClick={()=>{readiness.reload();summary.reload();data.reload();}}>Оновити команду та доступність створення</button>
  <State error={summary.error} loading={summary.loading}/>
  {summary.data&&!summary.error&&<section className="team-summary" aria-label="Підсумки команди">
   {Object.entries({'Усього облікових записів':summary.data.total,'Активні':summary.data.active,'Заблоковані':summary.data.blocked,'Директори':summary.data.by_role.DIRECTOR,'Адміністратори':summary.data.by_role.ADMIN,'Менеджери':summary.data.by_role.MANAGER}).map(([label,value])=><div className="panel padded" key={label}><span>{label}</span><strong>{String(value)}</strong></div>)}
   <small>{summary.data.scope==='workspace'?'Усі облікові записи робочого простору, включно з директором.':'Лише менеджери, доступні вам за правами.'}</small>
  </section>}
  <section className="team-dashboard-actions" aria-label="Дії з командою">
   <h2>Дії з командою</h2>
   <div className="team-action-grid">
    <button type="button" disabled={!can('team.manage_managers')||!readiness.data?.employee_creation_enabled||!data.data} onClick={()=>open({name:'',email:'',password:'',role:'MANAGER',permissions:['inventory.view','vehicles.view','catalog.view'].filter(p=>grantable.includes(p)),is_active:true})}><UserPlus size={20}/><span><strong>Додати працівника</strong><small>Особистий обліковий запис</small></span></button>
    <button type="button" disabled={!can('team.manage_managers')||!members.some(manageable)} onClick={()=>{document.getElementById('team-members')?.scrollIntoView({behavior:'smooth',block:'start'});}}><ShieldCheck size={20}/><span><strong>Ролі та допуски</strong><small>Редагування прав працівника</small></span></button>
    <button type="button" disabled={!can('team.manage_managers')||!members.some(manageable)} onClick={()=>{setStatus('active');document.getElementById('team-members')?.scrollIntoView({behavior:'smooth',block:'start'});}}><LockKeyhole size={20}/><span><strong>Керування доступом</strong><small>Блокування через картку працівника</small></span></button>
    <button type="button" disabled={!data.data||!visible.length} onClick={exportVisible}><Download size={20}/><span><strong>Експорт CSV</strong><small>Працівники поточної сторінки</small></span></button>
   </div>
  </section>
  <section className="team-insights" aria-label="Аналітика команди">
   <div className="panel padded team-insight-panel">
    <header><h2><Activity size={18}/> Зміни в команді за 7 днів</h2></header>
    {user.role==='DIRECTOR'?<>
     <div className="team-bars" role="img" aria-label={'Кількість подій керування командою за 7 днів: '+dailyActivity.map(d=>d.label+': '+d.value).join(', ')}>
      {dailyActivity.map(d=><div className="team-bar-column" key={d.label}><span className="team-bar-value">{d.value}</span><div className="team-bar-track"><div style={{height:(d.value/peak*100)+'%'}}/></div><small>{d.label}</small></div>)}
     </div>
     <small className="muted">Лише події керування командою. Останні {recentEvents.length} доступних записів; не загальна активність складу.</small>
     {teamEvents.error&&<p role="alert">{teamEvents.error}</p>}
    </>:<p className="muted">Журнал змін команди доступний директору.</p>}
   </div>
   <div className="panel padded team-insight-panel">
    <header><h2><Users size={18}/> Працівники за ролями</h2></header>
    {summary.data&&<div className="team-role-list">{(['DIRECTOR','ADMIN','MANAGER'] as const).map(roleName=>{
     const n=summary.data?.by_role?.[roleName]||0,total=Math.max(1,summary.data?.total||0);
     return <div key={roleName}><div className="team-role-label"><span>{roleLabel(roleName)}</span><strong>{n}</strong></div><div className="team-role-track"><div style={{width:(n/total*100)+'%'}}/></div></div>;
    })}</div>}
    <small className="muted">Фактичні облікові записи у доступній області перегляду.</small>
   </div>
   <div className="panel padded team-insight-panel">
    <header><h2><BarChart3 size={18}/> Останні зміни доступів</h2></header>
    {user.role==='DIRECTOR'?<div className="team-event-list">{recentEvents.slice(0,5).map(ev=><div key={ev.id}><span>{({employee_created:'Створення працівника',employee_updated:'Зміна ролі або доступів',access_reset:'Скидання доступу',password_changed:'Зміна пароля'} as Record<string,string>)[ev.type]||'Подія команди'}</span><time>{new Date(ev.created_at).toLocaleString('uk-UA',{dateStyle:'short',timeStyle:'short'})}</time></div>)}{!recentEvents.length&&<p className="muted">Подій поки немає.</p>}</div>:<p className="muted">Історія доступна директору.</p>}
   </div>
  </section>
  <section className="panel padded team-filters" aria-label="Фільтри команди">
   <label>Пошук на цій сторінці<input type="search" aria-label="Пошук працівників на сторінці" value={q} onChange={e=>setQ(e.target.value)} placeholder="Ім’я або email"/></label>
   <label>Роль<select aria-label="Роль у списку" value={role} onChange={e=>setRole(e.target.value)}><option value="">Усі ролі</option>{['DIRECTOR','ADMIN','MANAGER'].map(r=><option value={r} key={r}>{roleLabel(r)}</option>)}</select></label>
   <label>Статус<select aria-label="Статус працівника" value={status} onChange={e=>setStatus(e.target.value)}><option value="">Усі</option><option value="active">Активні</option><option value="blocked">Заблоковані</option></select></label>
  </section>
  <State error={data.error} loading={data.loading}/>{data.error&&<button onClick={data.reload}>Оновити команду</button>}
  <div id="team-members" className="team-list">{visible.map(u=><article className="panel padded" key={u.id}>
   <header><h2>{u.name}</h2><span className="team-status">{u.is_active?'Активний':'Заблокований'}</span></header><p>{u.email}</p>
   <p>{roleLabel(u.role)} · Дозволів: {u.permissions.length}{u.must_change_password?' · Потрібна зміна пароля':''}</p>
   <small>Створено: {new Date(u.created_at).toLocaleDateString('uk-UA')} · Останній вхід: {u.last_login_at?new Date(u.last_login_at).toLocaleString('uk-UA'):'Не зафіксовано'}</small>
   {can('audit.view')&&<Link to={'/analytics?actor_id='+encodeURIComponent(u.id)}>Історія операцій: {u.name}</Link>}
   {manageable(u)&&<><div className="modal-actions"><button onClick={()=>open(u)}>Права та доступ: {u.name}</button><button disabled={!resettable(u)} onClick={()=>{open(u);setEdit({...u,reset:true,password:''});}}>Скинути доступ: {u.name}</button></div>
    {!resettable(u)&&<small>Скинути доступ працівнику з ширшими правами може директор.</small>}</>}
  </article>)}</div>
  {data.data&&!data.loading&&!data.error&&!visible.length&&<Empty title={members.length?'Працівників не знайдено':'Співробітників ще немає'}>{members.length?'Змініть фільтри на цій сторінці.':'Після створення тут з’являться особисті облікові записи команди.'}</Empty>}
  <div className="pager"><span>Сторінка {page+1} · Усього: {data.data?.[0]?.total||0}</span><button disabled={!page||data.loading} onClick={()=>setPage(page-1)}>Попередні працівники</button><button disabled={data.loading||(page+1)*50>=(data.data?.[0]?.total||0)} onClick={()=>setPage(page+1)}>Наступні працівники</button></div>
  {edit&&<Modal className="team-edit-dialog" title={edit.reset?'Скидання доступу':edit.id?'Права працівника':'Новий співробітник'} onClose={()=>{if(!busy)setEdit(null);}}><form onSubmit={save}>
   {!edit.reset&&<>
    <label>Ім’я<input required maxLength={120} value={edit.name} onChange={e=>setEdit({...edit,name:e.target.value})}/></label>
    {!edit.id&&<label>Електронна пошта<input type="email" autoComplete="off" required maxLength={254} value={edit.email} onChange={e=>setEdit({...edit,email:e.target.value})}/></label>}
    <label>Роль<select aria-label="Роль" value={edit.role} onChange={e=>setEdit({...edit,role:e.target.value,permissions:e.target.value==='MANAGER'?edit.permissions.filter((p:string)=>p!=='team.manage_managers'):edit.permissions})}><option value="MANAGER">Менеджер</option>{user.role==='DIRECTOR'&&<option value="ADMIN">Адміністратор</option>}</select></label>
    {edit.id&&<label className="check-inline"><input type="checkbox" checked={edit.is_active} onChange={e=>setEdit({...edit,is_active:e.target.checked})}/>Доступ активний</label>}
    {edit.id&&edit.original_active&&!edit.is_active&&<p className="notice">Збереження заблокує вхід і завершить усі сесії цього працівника. Історія залишиться.</p>}
    <div className="permission-groups">{Object.entries(groups).map(([group,permissions])=><fieldset key={group}><legend>{group}</legend>{descriptions[group]&&<p className="muted">{descriptions[group]}</p>}{Object.entries(permissions as Record<string,string>).map(([key,label])=><label className="check-inline" key={key}><input type="checkbox" disabled={(!grantable.includes(key)&&!edit.permissions.includes(key))||(edit.role==='MANAGER'&&key==='team.manage_managers')} checked={edit.permissions.includes(key)} onChange={e=>setEdit({...edit,permissions:e.target.checked?[...edit.permissions,key]:edit.permissions.filter((p:string)=>p!==key)})}/>{label}</label>)}</fieldset>)}</div>
   </>}
   {(!edit.id||edit.reset)&&<><label>Тимчасовий пароль<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={edit.password} onChange={e=>setEdit({...edit,password:e.target.value})}/></label><p>Передайте пароль працівнику особисто захищеним каналом. При першому вході він зобов’язаний змінити пароль. Старий пароль не розкривається.</p></>}
   {activationBlocked&&<p role="alert">Для активації відкличте права, які ви не можете делегувати, або зверніться до директора.</p>}
   {error&&<p role="alert">{error}</p>}
   <div className="modal-actions"><button className="primary" disabled={busy||activationBlocked}>{busy?'Збереження…':'Зберегти працівника'}</button></div>
  </form></Modal>}
 </>;
}
export function PasswordChange({user,onDone}:{user:Row;onDone:()=>void}){
 const guard=useRef(false),[current,setCurrent]=useState(''),[next,setNext]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 return <section className="panel padded team-password"><h1>Змініть тимчасовий пароль</h1><p>{user.name} · {roleLabel(user.role)} · {user.workspace_name}</p><p>Після збереження увійдіть з новим паролем. Усі попередні сесії будуть завершені.</p><form onSubmit={async e=>{
  e.preventDefault();if(guard.current)return;guard.current=true;setBusy(true);setError('');
  try{await api('/auth/password','POST',{current_password:current,password:next});onDone();}
  catch(e){setError((e as Error).message);}finally{guard.current=false;setBusy(false);}
 }}><label>Поточний пароль<input type="password" autoComplete="current-password" required value={current} onChange={e=>setCurrent(e.target.value)}/></label><label>Новий пароль<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={next} onChange={e=>setNext(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}<div className="modal-actions"><button disabled={busy}>Змінити пароль</button><button type="button" disabled={busy} onClick={async()=>{try{await api('/auth/logout','POST');onDone();}catch(e){setError((e as Error).message);}}}>Вийти</button></div></form></section>;
}
