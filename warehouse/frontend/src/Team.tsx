import {Link} from 'react-router-dom';
import {useRef,useState} from 'react';
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
 const data=useLoad(()=>readiness.data&&!readiness.error?Promise.all([
  api('/team?offset='+page*50+'&limit=50'),api('/team/permissions'),
 ]):Promise.resolve(null),[readiness.data,readiness.error,page]);
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
   setEdit(null);data.reload();
  }catch(e){setError((e as Error).message);data.reload();}
  finally{guard.current=false;setBusy(false);}
 }
 if(readiness.error||readiness.loading)return <section className="panel padded"><h1>Команда</h1><State error={readiness.error} loading={readiness.loading}/><button disabled={readiness.loading} onClick={readiness.reload}>Перевірити готовність команди</button></section>;
 return <>
  <div className="page-heading"><div><h1>Команда</h1><p>{user.workspace_name} · особисті облікові записи працівників</p></div>
   {can('team.manage_managers')&&readiness.data?.employee_creation_enabled&&<button disabled={!data.data||data.loading||!!data.error} onClick={()=>open({name:'',email:'',password:'',role:'MANAGER',permissions:['inventory.view','vehicles.view','catalog.view'].filter(p=>grantable.includes(p)),is_active:true})}>Створити співробітника</button>}
  </div>
  {!readiness.data?.employee_creation_enabled&&<p className="notice" role="status">Створення співробітників ще не ввімкнено. Наявними обліковими записами можна керувати відповідно до ваших прав.</p>}
  <section className="panel padded team-filters" aria-label="Фільтри команди">
   <label>Пошук на цій сторінці<input type="search" aria-label="Пошук працівників на сторінці" value={q} onChange={e=>setQ(e.target.value)} placeholder="Ім’я або email"/></label>
   <label>Роль<select aria-label="Роль у списку" value={role} onChange={e=>setRole(e.target.value)}><option value="">Усі ролі</option>{['DIRECTOR','ADMIN','MANAGER'].map(r=><option value={r} key={r}>{roleLabel(r)}</option>)}</select></label>
   <label>Статус<select aria-label="Статус працівника" value={status} onChange={e=>setStatus(e.target.value)}><option value="">Усі</option><option value="active">Активні</option><option value="blocked">Заблоковані</option></select></label>
  </section>
  <State error={data.error} loading={data.loading}/>{data.error&&<button onClick={data.reload}>Оновити команду</button>}
  <div className="team-list">{visible.map(u=><article className="panel padded" key={u.id}>
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
