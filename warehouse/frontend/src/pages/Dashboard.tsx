import StatisticsCharts from '../StatisticsCharts';
import SalesTrend from '../SalesTrend';
import {useCan,Permit} from '../permissions';
import {
  ArrowUpRight,
  Boxes,
  CarFront,
  ClipboardList,
  Plus,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, money, type Row } from "../api";
import { Empty } from "../components";

import { Heading, Metrics, OperationTable, State, useLoad } from "../shared";
export default function Dashboard() {
  const can=useCan();
  const { data: d, error, loading } = useLoad(() => api("/dashboard"), []);
  return (
    <>
      <Heading
        eyebrow="ВАШ РОБОЧИЙ ПРОСТІР"
        title="Огляд складу"
        description="Актуальний стан запасів і останні зміни у вашому бізнесі."
      >
        <Link className="button" to="/vehicles">
          <CarFront size={17} />
          Додати донора
        </Link>
        <Link className="button secondary" to="/inventory">
          <Plus size={17} />
          Додати запчастину
        </Link>
      </Heading>
      <State error={error} loading={loading} />
      {d && (
        <>
          <Metrics d={d} />
          <StatisticsCharts data={d}/>
          {['analytics.view','analytics.financial','sales.view','sales.view_financials'].every(p=>can(p))&&<SalesTrend/>}
          <Permit permission="analytics.financial"><section className="panel padded"><h2>Вартість запасів за валютами</h2>{d.valuation_by_currency?.map((r:Row)=><p key={r.currency}>{money(r.value,r.currency)}</p>)}</section></Permit>
          <div className="dashboard-grid">
            <Permit permission="audit.view"><section className="panel">
              <div className="panel-title">
                <h2>Останні операції</h2>
                <Link to="/analytics">
                  Усі операції <ArrowUpRight size={15} />
                </Link>
              </div>
              {d.recent_operations?.length ? (
                <OperationTable rows={d.recent_operations} />
              ) : (
                <Empty title="Історія почнеться з першої дії">
                  Додайте донора або запчастину — кожна зміна з’явиться тут.
                </Empty>
              )}
            </section></Permit>
<Permit permission="analytics.financial">            <section className="panel">
              <div className="panel-title">
                <h2>Фінансовий огляд</h2>
                <span className="pill">UAH</span>
              </div>
              <div className="finance">
                <span>
                  Придбання донорів<b>{money(d.vehicle_acquisition_cost)}</b>
                </span>
                <span>
                  Облікована собівартість деталей
                  <b>{money(d.allocated_parts_cost)}</b>
                </span>
                <span>
                  Потенційна валова маржа
                  <b>{money(d.potential_gross_margin)}</b>
                </span>
                <p>
                  Оцінка за {d.margin_positions} позиціями з ціною та
                  собівартістю. Це не фактичний дохід чи реалізований прибуток.
                  Вартість донорів окремо, без подвійного віднімання.
                </p>
              </div>
            </section></Permit>
          </div>
          <div className="section-title">
            <h2>Розпочніть роботу зі складом</h2>
            <span>Простий і послідовний облік</span>
          </div>
          <div className="quick-grid">
            {[
              {
                n: "01",
                title: "Додайте автомобіль",
                desc: "Збережіть дані донора та витрати на придбання.",
                to: "/vehicles",
                icon: CarFront,
              },
              {
                n: "02",
                title: "Підготуйте чекліст",
                desc: "Імпортуйте таксономію та сформуйте список можливих деталей.",
                to: "/catalog",
                icon: ClipboardList,
              },
              {
                n: "03",
                title: "Зафіксуйте залишки",
                desc: "Підтвердьте наявність і проведіть надходження.",
                to: "/operations",
                icon: Boxes,
              },
            ].map((x) => (
              <Link to={x.to} className="quick-card" key={x.n}>
                <div>
                  <x.icon size={23} />
                  <span>{x.n}</span>
                </div>
                <h3>{x.title}</h3>
                <p>{x.desc}</p>
                <ArrowUpRight size={17} />
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}
