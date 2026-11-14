import {useState,useRef,useEffect,useContext,type CSSProperties} from 'react';
import {CarFront,Users,Layers,Crown,Check,CheckCircle2,CalendarDays,ReceiptText,FileText,ChevronRight,ShieldCheck,AlertTriangle,Wallet,Plus,Info} from 'lucide-react';
import {capacityBreakdown,paidCoverage} from './billingCabinet';
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
const shortDate=(value:string|null)=>value?new Date(value).toLocaleDateString('uk-UA'):'—';
function CapacityMeter({label,used,limit,staff=false}:{label:string;used:number;limit:number;staff?:boolean}){
 const c=capacityBreakdown(used,limit),Icon=staff?Users:CarFront;
 return <div className="bill-meter">
  <div className="bill-meter-title"><span className="bill-icon"><Icon size={20}/></span><strong>{label} <b>{c.used}/{c.limit}</b></strong></div>
  <div className="bill-meter-track" role="img" aria-label={label+': зайнято '+c.used+', місткість '+c.limit+', вільно '+c.free+', понад ліміт '+c.excess}>
   <span className="bill-meter-used" style={{width:c.usedPercent+'%'}}/><span className="bill-meter-excess" style={{width:c.excessPercent+'%'}}/>
  </div>
  <div className="bill-meter-stats"><span><b>{c.used}</b>Зайнято</span><span><b>{c.free}</b>Вільно</span>{!staff&&<span className={c.excess?'bill-over':''}><b>{c.excess}</b>Понад ліміт</span>}{staff&&c.excess>0&&<span className="bill-over"><b>{c.excess}</b>Понад ліміт</span>}</div>
 </div>;
}
function PaymentResult({payment,order,product,environment,busy,onRefresh,onClose,onDetails}:{payment:Row|null;order:string;product:string;environment:string;busy:boolean;onRefresh:()=>void;onClose:()=>void;onDetails:()=>void}){
 const paid=payment?.status==='paid',scheduled=paid&&payment?.effective_from&&new Date(payment.effective_from).getTime()>Date.now(),done=paid&&(payment?.activated===true||scheduled);
 return <section className={'billing-payment-state bill-result'+(paid?' bill-result--success':'')} aria-label="Стан оплати" key={order}>
  {paid?<div className="bill-success-art" aria-hidden="true"><span className="bill-success-ring"/><span className="bill-success-ring second"/><span className="bill-success-check"><Check size={39} strokeWidth={3}/></span>{Array.from({length:8},(_,i)=><i key={i} style={{'--angle':i*45+'deg','--delay':i*35+'ms'} as CSSProperties}/>)}</div>:<span className="bill-icon bill-result-icon"><Wallet size={25}/></span>}
  <div className="bill-result-copy"><h3>{paid?'Оплату успішно підтверджено':'Стан оплати'}</h3><p role="status">{paymentMessage(payment)||'Очікуємо підтвердження LiqPay'}</p>
   {paid&&<><span className="bill-result-product">{product}</span><strong className="bill-result-amount">{amount(payment.amount_minor)}</strong><span className="bill-muted">{shortDate(payment.effective_from)} — {shortDate(payment.effective_until)}</span></>}
   {environment==='sandbox'&&<small className="bill-muted">Тестова оплата · без реального списання</small>}
  </div>
  {!paid&&(!payment||payment.status==='pending')&&<OperationProgress label="Очікуємо підтвердження LiqPay"/>}
  <div className="bill-result-actions">{done?<button className="primary" onClick={onClose}>Повернутися до оплат</button>:<button className="primary" disabled={busy} onClick={onRefresh}>Перевірити оплату</button>}{paid&&payment.invoice_id&&<button disabled={busy} onClick={onDetails}>Переглянути рахунок</button>}</div>
 </section>;
}

