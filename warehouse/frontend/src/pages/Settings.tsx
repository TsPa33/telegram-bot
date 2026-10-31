import {useRef,useState,type FormEvent} from 'react';
import {Link} from 'react-router-dom';
import {
  ArrowUpRight, Boxes, CarFront, Check, ChartNoAxesCombined, ClipboardList,
  KeyRound, LockKeyhole, LogOut, Mail, Package, ShieldCheck, UserRound,
  Users, Warehouse
} from 'lucide-react';
import {api,type Row} from '../api';
import {roleLabel,useCan} from '../permissions';
import {Heading,State,useLoad} from '../shared';
import '../settings-r123.css';

type Capability={permission:string;label:string;description:string;path:string;icon:typeof Boxes};

const shortcuts:Capability[]=[
  {permission:'vehicles.view',label:'Автомобілі',description:'Картки донорів і розбір',path:'/vehicles',icon:CarFront},
  {permission:'inventory.view',label:'Склад',description:'Запчастини та залишки',path:'/inventory',icon:Boxes},
  {permission:'sales.view',label:'Продажі',description:'Реєстр продажів',path:'/sales',icon:Package},
  {permission:'orders.view',label:'Замовлення',description:'Замовлення та резерви',path:'/sales',icon:ClipboardList},
  {permission:'analytics.view',label:'Статистика',description:'Показники складу',path:'/statistics',icon:ChartNoAxesCombined},
  {permission:'team.view',label:'Команда',description:'Працівники робочого простору',path:'/team',icon:Users},
];

function ChangeOwnPassword(){
  const guard=useRef(false);
  const [expanded,setExpanded]=useState(false);
  const [current,setCurrent]=useState('');
  const [next,setNext]=useState('');
  const [confirm,setConfirm]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const valid=!!current&&next.length>=12&&next.length<=128&&next===confirm&&next!==current;
  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(guard.current||!valid)return;
    guard.current=true;setBusy(true);setError('');
    try{
      await api('/auth/password','POST',{current_password:current,password:next});
      setCurrent('');setNext('');setConfirm('');
      // The API revokes all sessions. Reset local identity immediately.
      window.dispatchEvent(new Event('warehouse:logout'));
    }catch(err){
      setError((err as Error).message);
    }finally{
      guard.current=false;setBusy(false);
    }
  }
  return <section className="r123-panel r123-security" aria-labelledby="r123-security-heading">
    <div className="r123-panel-heading">
      <span className="r123-heading-icon"><LockKeyhole size={19}/></span>
      <div><h2 id="r123-security-heading">Безпека облікового запису</h2><p>Пароль, захищений вхід та керування сесією</p></div>
    </div>
    <div className="r123-security-row">
      <span className="r123-security-symbol"><KeyRound size={20}/></span>
      <div className="r123-security-desc"><strong>Пароль для входу</strong><span>Не менше 12 символів. Після зміни потрібно увійти повторно.</span></div>
      <button type="button" aria-expanded={expanded} aria-controls="r123-password-form" onClick={()=>{setExpanded(v=>!v);setError('');}}>{expanded?'Закрити':'Змінити пароль'}</button>
    </div>
    {expanded&&<form id="r123-password-form" className="r123-password-form" onSubmit={submit}>
      <div className="r123-password-fields">
        <label>Поточний пароль
          <input type="password" autoComplete="current-password" required minLength={12} maxLength={128} value={current} onChange={e=>setCurrent(e.target.value)} disabled={busy}/>
        </label>
        <label>Новий пароль
          <input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={next} onChange={e=>setNext(e.target.value)} disabled={busy}/>
        </label>
        <label>Повторіть новий пароль
          <input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirm} onChange={e=>setConfirm(e.target.value)} disabled={busy}/>
        </label>
      </div>
      {confirm&&confirm!==next&&<p className="r123-form-error" role="status">Новий пароль і підтвердження не збігаються.</p>}
      {next&&next===current&&<p className="r123-form-error" role="status">Новий пароль має відрізнятися від поточного.</p>}
      {error&&<p className="r123-form-error" role="alert">{error}</p>}
      <div className="r123-form-actions">
        <button type="submit" className="primary" disabled={!valid||busy}>{busy?'Збереження…':'Зберегти новий пароль'}</button>
        <button type="button" disabled={busy} onClick={()=>{setExpanded(false);setCurrent('');setNext('');setConfirm('');setError('');}}>Скасувати</button>
      </div>
    </form>}
  </section>;
}

