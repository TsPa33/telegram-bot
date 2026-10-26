import {useState} from 'react';
import {labels,money,type Row} from './api';
import {Permit} from './permissions';
import './statistics.css';

type Datum={name:string;value:number;display?:string};
/** Native focusable buttons expose the exact value without hover or SVG-only text. */
export function Bars({title,rows,note}:{title:string;rows:Datum[];note?:string}){
 const [selected,setSelected]=useState<number|null>(null);
 const max=Math.max(1,...rows.map(r=>r.value));
 return <section className="panel padded statistics-chart" aria-label={title}><h2>{title}</h2>{note&&<p>{note}</p>}
  {!rows.length?<p role="status">Поки немає даних для діаграми.</p>:<>
   <div className="chart-bars">{rows.map((r,i)=><button type="button" className="chart-bar" key={r.name+':'+i} aria-pressed={selected===i} onClick={()=>setSelected(selected===i?null:i)} title={`${r.name}: ${r.display??r.value.toLocaleString('uk-UA')}`}>
    <span className="chart-label">{r.name}</span><span className="chart-track" aria-hidden="true"><span style={{width:Math.max(0,r.value)/max*100+'%'}}/></span><strong>{r.display??r.value.toLocaleString('uk-UA')}</strong>
   </button>)}</div>
   {selected!==null&&rows[selected]&&<p role="status">{rows[selected].name}: {rows[selected].display??rows[selected].value.toLocaleString('uk-UA')}</p>}
  </>}
 </section>;
}
export default function StatisticsCharts({data:d}:{data:Row}){
 const values:Row[]=d.vehicle_valuation_by_currency||[];
 const currencies=[...new Set(values.map(r=>String(r.currency)))].sort();
 return <div className="statistics-grid">
  <Bars title="Запчастини за категоріями" note="Обліковані одиниці, не потенційний каталог." rows={(d.by_category||[]).map((r:Row)=>({name:r.name,value:Number(r.quantity)}))}/>
  <Bars title="Стан запчастин" rows={(d.by_condition||[]).map((r:Row)=>({name:labels[r.name]||r.name,value:Number(r.quantity)}))}/>
  <Bars title="Доступні одиниці та резерви" rows={[{name:'Доступно',value:Number(d.available_units||0)},{name:'У резерві',value:Number(d.reserved_units||0)}]}/>
  <Permit permission="analytics.financial">{currencies.length?currencies.map(currency=><Bars key={currency} title={'Оціночна вартість за автомобілями · '+currency} note="Оцінка за поточними цінами залишків. Це не отриманий дохід. Позиції без ціни не оцінені." rows={values.filter(r=>r.currency===currency).map(r=>({name:r.name,value:Number(r.value),display:money(r.value,currency)}))}/>):<Bars title="Оціночна вартість за автомобілями" rows={[]}/>}</Permit>
 </div>;
}
