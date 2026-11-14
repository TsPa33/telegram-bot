import {useState,useRef,useEffect,useContext} from 'react';
import {TeamIdentity} from './permissions';
import {OperationProgress} from './DismantlingBulk';
import {billingScope,restoreBillingCommand,validCheckoutForm,billingOrder,paymentMessage,type BillingCommand} from './billingCabinet';
import {api,type Row} from './api';
import {State,useLoad} from './shared';
import './workspace-billing.css';

const labels:Record<string,string>={FREE:'Безкоштовний режим',TRIAL:'Тестовий період',ACTIVE:'Активна підписка',GRACE:'Пільговий період',EXPIRED:'Підписка завершена'};
const date=(value:string|null)=>value?new Date(value).toLocaleString('uk-UA'):'—';
function PilotBilling(){
 const {data,error,loading,reload}=useLoad(()=>api('/billing/entitlements'),[]);
 const [plan,setPlan]=useState('standard'),[pack,setPack]=useState('pack_1'),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[quote,setQuote]=useState<Row|null>(null);
 async function trial(){if(busy)return;setBusy(true);setNotice('');try{await api('/billing/trial','POST',{plan});reload();}catch(e){setNotice(e instanceof TypeError?'Зв’язок перервано. Відновіть запит оплати або перевірте стан.':(e as Error).message);}finally{setBusy(false);}}
 async function calculate(){setBusy(true);setNotice('');try{setQuote(await api('/billing/quote','POST',{pack}));}catch(e){setNotice(e instanceof TypeError?'Зв’язок перервано. Відновіть запит оплати або перевірте стан.':(e as Error).message);}finally{setBusy(false);}}
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
  {data.reviews?.length>0&&<section aria-label="Оплати на перевірці"><h3>Оплати на перевірці</h3><p>Ми перевіряємо ці операції. Для уточнення зверніться до підтримки CarPot.</p><ul>{data.reviews.map((r:Row)=><li key={r.id}>{date(r.created_at)} · Рахунок {r.invoice_id.slice(0,8)}</li>)}</ul></section>}
  </>}
 </section>;
}

const amount=(minor:number)=>((minor||0)/100).toLocaleString('uk-UA',{style:'currency',currency:'UAH'});
const skuName=(sku:string)=>sku==='warehouse.standard'?'Standard':sku==='warehouse.premium'?'Premium':sku==='warehouse.slots.1'?'+1 автомобіль':sku==='warehouse.slots.5'?'+5 автомобілів':sku==='warehouse.slots.10'?'+10 автомобілів':'Сервіс CarPot';
const invoiceStatus:Record<string,string>={draft:'Чернетка',open:'Очікує оплати',paid:'Оплачено',void:'Скасовано'};

export default function WorkspaceBilling(){
 const cabinet=useLoad(()=>api('/billing/cabinet'),[]);
 if(cabinet.loading&&!cabinet.data)return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><OperationProgress label="Завантажуємо підписку…"/></section>;
 if(cabinet.error)return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><State error={cabinet.error} loading={false}/><button onClick={cabinet.reload}>Перевірити доступність оплати</button></section>;
 return cabinet.data?.enabled?<BillingCabinet data={cabinet.data} reload={cabinet.reload}/>:<PilotBilling/>;
}

