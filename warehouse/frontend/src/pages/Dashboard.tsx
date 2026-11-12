import {useState} from 'react';
import StatisticsCharts from '../StatisticsCharts';
import SalesTrend from '../SalesTrend';
import {useCan,Permit} from '../permissions';
import {ArrowUpRight,Boxes,CarFront,ClipboardList,Package,ChartNoAxesCombined,Plus,RefreshCw} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api,money,type Row} from '../api';
import {Empty} from '../components';
import {Heading,OperationTable,State,useLoad} from '../shared';
import '../statistics.css';

const count=(v:unknown)=>Math.max(0,Number(v)||0).toLocaleString('uk-UA');

export default function Dashboard(){
 const can=useCan();
 const {data:d,error,loading,reload}=useLoad(()=>api('/dashboard'),[]);
 const finance=can('analytics.financial');
 const cost=finance&&can('parts.view_cost');
 const coverage=d?.cost_coverage;
 const uah=d?.valuation_by_currency?.find((r:Row)=>r.currency==='UAH');
 const knownValue=(value:unknown,known:unknown,currency='UAH')=>Number(known)>0?money(value,currency):'Не визначено';
 const [showFinance,setShowFinance]=useState(false);
 const [showSales,setShowSales]=useState(false);
 return <div className="stats-page">
  <Heading eyebrow="АНАЛІТИКА РОБОЧОГО ПРОСТОРУ" title="Статистика складу" description="Залишки, резерви, стан запчастин і вартість за поточними обліковими даними.">
   <button type="button" className="secondary" onClick={reload} disabled={loading}><RefreshCw size={16}/>Оновити</button>
   {can('vehicles.create')&&<Link className="button secondary" to="/vehicles"><CarFront size={16}/> Додати донора</Link>}
   {can('inventory.create')&&<Link className="button" to="/inventory"><Plus size={16}/> Додати запчастину</Link>}
  </Heading>
  <State error={error} loading={loading}/>
  {d&&<>
   <section className="stats-kpis" aria-label="Основні показники складу">
    {[
      {name:'Автомобілі-донори',value:count(d.vehicles),detail:'Активні автомобілі',Icon:CarFront},
      {name:'Позиції на складі',value:count(d.stock_positions??d.positions),detail:count(d.stock_units)+' фізичних одиниць',Icon:Package},
      {name:'Одиниці без резерву',value:count(d.available_units),detail:count(d.reserved_units)+' одиниць у резерві',Icon:Boxes},
      finance?{name:'Оцінка запасів · UAH',value:knownValue(uah?.value,uah?.priced_positions),detail:count(uah?.unpriced_positions)+' позицій без ціни · не дохід',Icon:ChartNoAxesCombined}:
      {name:'Одиниці в резерві',value:count(d.reserved_units),detail:'Не доступні до продажу',Icon:ClipboardList}
    ].map(m=><article className="stats-kpi" key={m.name}><div className="stats-kpi-top"><span>{m.name}</span><m.Icon size={18}/></div><strong>{m.value}</strong><small>{m.detail}</small></article>)}
   </section>
   <StatisticsCharts data={d}/>
   <div className="stats-lower-grid">
    <Permit permission="audit.view"><section className="stats-pane stats-operations">
     <div className="stats-pane-title"><h2>Останні операції</h2><Link className="stats-inline-link" to="/analytics">Журнал <ArrowUpRight size={14}/></Link></div>
     {d.recent_operations?.length?<OperationTable rows={d.recent_operations}/>:<Empty title="Історія почнеться з першої дії">Складські зміни відображатимуться тут.</Empty>}
    </section></Permit>
    <Permit permission="analytics.financial"><section className="stats-pane stats-finance">
     <div className="stats-pane-title"><h2>Фінансовий огляд</h2><span className="stats-currency">UAH</span></div>
     <p className="stats-pane-subtitle">Облікована оцінка, а не отриманий дохід.</p>
     <div className="stats-finance-rows">
      {cost&&<><div><span>Вартість придбання донорів</span><strong>{knownValue(d.vehicle_acquisition_cost,coverage?.vehicles_with_cost)}</strong></div>
      <div><span>Облікована собівартість деталей</span><strong>{knownValue(d.allocated_parts_cost,coverage?.stock_positions_with_cost)}</strong></div>
      <div><span>Потенційна валова маржа · UAH</span><strong>{knownValue(d.potential_gross_margin,d.margin_positions)}</strong></div></>}
      <div><span>Оцінка запасів · UAH</span><strong>{knownValue(uah?.value,uah?.priced_positions)}</strong></div>
     </div>
     {cost&&<p className="stats-finance-foot">Собівартість відома для {count(coverage?.stock_positions_with_cost)} позицій; не визначена для {count(coverage?.stock_positions_without_cost)}. Вартість придбання не визначена для {count(coverage?.vehicles_without_cost)} донорів. Маржа охоплює лише {count(d.margin_positions)} фізичних позицій із ціною та собівартістю в UAH. Вартість донорів не віднімається повторно.</p>}
     <button type="button" className="stats-expand" aria-expanded={showFinance} onClick={()=>setShowFinance(x=>!x)}>{showFinance?'Сховати':'Вартість за валютами'}</button>
     {showFinance&&<div className="stats-finance-rows">{(d.valuation_by_currency||[]).map((r:Row)=><div key={r.currency}><span>{r.currency} · {count(r.unpriced_positions)} без ціни</span><strong>{knownValue(r.value,r.priced_positions,r.currency)}</strong></div>)}</div>}
    </section></Permit>
   </div>
   {['analytics.view','analytics.financial','sales.view','sales.view_financials'].every(p=>can(p))&&<section className="stats-sales-section">
    <div className="stats-sales-toggle"><div><h2>Динаміка продажів</h2><p>Окремий звіт за фактичними операціями та обраним періодом.</p></div><button type="button" aria-expanded={showSales} onClick={()=>setShowSales(x=>!x)}>{showSales?'Згорнути':'Відкрити звіт'}</button></div>
    {showSales&&<SalesTrend/>}
   </section>}
  </>}
 </div>;
}
