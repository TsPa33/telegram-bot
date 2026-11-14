import type {Row} from './api';
export type BillingCommand={scope:string;kind:'invoice';sku:string;request_key:string}|{scope:string;kind:'checkout';invoice_id:string};
export function billingScope(actor:string,workspace:string){if(!actor||!workspace)throw Error('Оновіть доступ до компанії.');return JSON.stringify([actor,workspace]);}
export function restoreBillingCommand(raw:string|null,scope:string):BillingCommand|null{
 if(!raw)return null;const value=JSON.parse(raw);
 if(value?.scope!==scope)throw Error('Збережений запит належить іншій компанії.');
 if(value.kind==='invoice'&&typeof value.sku==='string'&&/^[a-z][a-z0-9_.]{1,79}$/.test(value.sku)&&typeof value.request_key==='string'&&/^[0-9a-f-]{36}$/.test(value.request_key))return value;
 if(value.kind==='checkout'&&typeof value.invoice_id==='string'&&/^[0-9a-f-]{36}$/.test(value.invoice_id))return value;
 throw Error('Збережений запит потребує перевірки в історії рахунків.');
}
export function billingOrder(value:string|null){return value&&/^carpot-(sandbox|production)-[0-9a-f]{32}$/.test(value)?value:null;}
export function validCheckoutForm(form:Row){
 if(form?.url!=='https://www.liqpay.ua/api/3/checkout'||form?.method!=='POST'||typeof form.data!=='string'||form.data.length>65536||!form.data.length||typeof form.signature!=='string'||form.signature.length>200||!form.signature.length)throw Error('Платіжну сторінку не підтверджено.');
 return {url:form.url,data:form.data,signature:form.signature};
}
export function paymentMessage(payment:Row|null){
 if(!payment)return '';
 if(payment.status==='refunded')return 'Оплату повернено. Перевірте поточну підписку.';
 if(payment.status==='paid'&&payment.activated===true)return 'Оплату підтверджено. Підписку активовано.';
 if(payment.status==='paid'&&payment.effective_from&&new Date(payment.effective_from).getTime()>Date.now())return 'Оплату підтверджено. Новий період почнеться після вже оплаченого.';
 if(payment.status==='paid')return 'Оплату підтверджено. Оновлюємо доступ до сервісу…';
 if(payment.status==='review')return 'Платіж потребує перевірки. Перегляньте історію або зверніться до підтримки.';
 if(payment.status==='expired')return 'Строк оплати завершився. Перевірте статус перед створенням нового рахунку.';
 return 'Очікуємо підтвердження LiqPay';
}

export function capacityBreakdown(used:number,limit:number){
 const u=Number.isFinite(used)?Math.max(0,used):0,l=Number.isFinite(limit)?Math.max(0,limit):0;
 const free=Math.max(0,l-u),excess=Math.max(0,u-l),total=Math.max(1,u,l);
 return {used:u,limit:l,free,excess,usedPercent:Math.min(u,l)/total*100,excessPercent:excess/total*100};
}

/** A conservative display-only chain of settled base periods in the bound cabinet.
 * Never extend across gaps, missing settlement evidence, full refunds, or add-ons.
 * The API returns at most 100 records of each kind; callers label truncated data.
 */
export function paidCoverage(currentEnd:string|null,status:string,invoices:Row[],payments:Row[],now=Date.now()){
 if(status!=='ACTIVE'||!currentEnd)return null;
 const end=Date.parse(currentEnd);if(!Number.isFinite(end)||end<=now)return null;
 const settled=new Map(payments.filter(p=>typeof p.invoice_id==='string'&&Number.isSafeInteger(p.amount_minor)&&p.amount_minor>0&&Number.isSafeInteger(p.refunded_minor)&&p.refunded_minor>=0&&p.refunded_minor<p.amount_minor&&/^warehouse\.(standard|premium)$/.test(p.sku)).map(p=>[p.invoice_id,p]));
 const intervals=invoices.filter(i=>i.kind==='base'&&i.status==='paid'&&settled.get(i.id)?.amount_minor===i.amount_minor).map(i=>({start:Date.parse(i.starts_at),end:Date.parse(i.ends_at)})).filter(i=>Number.isFinite(i.start)&&Number.isFinite(i.end)&&i.start<i.end).sort((a,b)=>a.start-b.start||a.end-b.end);
 if(!intervals.some(i=>i.start<=now&&i.end===end))return null;
 let through=end,additionalPeriods=0;
 for(const i of intervals){if(i.start>through)break;if(i.end>through){through=i.end;additionalPeriods++;}}
 return {through:new Date(through).toISOString(),additionalPeriods,limited:invoices.length>=100||payments.length>=100};
}