function BillingCabinet({data,reload}:{data:Row;reload:()=>void}){
 const identity=useContext(TeamIdentity),scope=data.workspace_scope&&identity?.id?billingScope(identity.id,data.workspace_scope):'';
 const storage='warehouse-billing-command:'+scope,orderStorage='warehouse-billing-order:'+scope;
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState(''),[pending,setPending]=useState<BillingCommand|null>(null),[invoice,setInvoice]=useState<Row|null>(null),[payment,setPayment]=useState<Row|null>(null),[details,setDetails]=useState<Row|null>(null),[order,setOrder]=useState<string|null>(null);
 const [trialPlan,setTrialPlan]=useState('standard');
 const running=useRef(false),mounted=useRef(true),liveScope=useRef(scope);liveScope.current=scope;
 useEffect(()=>{mounted.current=true;setPending(null);setInvoice(null);setPayment(null);setDetails(null);setNotice('');setOrder(null);
  if(scope)try{setPending(restoreBillingCommand(sessionStorage.getItem(storage),scope));setOrder(billingOrder(new URLSearchParams(location.search).get('billing_order'))||billingOrder(sessionStorage.getItem(orderStorage)));}catch(e){setNotice(e instanceof TypeError?'Зв’язок перервано. Відновіть запит оплати або перевірте стан.':(e as Error).message);}
  return()=>{mounted.current=false;};
 },[scope]);
 const current=(captured:string)=>mounted.current&&liveScope.current===captured;
 async function work(label:string,fn:(captured:string)=>Promise<unknown>){if(running.current||!scope)return;const captured=scope;running.current=true;setBusy(label);setNotice('');try{await fn(captured);}catch(e){if(current(captured))setNotice(e instanceof TypeError?'Зв’язок перервано. Відновіть запит оплати або перевірте стан.':(e as Error).message);}finally{running.current=false;if(current(captured))setBusy('');}}
 function save(command:BillingCommand){sessionStorage.setItem(storage,JSON.stringify(command));setPending(command);}
 function clear(){sessionStorage.removeItem(storage);setPending(null);}
 async function execute(command:BillingCommand,captured:string){
  save(command);
  if(command.kind==='invoice'){
   const value=await api('/billing/invoices','POST',{sku:command.sku,request_key:command.request_key});if(!current(captured))return;
   setInvoice(value);clear();reload();return;
  }
  const value=await api('/billing/checkout','POST',{invoice_id:command.invoice_id});if(!current(captured))return;
  const form=validCheckoutForm(value.form),id=billingOrder(value.order_id);if(!id)throw Error('Замовлення оплати не підтверджено.');
  sessionStorage.setItem(orderStorage,id);setOrder(id);clear();
  // Hosted POST only. No card fields or secret provider key in CarPot.
  const element=document.createElement('form');element.action=form.url;element.method='POST';
  for(const [name,value] of Object.entries({data:form.data,signature:form.signature})){const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;element.appendChild(input);}
  document.body.appendChild(element);element.submit();
 }
 function purchase(sku:string){return work('Готуємо оплату…',captured=>execute({kind:'invoice',scope,sku,request_key:crypto.randomUUID()},captured));}
 async function verify(id:string,refresh=false){const captured=scope;const value=await api('/billing/orders/'+id+(refresh?'/refresh':''),refresh?'POST':'GET');if(!current(captured))return;
  if(value.status==='paid'){
   const rights=await api('/billing/sync','POST');if(!current(captured))return;
   value.activated=rights.paid===true&&(!value.effective_from||new Date(value.effective_from).getTime()<=Date.now());
   if(value.activated||value.effective_from&&new Date(value.effective_from).getTime()>Date.now()){sessionStorage.removeItem(orderStorage);reload();}
  }
  setPayment(value);return value;
 }
 useEffect(()=>{if(!order||!scope)return;let alive=true,timer:ReturnType<typeof setTimeout>|undefined,attempt=0;const captured=scope;
  async function poll(){if(!alive||!current(captured))return;try{const result=await verify(order!);if(result&&(result.status==='refunded'||result.status==='paid'&&(result.activated||new Date(result.effective_from).getTime()>Date.now())))return;}catch(e){if(alive&&current(captured))setNotice(e instanceof TypeError?'Зв’язок перервано. Відновіть запит оплати або перевірте стан.':(e as Error).message);}if(alive&&current(captured)&&++attempt<20)timer=setTimeout(poll,Math.min(5000,1000+attempt*500));}
  void poll();return()=>{alive=false;if(timer)clearTimeout(timer);};
 },[order,scope]);
 if(!data.can_manage)return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><h2>Підписка та оплата</h2><p>Підпискою та оплатою керує власник робочого простору.</p></section>;
 const e=data.entitlements,plans=(data.plans||[]) as Row[],invoices=(data.invoices||[]) as Row[],payments=(data.payments||[]) as Row[];
 return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><h2>Підписка та оплата</h2>
  {data.environment==='sandbox'&&<p className="notice">Тестове середовище. Ця оплата не активує реальні послуги.</p>}
  {busy&&<OperationProgress label={busy}/>}{notice&&<p role="alert">{notice}</p>}
  {!data.bound?<><p>Підключіть компанію до єдиного фінансового кабінету CarPot.</p><button className="primary" disabled={!!busy} onClick={()=>work('Підключаємо компанію…',async captured=>{await api('/billing/bind','POST');if(current(captured))reload();})}>Підключити оплату CarPot</button></>:<>
  {e&&<><h3>{e.plan==='premium'?'Premium':e.plan==='standard'?'Standard':'CarPot Free'} · {labels[e.status]||e.status}</h3><p>Доступ до {date(e.period_end)}{e.status==='GRACE'&&(' · Пільговий строк до '+date(e.cutoff))}</p><div className="entitlement-meters"><strong>Автомобілі {e.usage.vehicles}/{e.vehicle_capacity}</strong><strong>Працівники {e.usage.employees}/{e.employee_seats}</strong></div>
  {(e.over_limit.vehicles||e.over_limit.employees)&&<p role="status">Ліміт досягнуто. Дані збережено; для нових операцій розширте тариф.</p>}</>}
  <p>Автопродовження: {data.subscription?.auto_renew?'увімкнено':'вимкнено'}. {data.subscription?.next_payment_at&&('Наступний платіж: '+date(data.subscription.next_payment_at))}</p>
  {data.subscription?.auto_renew&&<button disabled={!!busy} onClick={()=>work('Скасовуємо автопродовження…',async()=>{await api('/billing/cancel-renewal','POST');reload();})}>Скасувати автопродовження</button>}
  {data.subscription?.recurring&&data.subscription.recurring.state!=='canceled'&&<><button disabled={!!busy||data.subscription.recurring.state==='cancel_requested'} onClick={()=>work('Надсилаємо запит скасування…',async captured=>{const result=await api('/billing/cancel-renewal','POST');if(current(captured)){setNotice(result.provider_confirmed?'Автопродовження скасовано. Оплачений доступ збережено.':'Запит скасування прийнято. Очікуємо підтвердження LiqPay; оплачений доступ збережено.');reload();}})}>Скасувати автопродовження</button>{data.subscription.recurring.state==='cancel_requested'&&<p role="status">Скасування очікує підтвердження LiqPay.</p>}</>}
  {pending&&<div className="notice" role="status"><p>Попередній запит збережено. Відновіть його перед створенням нової оплати.</p><button disabled={!!busy} onClick={()=>work('Відновлюємо оплату…',captured=>execute(pending,captured))}>Відновити запит оплати</button></div>}
  <div className="entitlement-plans">{['warehouse.standard','warehouse.premium'].map(sku=>{const plan=plans.find(p=>p.sku===sku);return plan?<article key={sku}><h3>{skuName(sku)}</h3><strong>{amount(plan.amount_minor)}/місяць</strong><p>{plan.vehicle_capacity} автомобілів · власник + {plan.employees} працівників</p><button disabled={!!busy||!!pending} onClick={()=>purchase(sku)}>Обрати {skuName(sku)}</button></article>:null;})}</div>
  {e&&!e.trial_used&&!e.paid&&<div className="billing-trial"><label>Тариф тестового періоду<select value={trialPlan} onChange={event=>setTrialPlan(event.target.value)}><option value="standard">Standard</option><option value="premium">Premium</option></select></label><button disabled={!!busy||!!pending} onClick={()=>work('Активуємо тестовий період…',async()=>{await api('/billing/trial','POST',{plan:trialPlan});reload();})}>Активувати CarPot безкоштовно на 10 днів</button><p>Один trial на компанію. Без картки та автоматичних списань.</p></div>}
  <h3>Розширити гараж</h3><div className="billing-addon-list">{plans.filter(p=>p.kind==='addon').map(p=><button key={p.sku} disabled={!!busy||!!pending||!e?.paid||e.status==='GRACE'} onClick={()=>purchase(p.sku)}>{skuName(p.sku)} · {amount(p.amount_minor)}/місяць</button>)}</div><p>Пакет діє до кінця поточного оплаченого періоду. Остаточну суму за залишок періоду показано в рахунку.</p>
  {invoice&&<section className="billing-checkout-summary" aria-label="Підтвердження оплати"><h3>{skuName(invoice.lines?.[0]?.sku)}</h3><p>{date(invoice.effective_at||invoice.starts_at)} — {date(invoice.ends_at)}</p><strong>До сплати: {amount(invoice.amount_minor)}</strong><p>Платіжні реквізити вводяться лише на офіційній сторінці LiqPay.</p><button className="primary" disabled={!!busy||!!pending||!data.checkout_available} onClick={()=>work('Готуємо оплату…',captured=>execute({kind:'checkout',scope,invoice_id:invoice.id},captured))}>Оплатити через LiqPay</button>{!data.checkout_available&&<p role="status">Оплата ще недоступна для цього середовища.</p>}</section>}
  {order&&<section className="billing-payment-state" aria-label="Стан оплати"><h3>Стан оплати</h3><p role="status">{paymentMessage(payment)||'Очікуємо підтвердження LiqPay'}</p><button disabled={!!busy} onClick={()=>work('Перевіряємо оплату…',()=>verify(order,true))}>Перевірити оплату</button></section>}
  <h3>Рахунки</h3>{invoices.length?<div className="billing-history"><table><thead><tr><th>Період</th><th>Сума</th><th>Статус</th><th>Дії</th></tr></thead><tbody>{invoices.map(i=><tr key={i.id}><td>{date(i.starts_at)} — {date(i.ends_at)}</td><td>{amount(i.amount_minor)}</td><td>{invoiceStatus[i.status]||'Перевірка'}</td><td><button disabled={!!busy} onClick={()=>work('Завантажуємо рахунок…',async captured=>{const value=await api('/billing/invoices/'+i.id);if(current(captured))setDetails(value);})}>Переглянути рахунок</button>{i.status==='open'&&<><button disabled={!!busy||!!pending} onClick={()=>work('Завантажуємо рахунок…',async captured=>{const value=await api('/billing/invoices/'+i.id);if(current(captured))setInvoice(value);})}>Продовжити оплату</button><button disabled={!!busy} onClick={()=>work('Скасовуємо рахунок…',async()=>{await api('/billing/invoices/'+i.id+'/void','POST');reload();if(invoice?.id===i.id)setInvoice(null);})}>Скасувати рахунок</button></>}</td></tr>)}</tbody></table></div>:<p>Створених рахунків ще немає.</p>}
  {details&&<aside className="billing-invoice-details" aria-label="Деталі рахунку"><h3>Рахунок {details.id.slice(0,8)}</h3>{details.lines?.map((line:Row,index:number)=><p key={index}>{skuName(line.sku)} · {amount(line.amount_minor)}</p>)}<p>{date(details.starts_at)} — {date(details.ends_at)}</p><strong>{amount(details.amount_minor)}</strong><p>{invoiceStatus[details.status]}</p><button onClick={()=>setDetails(null)}>Закрити деталі</button></aside>}
  {data.wallet?.test_only&&<section aria-label="Тестовий баланс"><h3>Тестовий баланс</h3><p>Тестові записи. Реальні поповнення, перекази та виведення недоступні.</p><div className="entitlement-meters">{Object.entries({cash:'Основний баланс',promo:'Промоційні бонуси',referral:'Реферальні кошти'}).map(([key,label])=><article key={key}><strong>{label}: {amount(data.wallet.balances[key].available_minor)}</strong>{data.wallet.balances[key].reserved_minor>0&&<p>Зарезервовано: {amount(data.wallet.balances[key].reserved_minor)}</p>}{data.wallet.balances[key].pending_minor>0&&<p>Очікує: {amount(data.wallet.balances[key].pending_minor)}</p>}</article>)}</div></section>}
  {data.referrals?.rewards?.length>0&&<section aria-label="Реферальні винагороди"><h3>Реферальні винагороди · тестовий режим</h3><ul>{data.referrals.rewards.map((r:Row)=><li key={r.id}>{amount(r.amount_minor-r.reversed_minor)} · {r.state==='available'?'Доступно':r.state==='reversed'?'Сторновано':'Очікує підтвердження'}</li>)}</ul></section>}
  <h3>Історія оплат</h3>{payments.length?<ul className="billing-payment-history">{payments.map(p=><li key={p.id}><time>{date(p.created_at)}</time><strong>{amount(p.amount_minor)}</strong><span>{p.refunded_minor>=p.amount_minor?'Повернено':p.refunded_minor>0?'Частково повернено':'Оплачено'}</span><span>{skuName(p.sku)} · Рахунок {p.invoice_id.slice(0,8)}</span>{p.refunded_minor>0&&<span>Повернено {amount(p.refunded_minor)}</span>}{p.order_id&&<small>{p.order_id}</small>}</li>)}</ul>:<p>Підтверджених оплат ще немає.</p>}
  {data.reviews?.length>0&&<section aria-label="Оплати на перевірці"><h3>Оплати на перевірці</h3><p>Ми перевіряємо ці операції. Для уточнення зверніться до підтримки CarPot.</p><ul>{data.reviews.map((r:Row)=><li key={r.id}>{date(r.created_at)} · Рахунок {r.invoice_id.slice(0,8)}</li>)}</ul></section>}
  </>}
 </section>;
}
