import {useState} from 'react';
import {api,money,type Row} from './api';
import {State,useLoad} from './shared';
import {Bars} from './StatisticsCharts';
import {calendarToday,periodLabel,recentPeriod,validPeriod} from './salesChart';

export default function SalesTrend(){
 const [range,setRange]=useState(()=>recentPeriod(30));
 const [draft,setDraft]=useState(range),[interval,setInterval]=useState('day'),[tz,setTz]=useState('Europe/Kyiv');
 const [validation,setValidation]=useState('');
 const data=useLoad(()=>api('/sales/summary?'+new URLSearchParams({date_from:range.from,date_to:range.to,interval,tz})),[range.from,range.to,interval,tz]);
 const d=data.data;
 const currencies:string[]=d?.totals_by_currency?.map((r:Row)=>r.currency)||[];
 function preset(days:number){const r=recentPeriod(days,calendarToday(new Date(),tz));setDraft(r);setRange(r);setValidation('');}
 return <section className="panel padded sales-trend" aria-label="Динаміка продажів"><h2>Динаміка продажів</h2>
  <p>Фактично проведені продажі за датою складської операції. Це суми продажів, не прибуток. Повернення та сторнування поки не підтримуються.</p>
  <form className="sales-trend-filters" onSubmit={e=>{e.preventDefault();if(!validPeriod(draft.from,draft.to)){setValidation('Оберіть коректний період до 366 днів включно (1900–2100).');return;}setValidation('');setRange({...draft});}}>
   <label>Від<input type="date" aria-label="Продажі від" required min="1900-01-01" max="2100-12-31" value={draft.from} onChange={e=>setDraft({...draft,from:e.target.value})}/></label>
   <label>До<input type="date" aria-label="Продажі до" required min="1900-01-01" max="2100-12-31" value={draft.to} onChange={e=>setDraft({...draft,to:e.target.value})}/></label>
   <label>Групування<select aria-label="Групування продажів" value={interval} onChange={e=>setInterval(e.target.value)}><option value="day">За днями</option><option value="week">За тижнями</option><option value="month">За місяцями</option></select></label>
   <label>Часовий пояс<select aria-label="Часовий пояс продажів" value={tz} onChange={e=>setTz(e.target.value)}><option value="Europe/Kyiv">Київ</option><option value="UTC">UTC</option></select></label>
   <button type="submit">Показати</button>
  </form>
  <div className="sales-trend-presets">{[7,30,90].map(days=><button className="secondary" key={days} onClick={()=>preset(days)}>Останні {days} днів</button>)}</div>
  <p>Період: {periodLabel(range.from,'day')} — {periodLabel(range.to,'day')} · {tz==='UTC'?'UTC':'Київ'}</p>
  {validation&&<p role="alert">{validation}</p>}
  <State loading={data.loading} error={data.error}/>{data.error&&<button onClick={data.reload}>Повторити завантаження продажів</button>}
  {!data.loading&&!data.error&&d&&<>
   <p className="sales-trend-total">Продано одиниць: <strong>{d.units}</strong> · Операцій: <strong>{d.sales_count}</strong></p>
   {!d.sales_count?<p role="status">За обраний період проведених продажів немає.</p>:<>
    <div className="sales-trend-totals">{d.totals_by_currency.map((r:Row)=><p key={r.currency}>{money(r.amount,r.currency)} · {r.units} од.</p>)}</div>
    {!!d.unpriced_units&&<p className="notice">{d.unpriced_units} проданих одиниць без достовірної історичної ціни. Їх включено лише до кількості.</p>}
    {currencies.map(currency=><Bars key={`${currency}:${range.from}:${range.to}:${interval}:${tz}`} title={'Сума продажів · '+currency} note="Нові періоди зверху. Виберіть стовпчик для точного значення. Перший і останній періоди можуть бути неповними." rows={[...d.periods].reverse().map((p:Row)=>{const r=p.by_currency.find((v:Row)=>v.currency===currency);return {name:periodLabel(p.date,interval),value:Number(r?.amount||0),display:money(r?.amount||'0.00',currency)+' · '+(r?.units||0)+' од.'};})}/>)}
    <Bars key={`units:${range.from}:${range.to}:${interval}:${tz}`} title="Продані одиниці" rows={[...d.periods].reverse().map((p:Row)=>({name:periodLabel(p.date,interval),value:p.units,display:p.units+' од. · '+p.sales_count+' операцій'}))}/>
   </>}
  </>}
 </section>;
}
