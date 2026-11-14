import {useRef,useState,useEffect} from 'react';
import {Gift,Users,CheckCircle2,Wallet,Copy,Link2,Clock3,ShieldCheck,ArrowUpRight} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api,type Row} from './api';
import {State,useLoad} from './shared';
import {OperationProgress} from './DismantlingBulk';
import {referralCode,referralPath} from './referralCabinet';
import './workspace-billing.css';
import './workspace-referrals.css';

const amount=(v:number)=> (v/100).toLocaleString('uk-UA',{style:'currency',currency:'UAH'});
const day=(v:string)=>new Date(v).toLocaleDateString('uk-UA');

export default function WorkspaceReferrals({invite}:{invite:string|null}){
 const {data,error,loading,reload}=useLoad(()=>api('/billing/referrals'),[]);
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState(''),[failure,setFailure]=useState(''),[code,setCode]=useState(invite||''),[expanded,setExpanded]=useState(false);
 const guard=useRef(false),live=useRef(true);
 useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
 useEffect(()=>{if(invite)setCode(invite)},[invite]);
 async function work(label:string,fn:()=>Promise<unknown>){if(guard.current)return;guard.current=true;setBusy(label);setFailure('');setNotice('');try{await fn();if(live.current)reload()}catch(e){if(live.current)setFailure((e as Error).message)}finally{guard.current=false;if(live.current)setBusy('')}}
 if(loading&&!data)return <section className="r123-panel" aria-label="Реферальна програма"><OperationProgress label="Завантажуємо реферальний кабінет…"/></section>;
 if(error)return <section className="r123-panel" aria-label="Реферальна програма"><State error={error} loading={false}/><button onClick={reload}>Повторити</button></section>;
 if(!data?.enabled)return <section className="r123-panel" aria-label="Реферальна програма"><p>Реферальна програма ще недоступна.</p><Link to="/settings?section=payments">До оплат</Link></section>;
 const valid=referralCode(code),url=data.code?location.origin+referralPath(data.code):'',policy=data.policy,rewards=(data.rewards||[]) as Row[];
 return <section className="referral-cabinet bill-premium" aria-label="Реферальна програма">
  <div className="bill-section-heading"><h2>Запрошуйте партнерів</h2><span className="bill-environment"><ShieldCheck size={15}/>Тестовий режим</span></div>
  <p className="bill-sandbox-note">Тестові винагороди не є реальними коштами. Оплата ними та виведення недоступні.</p>
  {busy&&<OperationProgress label={busy}/>}
  {failure&&<p role="alert" className="error">{failure}</p>}{notice&&<p role="status" className="ref-notice"><CheckCircle2 size={18}/>{notice}</p>}
  {!data.bound?<div className="ref-card"><h3>Підключіть компанію</h3><p>Для участі потрібен фінансовий кабінет CarPot.</p><button className="primary" disabled={!!busy} onClick={()=>work('Підключаємо компанію…',()=>api('/billing/bind','POST'))}>Підключити компанію</button></div>:<>
  <div className="ref-hero ref-card"><div className="ref-hero-top"><span className="bill-icon"><Gift size={26}/></span><div><small>ВАША ВИНАГОРОДА</small><strong>{policy.rate_bps/100}%</strong></div></div><h3>Від першої оплаченої підписки</h3><p>Одна винагорода за нового клієнта. Підтвердження через {policy.hold_days} днів, за умови відсутності повернення.</p><div className="ref-examples"><span>Standard <b>{amount(100000*policy.rate_bps/10000)}</b></span><span>Premium <b>{amount(450000*policy.rate_bps/10000)}</b></span></div></div>
  {invite&&data.can_bind&&<div className="ref-card ref-invite"><h3>Ви отримали запрошення</h3><p>Підтвердьте код до першої оплати. Після прив'язки змінити його неможливо.</p><button className="primary" disabled={!!busy||!valid} onClick={()=>work('Підтверджуємо запрошення…',async()=>{await api('/billing/referrals/bind','POST',{code:valid});if(live.current)setNotice('Запрошення підтверджено.');})}>Підтвердити запрошення</button></div>}
  <div className="ref-metrics"><article className="ref-card"><Users size={21}/><small>Запрошено компаній</small><strong>{data.invited}</strong></article><article className="ref-card"><CheckCircle2 size={21}/><small>Перші оплати</small><strong>{data.converted}</strong></article><article className="ref-card"><Clock3 size={21}/><small>Очікує підтвердження</small><strong>{amount(data.balances.pending_minor)}</strong></article><article className="ref-card"><Wallet size={21}/><small>Доступно · тестові</small><strong>{amount(data.balances.available_minor)}</strong></article></div>
  <div className="ref-card ref-link"><div className="bill-section-heading"><h3>Ваше запрошення</h3><Link2 size={20}/></div>{url?<><label>Персональне посилання<input readOnly value={url} onFocus={e=>e.target.select()}/></label><button className="primary" disabled={!!busy} onClick={async()=>{try{await navigator.clipboard.writeText(url);setNotice('Посилання скопійовано.')}catch{setNotice('Виділіть і скопіюйте посилання вручну.')}}}><Copy size={17}/>Скопіювати посилання</button><small>Код: {data.code}</small></>:<><p>Створіть персональне посилання та надішліть його партнеру.</p><button className="primary" disabled={!!busy} onClick={()=>work('Створюємо посилання…',()=>api('/billing/referrals/code','POST'))}>Отримати посилання <ArrowUpRight size={17}/></button></>}</div>
  {!invite&&data.can_bind&&<div className="ref-card"><h3>Маєте код запрошення?</h3><p>Прив'язка можлива лише до першої підтвердженої оплати.</p><label>Код запрошення<input value={code} maxLength={16} onChange={e=>setCode(e.target.value.toUpperCase())}/></label><button disabled={!valid||!!busy} onClick={()=>work('Підтверджуємо запрошення…',async()=>{await api('/billing/referrals/bind','POST',{code:valid});if(live.current)setNotice('Запрошення підтверджено.');})}>Підтвердити код</button></div>}
  {data.attributed&&<p className="ref-notice"><CheckCircle2 size={17}/>Запрошення вже прив'язане до вашої компанії.</p>}
  {invite&&!data.can_bind&&!data.attributed&&<p className="bill-muted">Код не можна застосувати після першої підтвердженої оплати.</p>}
  <div className="bill-section-heading"><h3>Історія винагород</h3>{rewards.length>3&&<button className="bill-list-toggle" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>{expanded?'Згорнути':'Показати всі ('+rewards.length+')'}</button>}</div>
  {rewards.length?<div className="ref-history">{(expanded?rewards:rewards.slice(0,3)).map(r=><article className="ref-card" key={r.id}><div><strong>{amount(r.amount_minor-r.reversed_minor)}</strong><span>{r.state==='available'?'Доступно':r.state==='reversed'?'Сторновано':'Очікує підтвердження'}</span></div><small>Нараховано {day(r.created_at)} · {r.rate_bps/100}%</small>{r.state==='pending'&&<small>Не раніше {day(r.available_after)} · після перевірки</small>}{r.reversed_minor>0&&<small>Скориговано: {amount(r.reversed_minor)}</small>}</article>)}</div>:<div className="ref-card ref-empty"><Gift size={24}/><strong>Винагород ще немає</strong><p>Поділіться посиланням. Перша підтверджена оплата партнера з'явиться тут.</p></div>}
  <p className="bill-muted">Винагорода зберігається у фінансовому журналі. Повернення оплати коригує її суму. Показано до 100 останніх винагород.</p>
  </>}
 </section>
}