export default function WorkspaceBilling(){
 const cabinet=useLoad(async()=>{const first=await api('/billing/cabinet');if(first.enabled&&first.can_manage&&(!first.bound||first.referral_state==='pending')){await api('/billing/bind','POST');return api('/billing/cabinet');}return first;},[]);
 if(cabinet.loading&&!cabinet.data)return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><OperationProgress label="Завантажуємо підписку…"/></section>;
 if(cabinet.error)return <section className="r123-panel workspace-billing" aria-label="Підписка та оплата"><State error={cabinet.error} loading={false}/><button onClick={cabinet.reload}>Перевірити доступність оплати</button></section>;
 return cabinet.data?.enabled?<BillingCabinet data={cabinet.data} reload={cabinet.reload}/>:<PilotBilling/>;
}

function BillingCabinet({data,reload}:{data:Row;reload:()=>void}){
 const identity=useContext(TeamIdentity),scope=data.workspace_scope&&identity?.id?billingScope(identity.id,data.workspace_scope):'';
 const storage='warehouse-billing-command:'+scope,orderStorage='warehouse-billing-order:'+scope;
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState(''),[pending,setPending]=useState<BillingCommand|null>(null),[invoice,setInvoice]=useState<Row|null>(null),[payment,setPayment]=useState<Row|null>(null),[details,setDetails]=useState<Row|null>(null),[order,setOrder]=useState<string|null>(null);
 const [trialPlan,setTrialPlan]=useState('standard');
 const [allInvoices,setAllInvoices]=useState(false),[allPayments,setAllPayments]=useState(false);
 const checkoutRef=useRef<HTMLElement>(null),resultRef=useRef<HTMLDivElement>(null),detailsRef=useRef<HTMLElement>(null);
 const scrollBehavior=()=>matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';
 useEffect(()=>{if(invoice?.id)checkoutRef.current?.scrollIntoView({block:'nearest',behavior:scrollBehavior()});},[invoice?.id]);
 useEffect(()=>{if(details?.id)detailsRef.current?.scrollIntoView({block:'start',behavior:scrollBehavior()});},[details?.id]);
 useEffect(()=>{if(order)resultRef.current?.scrollIntoView({block:'start',behavior:scrollBehavior()});},[order,payment?.status]);
 const running=useRef(false),mounted=useRef(true),liveScope=useRef(scope);liveScope.current=scope;
 useEffect(()=>{mounted.current=true;setPending(null);setInvoice(null);setPayment(null);setDetails(null);setNotice('');setOrder(null);setAllInvoices(false);setAllPayments(false);
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
 const coverage=paidCoverage(e?.period_end,e?.status,invoices,payments);
 const latestInvoices=invoices.slice(0,3),shownInvoices=allInvoices?invoices:invoices.filter(i=>i.status==='open'||latestInvoices.some(x=>x.id===i.id));
 const premiumPlan=plans.find(p=>p.sku==='warehouse.premium'),premiumFree=premiumPlan&&e?Math.max(0,premiumPlan.vehicle_capacity-e.usage.vehicles):0;
 const paidProduct=payments.find(p=>p.invoice_id===payment?.invoice_id)?.sku;
 const activePlan=plans.find(p=>p.sku==='warehouse.'+e?.plan),activeName=e?.plan==='premium'?'Premium':e?.plan==='standard'?'Standard':'CarPot Free';
 const viewInvoice=(id:string)=>work('Завантажуємо рахунок…',async captured=>{const value=await api('/billing/invoices/'+id);if(current(captured)){setDetails(value);}});
 function closeResult(){sessionStorage.removeItem(orderStorage);const url=new URL(location.href);url.searchParams.delete('billing_order');history.replaceState(history.state,'',url);setOrder(null);setPayment(null);setInvoice(null);document.getElementById('billing-overview')?.scrollIntoView({block:'start',behavior:scrollBehavior()});}
 const firstChoice=!e?.paid;
 const planSelection=<section id="billing-plans" className={'bill-plan-selection bill-anchor'+(firstChoice?' bill-first-choice':'')} aria-label="Вибір тарифу">
  <div className="bill-selection-heading"><div><span className="bill-eyebrow">CARPOT WAREHOUSE</span><h3>{firstChoice?'Оберіть свій тариф':'Тарифи та місткість'}</h3><p>{firstChoice?'Почніть роботу зі складом. Оберіть місткість для вашої компанії.':'Керуйте місткістю складу та команди.'}</p></div></div>
  <div className="entitlement-plans bill-plans bill-plan-options">{['warehouse.standard','warehouse.premium'].map(sku=>{const plan=plans.find(p=>p.sku===sku),selected=sku==='warehouse.'+e?.plan,premium=sku.endsWith('premium');return plan?<article key={sku} className={'bill-plan-option '+(premium?'bill-plan-option--premium':'bill-plan-option--standard')+(selected?' bill-plan-current':'')}>
   <div className="bill-plan-head"><span className="bill-icon">{premium?<Crown size={26}/>:<Layers size={26}/>}</span>{selected?<span className="bill-current"><Check size={15}/>Ваш тариф</span>:<span className="bill-plan-label">{premium?'Для масштабування':'Для старту'}</span>}</div>
   <div><h3>{skuName(sku)}</h3><p className="bill-plan-description">{premium?'Для великої авторозбірки та команди':'Для малого та середнього складу'}</p></div>
   <div className="bill-plan-price"><strong>{amount(plan.amount_minor)}</strong><small>/ місяць</small></div>
   <div className="bill-plan-quotas"><div><CarFront size={20}/><strong>{plan.vehicle_capacity}</strong><span>автомобілів</span></div><div><Users size={20}/><strong>{plan.employees}</strong><span>працівників + власник</span></div></div>
   <div className="bill-plan-features"><span><Check size={16}/> {plan.vehicle_capacity} автомобілів у гаражі</span><span><Check size={16}/>Власник + {plan.employees} працівників</span><span><Check size={16}/>Склад та продажі</span></div>
   <button className={selected||!premium?'primary':'bill-premium-cta'} disabled={!!busy||!!pending} onClick={()=>purchase(sku)}>{selected&&e?.paid?'Продовжити '+skuName(sku):'Обрати '+skuName(sku)}<ChevronRight size={18}/></button></article>:null;})}</div>
  {e&&!e.trial_used&&!e.paid&&<div className="billing-trial"><label>Тариф тестового періоду<select value={trialPlan} onChange={event=>setTrialPlan(event.target.value)}><option value="standard">Standard</option><option value="premium">Premium</option></select></label><button disabled={!!busy||!!pending} onClick={()=>work('Активуємо тестовий період…',async()=>{await api('/billing/trial','POST',{plan:trialPlan});reload();})}>Активувати CarPot безкоштовно на 10 днів</button><p>Один trial на компанію. Без картки та автоматичних списань.</p></div>}

 </section>;
 const checkoutPanel=invoice&&<section ref={checkoutRef} className="billing-checkout-summary bill-checkout" aria-label="Підтвердження оплати"><h3>{skuName(invoice.lines?.[0]?.sku)}</h3><p>{date(invoice.effective_at||invoice.starts_at)} — {date(invoice.ends_at)}</p><strong>До сплати: {amount(invoice.amount_minor)}</strong><p>Платіжні реквізити вводяться лише на офіційній сторінці LiqPay.</p><button className="primary" disabled={!!busy||!!pending||!data.checkout_available} onClick={()=>work('Готуємо оплату…',captured=>execute({kind:'checkout',scope,invoice_id:invoice.id},captured))}>Оплатити через LiqPay</button>{!data.checkout_available&&<p role="status">Оплата ще недоступна для цього середовища.</p>}</section>;
 return <section className="r123-panel workspace-billing bill-premium" aria-label="Підписка та оплата"><div className="bill-section-heading"><h2>Підписка та оплата</h2>{data.environment==='sandbox'&&<span className="bill-environment"><ShieldCheck size={15}/>Тестовий режим</span>}</div>
  {data.environment==='sandbox'&&<p className="bill-sandbox-note">Тестове середовище. Ця оплата не активує реальні послуги.</p>}
  {busy&&<OperationProgress label={busy}/>}{notice&&<p role="alert">{notice}</p>}
  {data.referral_state==='invalid'&&<p className="bill-muted" role="status">Запрошення не вдалося розпізнати. Ви можете користуватися CarPot без нього.</p>}
  {!data.bound?<OperationProgress label="Готуємо фінансовий кабінет…"/>:<>
  {order&&<div ref={resultRef} className="bill-result-anchor"><PaymentResult payment={payment} order={order} product={paidProduct?skuName(paidProduct):'Оплата CarPot'} environment={data.environment} busy={!!busy} onRefresh={()=>work('Перевіряємо оплату…',()=>verify(order,true))} onClose={closeResult} onDetails={()=>viewInvoice(payment!.invoice_id)}/></div>}
  {pending&&<div className="notice" role="status"><p>Попередній запит збережено. Відновіть його перед створенням нової оплати.</p><button disabled={!!busy} onClick={()=>work('Відновлюємо оплату…',captured=>execute(pending,captured))}>Відновити запит оплати</button></div>}
  {firstChoice&&<>{planSelection}{checkoutPanel}</>}
  {e&&<div id="billing-overview" className="bill-overview">
   <div className="bill-hero"><div className="bill-hero-top"><span className="bill-icon bill-hero-icon">{e.plan==='premium'?<Crown size={26}/>:<Layers size={26}/>}</span><div><small className="bill-eyebrow">ПОТОЧНИЙ ТАРИФ</small><h3>{activeName}</h3><span className={'bill-plan-status'+(e.status==='ACTIVE'?' active':'')}><span/>{labels[e.status]||e.status}</span></div>{activePlan&&<div className="bill-price"><strong>{amount(activePlan.amount_minor)}</strong><small>на місяць</small></div>}</div>
    <div className="bill-hero-meta bill-periods"><div><span><CalendarDays size={16}/>{e.status==='ACTIVE'?'Поточний період до':e.status==='TRIAL'?'Тестовий період до':'Поточний строк до'}</span><b>{shortDate(e.period_end)}</b></div>{coverage&&<div className="bill-paid-through"><span>{coverage.limited?'Підтверджено щонайменше до':'Оплачено до'}</span><b>{shortDate(coverage.through)}</b></div>}
    {coverage&&coverage.additionalPeriods>0&&<p className="bill-prepaid"><CheckCircle2 size={17}/>Наперед оплачено ще {coverage.additionalPeriods} {coverage.additionalPeriods===1?'період':coverage.additionalPeriods<5?'періоди':'періодів'}. Місткість не накопичується.</p>}
    <div><span>Автопродовження</span><b>{data.subscription?.auto_renew?'Увімкнено':'Вимкнено'}</b></div>{data.subscription?.next_payment_at&&<div><span>Наступний платіж</span><b>{shortDate(data.subscription.next_payment_at)}</b></div>}{e.status==='GRACE'&&<div><span>Пільговий строк до</span><b>{shortDate(e.cutoff)}</b></div>}</div>
   </div>
   <div className="bill-capacity"><div className="bill-section-heading"><h3>Місткість гаража</h3><Info size={17}/></div><CapacityMeter label="Автомобілі" used={e.usage.vehicles} limit={e.vehicle_capacity}/><CapacityMeter label="Працівники" used={e.usage.employees} limit={e.employee_seats} staff/>
    {(e.over_limit.vehicles||e.over_limit.employees)&&<div className="bill-limit-note" role="status"><AlertTriangle size={19}/><div><strong>{capacityBreakdown(e.usage.vehicles,e.vehicle_capacity).excess>0?'Понад ліміт гаража на '+capacityBreakdown(e.usage.vehicles,e.vehicle_capacity).excess+' авто':'Ліміт досягнуто або перевищено'}</strong><p>Дані збережено. {e.plan==='standard'&&premiumPlan&&premiumFree>0?`Premium: ${premiumFree} вільних місць за поточного складу після активації тарифу.`:'Для нових місць оберіть більший тариф або пакет.'}</p></div></div>}
   </div>
   <a className="bill-main-action" href="#billing-plans">Керувати тарифом <ChevronRight size={20}/></a>
   <div className="bill-quick-links"><a href="#billing-history"><ReceiptText size={19}/>Історія оплат<ChevronRight size={16}/></a><a href="#billing-invoices"><FileText size={19}/>Переглянути рахунки<ChevronRight size={16}/></a></div>
  </div>}
  {data.subscription?.auto_renew&&<button disabled={!!busy} onClick={()=>work('Скасовуємо автопродовження…',async()=>{await api('/billing/cancel-renewal','POST');reload();})}>Скасувати автопродовження</button>}
  {data.subscription?.recurring&&data.subscription.recurring.state!=='canceled'&&<><button disabled={!!busy||data.subscription.recurring.state==='cancel_requested'} onClick={()=>work('Надсилаємо запит скасування…',async captured=>{const result=await api('/billing/cancel-renewal','POST');if(current(captured)){setNotice(result.provider_confirmed?'Автопродовження скасовано. Оплачений доступ збережено.':'Запит скасування прийнято. Очікуємо підтвердження LiqPay; оплачений доступ збережено.');reload();}})}>Скасувати автопродовження</button>{data.subscription.recurring.state==='cancel_requested'&&<p role="status">Скасування очікує підтвердження LiqPay.</p>}</>}
  {!firstChoice&&<>{planSelection}{checkoutPanel}</>}
  <h3>Розширити гараж</h3><div className="billing-addon-list bill-addons">{plans.filter(p=>p.kind==='addon').sort((a,b)=>Number(a.sku.split('.').at(-1))-Number(b.sku.split('.').at(-1))).map(p=><button key={p.sku} disabled={!!busy||!!pending||!e?.paid||e.status==='GRACE'} onClick={()=>purchase(p.sku)}><span className="bill-icon"><Plus size={19}/></span><span><strong>{skuName(p.sku)}</strong><small>{amount(p.amount_minor)}/місяць</small></span><ChevronRight size={16}/></button>)}</div><p className="bill-muted">Пакет діє до кінця поточного оплаченого періоду. Остаточну суму за залишок періоду показано в рахунку.</p>
  <div id="billing-invoices" className="bill-section-heading bill-anchor"><h3>Рахунки</h3>{invoices.length>3&&<button className="bill-list-toggle" onClick={()=>setAllInvoices(v=>!v)} aria-expanded={allInvoices}>{allInvoices?'Згорнути':'Усі рахунки ('+invoices.length+')'}</button>}</div>{invoices.length?<div className="bill-invoices">{shownInvoices.map(i=><article key={i.id} className="bill-invoice-card"><div className="bill-invoice-main"><span className="bill-icon"><FileText size={20}/></span><div><strong>{shortDate(i.starts_at)} — {shortDate(i.ends_at)}</strong><small className={i.status==='paid'?'bill-paid-text':''}>{invoiceStatus[i.status]||'Перевірка'}</small></div><b>{amount(i.amount_minor)}</b></div><div className="bill-invoice-actions"><button disabled={!!busy} onClick={()=>viewInvoice(i.id)}>Переглянути рахунок</button>{i.status==='open'&&<><button disabled={!!busy||!!pending} onClick={()=>work('Завантажуємо рахунок…',async captured=>{const value=await api('/billing/invoices/'+i.id);if(current(captured))setInvoice(value);})}>Продовжити оплату</button><button disabled={!!busy} onClick={()=>work('Скасовуємо рахунок…',async()=>{await api('/billing/invoices/'+i.id+'/void','POST');reload();if(invoice?.id===i.id)setInvoice(null);})}>Скасувати рахунок</button></>}</div></article>)}</div>:<p>Створених рахунків ще немає.</p>}
  {details&&<aside ref={detailsRef} className="billing-invoice-details" aria-label="Деталі рахунку"><h3>Рахунок {details.id.slice(0,8)}</h3>{details.lines?.map((line:Row,index:number)=><p key={index}>{skuName(line.sku)} · {amount(line.amount_minor)}</p>)}<p>{date(details.starts_at)} — {date(details.ends_at)}</p><strong>{amount(details.amount_minor)}</strong><p>{invoiceStatus[details.status]}</p><button onClick={()=>setDetails(null)}>Закрити деталі</button></aside>}
  {data.wallet?.test_only&&<section aria-label="Тестовий баланс"><h3>Тестовий баланс</h3><p>Тестові записи. Реальні поповнення, перекази та виведення недоступні.</p><div className="entitlement-meters">{Object.entries({cash:'Основний баланс',promo:'Промоційні бонуси',referral:'Реферальні кошти'}).map(([key,label])=><article key={key}><strong>{label}: {amount(data.wallet.balances[key].available_minor)}</strong>{data.wallet.balances[key].reserved_minor>0&&<p>Зарезервовано: {amount(data.wallet.balances[key].reserved_minor)}</p>}{data.wallet.balances[key].pending_minor>0&&<p>Очікує: {amount(data.wallet.balances[key].pending_minor)}</p>}</article>)}</div></section>}
  {data.referrals?.test_only&&<a className="bill-main-action" href="/settings?section=referrals">Реферальна програма <ChevronRight size={20}/></a>}
  <div id="billing-history" className="bill-section-heading bill-anchor"><h3>Історія оплат</h3>{payments.length>3&&<button className="bill-list-toggle" onClick={()=>setAllPayments(v=>!v)} aria-expanded={allPayments}>{allPayments?'Згорнути':'Вся історія ('+payments.length+')'}</button>}</div>{payments.length?<ul className="billing-payment-history bill-history">{(allPayments?payments:payments.slice(0,3)).map(p=><li key={p.id}><span className={'bill-icon '+(p.refunded_minor?'':'bill-paid-icon')}>{p.refunded_minor?<ReceiptText size={20}/>:<CheckCircle2 size={20}/>}</span><div className="bill-history-copy"><strong>{skuName(p.sku)}</strong><time>{date(p.created_at)}</time><small className={!p.refunded_minor?'bill-paid-text':''}>{p.refunded_minor>=p.amount_minor?'Повернено':p.refunded_minor>0?'Частково повернено':'Оплачено'}</small></div><b>{amount(p.amount_minor)}</b><details className="bill-history-details"><summary>Деталі операції</summary><p>Рахунок {p.invoice_id.slice(0,8)}</p>{p.refunded_minor>0&&<p>Повернено {amount(p.refunded_minor)}</p>}{p.order_id&&<small>{p.order_id}</small>}<button disabled={!!busy} onClick={()=>viewInvoice(p.invoice_id)}>Переглянути рахунок</button></details></li>)}</ul>:<p>Підтверджених оплат ще немає.</p>}
  {(invoices.length>=100||payments.length>=100)&&<p className="bill-muted">Показано до 100 останніх записів кожного типу. Для давніших операцій зверніться до підтримки.</p>}
  {data.reviews?.length>0&&<section aria-label="Оплати на перевірці"><h3>Оплати на перевірці</h3><p>Ми перевіряємо ці операції. Для уточнення зверніться до підтримки CarPot.</p><ul>{data.reviews.map((r:Row)=><li key={r.id}>{date(r.created_at)} · Рахунок {r.invoice_id.slice(0,8)}</li>)}</ul></section>}
  </>}
 </section>;
}
