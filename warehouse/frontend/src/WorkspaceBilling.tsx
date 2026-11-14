import {useState} from 'react';
import {api,type Row} from './api';
import {State,useLoad} from './shared';
import './workspace-billing.css';

const labels:Record<string,string>={FREE:'Безкоштовний режим',TRIAL:'Тестовий період',ACTIVE:'Активна підписка',GRACE:'Пільговий період',EXPIRED:'Підписка завершена'};
const date=(value:string|null)=>value?new Date(value).toLocaleString('uk-UA'):'—';
export default function WorkspaceBilling(){
 const {data,error,loading,reload}=useLoad(()=>api('/billing/entitlements'),[]);
 const [plan,setPlan]=useState('standard'),[pack,setPack]=useState('pack_1'),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[quote,setQuote]=useState<Row|null>(null);
 async function trial(){if(busy)return;setBusy(true);setNotice('');try{await api('/billing/trial','POST',{plan});reload();}catch(e){setNotice((e as Error).message);}finally{setBusy(false);}}
 async function calculate(){setBusy(true);setNotice('');try{setQuote(await api('/billing/quote','POST',{pack}));}catch(e){setNotice((e as Error).message);}finally{setBusy(false);}}
 return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата">
  <h2>Підписка та оплата</h2><State loading={loading} error={error}/>
  {data&&<><p className="notice">Ізольований пілот. Реальна оплата та автоматичні списання недоступні.</p>
   <h3>{data.plan==='premium'?'Premium':data.plan==='standard'?'Standard':'CarPot Free'} · {labels[data.status]||data.status}</h3>
   <p>Доступ до {date(data.period_end)}{data.status==='GRACE'&&` · Пільговий строк до ${date(data.cutoff)}`}</p>
   <div className="entitlement-meters"><strong>Автомобілі {data.usage.vehicles}/{data.vehicle_capacity}</strong>{data.usage.employees!=null&&<strong>Працівники {data.usage.employees}/{data.employee_seats}</strong>}</div>
   {(data.over_limit.vehicles||data.over_limit.employees)&&<p role="status">Ліміт досягнуто або перевищено. Дані збережено; нові місця та працівники потребують розширення тарифу.</p>}
   <p>Гараж — постійна місткість. Щомісячне поновлення не додає нових місць. Архівування звільняє місце лише після продажу або документованого виведення залишків і зняття резервів.</p>
   {!data.paid&&<p>Доступні перегляд, пошук, історія, експорт і безпечне завершення раніше створених зобов’язань. Для нових операцій відновіть доступ.</p>}
   {data.can_manage?<><div className="entitlement-plans">{Object.entries(data.plans as Row).map(([key,p])=><article key={key}><h3>{key==='standard'?'Standard':'Premium'}</h3><strong>{(p.amount_minor/100).toLocaleString('uk-UA')} грн/місяць</strong><p>{p.vehicle_capacity} автомобілів · власник + {p.employee_seats} працівників</p></article>)}</div>
    <label>Тариф тестового періоду<select value={plan} onChange={e=>setPlan(e.target.value)}><option value="standard">Standard</option><option value="premium">Premium</option></select></label>
    <button className="primary" disabled={busy||(data.paid&&data.status!=='TRIAL')||(data.trial_used&&data.status!=='TRIAL')} onClick={trial}>{data.status==='TRIAL'?'Змінити тариф trial без зміни строку':'Активувати CarPot безкоштовно на 10 днів'}</button>
    <p>Один trial на клієнта/компанію, без картки й автоматичного продовження.</p>
    <h3>Розширити гараж</h3><label>Щомісячний пакет<select value={pack} onChange={e=>{setPack(e.target.value);setQuote(null);}}>{Object.entries(data.packs as Row).map(([key,p])=><option key={key} value={key}>+{p.capacity} · {p.amount_minor/100} грн/місяць</option>)}</select></label>
    <button disabled={busy||!data.paid||data.status==='GRACE'} onClick={calculate}>Розрахувати за залишок періоду</button>
    {quote&&<p role="status">До сплати {(quote.amount_minor/100).toLocaleString('uk-UA')} грн · до {date(quote.effective_until)}. Купівля стане доступною після підключення оплати.</p>}
    <button disabled>Оплата LiqPay недоступна</button>
   </>:<p>Підпискою та оплатою керує власник робочого простору.</p>}
   {notice&&<p role="alert">{notice}</p>}
  </>}
 </section>;
}
