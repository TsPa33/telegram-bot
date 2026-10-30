import type {Row} from './api';
const cents=(value:unknown)=>{if(value===null||value===undefined)return null;const m=/^(\d{1,20})(?:\.(\d{1,2}))?$/.exec(String(value));return m?BigInt(m[1])*100n+BigInt((m[2]||'').padEnd(2,'0')):null;};
const decimal=(value:bigint)=>`${value/100n}.${String(value%100n).padStart(2,'0')}`;
// Display only the ledger's recorded values; never consult Part.selling_price.
export function saleMoney(row:Row){
 const currency=['UAH','USD'].includes(row.currency)?row.currency:null;
 const unit=row.price_recorded===true?cents(row.unit_price):null,total=row.price_recorded===true?cents(row.total):null;
 return {currency,unit:currency&&unit!==null?decimal(unit):null,total:currency&&unit!==null&&total!==null?decimal(total):null};
}
export function salesPageSummary(rows:Row[],financial:boolean){
 const groups=new Map<string,{cents:bigint;count:number}>();let units=0,unpriced=0;
 for(const row of rows){if(Number.isSafeInteger(row.quantity)&&row.quantity>0)units+=row.quantity;if(!financial)continue;const price=saleMoney(row);if(price.total===null||!price.currency){unpriced++;continue;}const g=groups.get(price.currency)||{cents:0n,count:0};g.cents+=cents(price.total)!;g.count++;groups.set(price.currency,g);}
 return {units,unpriced:financial?unpriced:null,currencies:[...groups].sort(([a],[b])=>a.localeCompare(b)).map(([currency,g])=>({currency,total:decimal(g.cents),average:decimal((g.cents+BigInt(Math.floor(g.count/2)))/BigInt(g.count)),count:g.count}))};
}
export function salesLedgerQuery({q,vehicle,source,from,to,page}:{q:string;vehicle:string;source:string;from:string;to:string;page:number}){
 const query=new URLSearchParams({q,limit:'50',offset:String(page*50)});if(vehicle)query.set('vehicle_id',vehicle);if(source)query.set('source',source);
 const valid=(day:string)=>{const d=new Date(day+'T00:00:00');return /^\d{4}-\d{2}-\d{2}$/.test(day)&&!isNaN(d.valueOf())&&d.getFullYear()===Number(day.slice(0,4))&&d.getMonth()+1===Number(day.slice(5,7))&&d.getDate()===Number(day.slice(8,10));};
 if((from&&!valid(from))||(to&&!valid(to))||(from&&to&&from>to))return {query,error:'Оберіть коректний період: дата «Від» має бути не пізнішою за «До».'};
 if(from)query.set('date_from',new Date(from+'T00:00:00').toISOString());if(to)query.set('date_to',new Date(to+'T23:59:59.999').toISOString());return {query,error:''};
}
