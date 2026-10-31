import {useState} from 'react';
import {ArrowRight, ChartNoAxesColumnIncreasing, CircleHelp, PackageCheck, Tags} from 'lucide-react';
import {Link} from 'react-router-dom';
import {labels,money,type Row} from './api';
import {Permit} from './permissions';
import './statistics.css';

type Datum={name:string;value:number;display?:string;note?:string};
const positive=(value:unknown)=>Math.max(0,Number(value)||0);
const number=(value:unknown)=>positive(value).toLocaleString('uk-UA');
const translated:Record<string,string>={
 'Дополнительные удобства':'Додаткове обладнання',
 'Внутренняя отделка':'Оздоблення салону',
 'Освещение':'Освітлення',
 'Сцепления и навесные элементы':'Зчеплення й навісні елементи',
 'Ходовая часть':'Ходова частина',
 'Двигатель':'Двигун',
 'Электрика':'Електрика',
 'Кузов':'Кузов',
 'Отопление и вентиляция':'Опалення та вентиляція'
};
const localized=(value:unknown)=>translated[String(value)]||String(value||'Без категорії');

/** Shared with sales analytics: accessible, progressive disclosure, no nested scrolling. */
export function Bars({title,rows,note,initial=7}:{title:string;rows:Datum[];note?:string;initial?:number}){
 const [selected,setSelected]=useState<number|null>(null);
 const [expanded,setExpanded]=useState(false);
 const max=Math.max(1,...rows.map(r=>positive(r.value)));
 const visible=expanded?rows:rows.slice(0,initial);
 return <section className="panel padded statistics-chart" aria-label={title}>
  <h2>{title}</h2>{note&&<p>{note}</p>}
  {!rows.length?<p role="status">Поки немає даних для діаграми.</p>:<>
   <div className="chart-bars">{visible.map((r,i)=><button type="button" className="chart-bar" key={r.name+':'+i} aria-pressed={selected===i} onClick={()=>setSelected(selected===i?null:i)} title={r.name+': '+(r.display??number(r.value))}>
    <span className="chart-label">{r.name}</span><span className="chart-track" aria-hidden="true"><span style={{width:positive(r.value)/max*100+'%'}}/></span><strong>{r.display??number(r.value)}</strong>
   </button>)}</div>
   {selected!==null&&rows[selected]&&<p role="status">{rows[selected].name}: {rows[selected].display??number(rows[selected].value)}</p>}
   {rows.length>initial&&<button type="button" className="stats-expand" aria-expanded={expanded} onClick={()=>{setExpanded(v=>!v);setSelected(null)}}>{expanded?'Згорнути список':`Показати всі (${rows.length})`}</button>}
  </>}
 </section>;
}

function ConditionOverview({rows}:{rows:Row[]}){
 const normalized=rows.map(r=>({name:labels[r.name]||String(r.name||'Стан не уточнено'),quantity:positive(r.quantity)})).sort((a,b)=>b.quantity-a.quantity);
 const total=normalized.reduce((sum,r)=>sum+r.quantity,0);
 return <section className="stats-pane" aria-labelledby="stats-condition-title">
  <div className="stats-pane-title"><h2 id="stats-condition-title">Стан запчастин</h2><span><PackageCheck size={17}/></span></div>
  <p className="stats-pane-subtitle">Фізичний стан облікованих одиниць, без припущень.</p>
  {!total?<p className="stats-empty">Немає даних про стан деталей.</p>:<>
   <div className="stats-condition-segments" aria-label="Розподіл за станом" role="img">{normalized.filter(x=>x.quantity>0).map((r,i)=><div key={r.name} className={'stats-segment stats-segment-'+(i%5)} style={{width:r.quantity/total*100+'%'}} title={r.name+': '+number(r.quantity)}/>)}</div>
   <div className="stats-condition-list">{normalized.map((r,i)=><div key={r.name}><span className={'stats-dot stats-dot-'+(i%5)}/><span>{r.name}</span><strong>{number(r.quantity)}</strong><small>{total?Math.round(r.quantity/total*100):0}%</small></div>)}</div>
  </>}
  <Link className="stats-inline-link" to="/inventory">Переглянути запчастини <ArrowRight size={14}/></Link>
 </section>;
}