function SessionExit(){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  return <div className="r123-logout">
    <div><strong>Завершити поточний сеанс</strong><span>Для повторного входу буде потрібен пароль.</span></div>
    <button type="button" disabled={busy} onClick={async()=>{
      setBusy(true);setError('');
      try{await api('/auth/logout','POST');window.dispatchEvent(new Event('warehouse:logout'));}
      catch(e){setError((e as Error).message);setBusy(false);}
    }}><LogOut size={16}/>{busy?'Вихід…':'Вийти з акаунта'}</button>
    {error&&<p role="alert" className="r123-form-error">{error}</p>}
  </div>;
}

export default function Settings({user}:{user:Row}){
  const can=useCan();
  const {data,error,loading,reload}=useLoad(()=>api('/settings'),[]);
  const sections=shortcuts.filter(item=>can(item.permission)).filter((item,i,items)=>item.path!=='/sales'||items.findIndex(x=>x.path==='/sales')===i);
  const permissionCount=Array.isArray(user.permissions)?user.permissions.length:0;
  return <div className="r123-settings">
    <Heading eyebrow="РОБОЧИЙ ПРОСТІР" title="Налаштування" description="Ваш профіль, безпека та доступ до інструментів CarPot Warehouse."/>
    <div className="r123-profile-bar">
      <span className="r123-profile-avatar" aria-hidden="true">{String(user.name||'К').slice(0,1).toLocaleUpperCase('uk')}</span>
      <div className="r123-profile-intro"><strong>{user.name||'Користувач'}</strong><span>{user.email}</span></div>
      <span className="r123-role"><ShieldCheck size={15}/>{roleLabel(user.role)}</span>
    </div>

    <div className="r123-grid">
      <section className="r123-panel" aria-labelledby="r123-profile-heading">
        <div className="r123-panel-heading">
          <span className="r123-heading-icon"><UserRound size={19}/></span>
          <div><h2 id="r123-profile-heading">Мій профіль</h2><p>Інформація вашого робочого облікового запису</p></div>
        </div>
        <dl className="r123-detail-list">
          <div><dt>Ім’я</dt><dd>{user.name||'Не вказано'}</dd></div>
          <div><dt>Електронна пошта</dt><dd className="r123-email">{user.email||'Не вказано'}</dd></div>
          <div><dt>Роль</dt><dd>{roleLabel(user.role)}</dd></div>
          <div><dt>Робочий простір</dt><dd>{user.workspace_name||'Мій склад'}</dd></div>
        </dl>
        <p className="r123-note"><ShieldCheck size={16}/>Ім’я, роль і доступи до робочого простору змінюються через керування командою, якщо вам призначено відповідні права.</p>
      </section>

      <section className="r123-panel" aria-labelledby="r123-workspace-heading">
        <div className="r123-panel-heading">
          <span className="r123-heading-icon"><Warehouse size={19}/></span>
          <div><h2 id="r123-workspace-heading">Мій робочий простір</h2><p>Поточні можливості системи</p></div>
        </div>
        <State error={error} loading={loading}/>
        <dl className="r123-detail-list">
          <div><dt>Валюта обліку</dt><dd>Гривня (UAH)</dd></div>
          <div><dt>Зберігання фотографій</dt><dd className="r123-feature">{loading?'Перевірка…':error?'Стан невідомий':data?.photos_enabled?<><Check size={15}/>Увімкнено</>:'Не налаштовано'}</dd></div>
          <div><dt>Тип складу</dt><dd>Незалежний облік</dd></div>
          <div><dt>Доступ до операцій</dt><dd>{user.role==='DIRECTOR'?'Повний доступ':permissionCount+' дозволів'}</dd></div>
        </dl>
        <div className="r123-workspace-foot">
          <p>Ви працюєте з даними свого робочого простору. Доступні дії визначаються вашою роллю.</p>
          <button type="button" className="r123-refresh" onClick={reload} disabled={loading}>Оновити стан</button>
        </div>
      </section>
    </div>

    <section className="r123-panel r123-access" aria-labelledby="r123-access-heading">
      <div className="r123-panel-heading">
        <span className="r123-heading-icon"><ClipboardList size={19}/></span>
        <div><h2 id="r123-access-heading">Доступні інструменти</h2><p>Швидкий перехід до розділів відповідно до ваших дозволів</p></div>
      </div>
      {sections.length>0?<div className="r123-shortcuts">
        {sections.map(item=><Link key={item.path} to={item.path} className="r123-shortcut">
          <span className="r123-shortcut-icon"><item.icon size={19}/></span>
          <span><strong>{item.label}</strong><small>{item.description}</small></span>
          <ArrowUpRight size={16} className="r123-shortcut-arrow"/>
        </Link>)}
      </div>:<p className="r123-no-access">Права на робочі розділи ще не призначено. Зверніться до директора робочого простору.</p>}
    </section>

    <ChangeOwnPassword/>
    <SessionExit/>
  </div>;
}