function StockOverview({available,reserved}:{available:number;reserved:number}){
 const all=available+reserved;
 return <section className="stats-pane" aria-labelledby="stats-stock-title">
  <div className="stats-pane-title"><h2 id="stats-stock-title">Наявність і резерви</h2><span><PackageCheck size={17}/></span></div>
  <p className="stats-pane-subtitle">Доступний залишок і одиниці, відкладені в резерв.</p>
  <div className="stats-stock-total"><strong>{number(all)}</strong><span>одиниць на складі</span></div>
  <div className="stats-condition-segments" aria-label="Доступні одиниці та резерв" role="img">
   {all>0&&<><div className="stats-segment stats-segment-0" style={{width:available/all*100+'%'}}/><div className="stats-segment stats-segment-2" style={{width:reserved/all*100+'%'}}/></>}
  </div>
  <div className="stats-stock-rows">
   <div><span className="stats-dot stats-dot-0"/>Доступно <strong>{number(available)}</strong></div>
   <div><span className="stats-dot stats-dot-2"/>У резерві <strong>{number(reserved)}</strong></div>
  </div>
  <Link className="stats-inline-link" to="/inventory">Відкрити склад <ArrowRight size={14}/></Link>
 </section>;
}

function CategoryOverview({rows}:{rows:Row[]}){
 const [expanded,setExpanded]=useState(false);
 const sorted=rows.map(r=>({name:localized(r.name),count:positive(r.quantity)})).sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name,'uk'));
 const max=Math.max(1,...sorted.map(x=>x.count)),visible=expanded?sorted:sorted.slice(0,6);
 return <section className="stats-pane" aria-labelledby="stats-category-title">
  <div className="stats-pane-title"><h2 id="stats-category-title">Запчастини за категоріями</h2><span><Tags size={17}/></span></div>
  <p className="stats-pane-subtitle">Одиниці на складі за категоріями. Не весь потенційний каталог.</p>
  {!visible.length?<p className="stats-empty">Немає категорій із залишками.</p>:<div className="stats-rank-list">{visible.map(r=><div className="stats-rank" key={r.name}>
   <span title={r.name}>{r.name}</span><div className="stats-rank-track"><span style={{width:r.count/max*100+'%'}}/></div><strong>{number(r.count)}</strong>
  </div>)}</div>}
  {sorted.length>6&&<button className="stats-expand" type="button" aria-expanded={expanded} onClick={()=>setExpanded(e=>!e)}>{expanded?'Згорнути':`Усі категорії (${sorted.length})`}</button>}
 </section>;
}
function ValuationOverview({rows,currency}:{rows:Row[];currency:string}){
 const [expanded,setExpanded]=useState(false);
 const sorted=[...rows].sort((a,b)=>positive(b.value)-positive(a.value)||String(a.name).localeCompare(String(b.name),'uk'));
 const max=Math.max(1,...sorted.map(r=>positive(r.value))),visible=expanded?sorted:sorted.slice(0,7);
 const unpriced=sorted.reduce((sum,r)=>sum+positive(r.unpriced_positions),0);
 return <section className="stats-pane stats-valuation" aria-label={'Оцінка складу за авто, '+currency}>
   <div className="stats-pane-title"><h2>Оціночна вартість за автомобілями · {currency}</h2><span><ChartNoAxesColumnIncreasing size={17}/></span></div>
   <p className="stats-pane-subtitle">Поточні ціни залишків, не дохід або прибуток. Без ціни позиції не оцінюються.</p>
   {!sorted.length?<p className="stats-empty">У цій валюті немає позицій.</p>:<div className="stats-rank-list">{visible.map((r:Row)=><div className="stats-valuation-row" key={String(r.id)+currency}>
    <span title={r.name}>{r.name}</span>
    {positive(r.priced_positions)>0?<><div className="stats-rank-track"><span style={{width:positive(r.value)/max*100+'%'}}/></div><strong>{money(r.value,currency)}</strong></>:<><div className="stats-rank-track stats-unvalued"/><strong className="stats-no-price">Без оцінки</strong></>}
   </div>)}</div>}
   {sorted.length>7&&<button className="stats-expand" type="button" aria-expanded={expanded} onClick={()=>setExpanded(e=>!e)}>{expanded?'Згорнути':`Показати всі автомобілі (${sorted.length})`}</button>}
   {unpriced>0&&<p className="stats-valuation-note"><CircleHelp size={15}/> {number(unpriced)} позицій у цьому переліку не мають указаної ціни.</p>}
 </section>;
}

export default function StatisticsCharts({data:d}:{data:Row}){
 const values:Row[]=d.vehicle_valuation_by_currency||[];
 const currencies=[...new Set(values.map(r=>String(r.currency)))].sort();
 return <div className="stats-dashboard-grid">
   <CategoryOverview rows={d.by_category||[]}/>
   <ConditionOverview rows={d.by_condition||[]}/>
   <StockOverview available={positive(d.available_units)} reserved={positive(d.reserved_units)}/>
   <Permit permission="analytics.financial">{currencies.length?currencies.map(currency=><ValuationOverview key={currency} rows={values.filter(r=>r.currency===currency)} currency={currency}/>):<section className="stats-pane"><h2>Оціночна вартість за автомобілями</h2><p className="stats-empty">Немає даних для оцінки.</p></section>}</Permit>
 </div>;
}
