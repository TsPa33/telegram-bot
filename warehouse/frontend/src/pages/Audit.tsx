import { useEffect, useState } from "react";
import { all, api, labels, money, type Page, type Row } from "../api";
import { Empty, Pager } from "../components";

import {
  choices,
  Heading,
  Metrics,
  OperationTable,
  State,
  useLoad,
} from "../shared";
export default function Audit() {
  const [type, setType] = useState(""),
    [vehicle, setVehicle] = useState(""),
    [part, setPart] = useState(""),
    [actor, setActor] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [page, setPage] = useState(0);
  const lookups = useLoad(
    () =>
      Promise.all([
        all("/vehicles"),
        all("/vehicles?archived=true"),
        all("/parts"),
        all("/parts?archived=true"),
        api("/auth/me"),
      ]),
    [],
  );
  const summary = useLoad(() => api("/dashboard"), []);
  const query = new URLSearchParams({ limit: "50", offset: String(page * 50) });
  if (type) query.set("type", type);
  if (vehicle) query.set("vehicle_id", vehicle);
  if (part) query.set("part_id", part);
  if (actor) query.set("actor_id", actor);
  if (from) query.set("date_from", new Date(from + "T00:00:00").toISOString());
  if (to) query.set("date_to", new Date(to + "T23:59:59.999").toISOString());
  const log = useLoad(() => api<Page>("/audit?" + query), [query.toString()]);
  useEffect(() => setPage(0), [type, vehicle, part, actor, from, to]);
  return (
    <>
      <Heading
        eyebrow="ДАНІ ТА ПРОЗОРІСТЬ"
        title="Аналітика та аудит"
        description="Структура запасів і повна історія дій, включно з архівними записами."
      />
      {summary.data && (
        <>
          <Metrics d={summary.data} />
          <div className="chart-grid">
            {[
              {
                title: "Залишки за категоріями",
                data: summary.data.by_category,
                key: "quantity",
                currency: false,
              },
              {
                title: "Стан запчастин",
                data: summary.data.by_condition.map((r: Row) => ({
                  ...r,
                  name: labels[r.name] || r.name,
                })),
                key: "quantity",
                currency: false,
              },
              {
                title: "Оцінка за донорами",
                data: summary.data.by_vehicle,
                key: "value",
                currency: true,
              },
            ].map((g) => (
              <section className="panel padded" key={g.title}>
                <h2>{g.title}</h2>
                {g.data.length ? (
                  <div className="bars">
                    {g.data.map((r: Row, i: number) => (
                      <div key={i}>
                        <span>
                          {r.name}
                          <b>{g.currency ? money(r[g.key]) : r[g.key]}</b>
                        </span>
                        <div>
                          <i
                            style={{
                              width: `${Math.max(1, (100 * Number(r[g.key])) / Math.max(1, ...g.data.map((x: Row) => Number(x[g.key]))))}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">
                    Дані з’являться після додавання запасів.
                  </p>
                )}
              </section>
            ))}
          </div>
        </>
      )}
      <div className="section-title">
        <h2>Журнал операцій</h2>
        <span>Історія захищена від змін</span>
      </div>
      <div className="toolbar audit-filters">
        <select
          aria-label="Тип операції"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">Усі операції</option>
          {choices([
            "receipt",
            "write_off",
            "sale",
            "reserve",
            "release",
            "correction",
            "transfer",
            "archive",
            "restore",
            "vehicle_create",
            "vehicle_update",
            "part_create",
            "part_update",
            "checklist_create",
            "dismantling_start",
            "dismantling_status",
            "dismantling_receipt",
            "category_import",
          ]).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Донор в аудиті"
          value={vehicle}
          onChange={(e) => setVehicle(e.target.value)}
        >
          <option value="">Усі донори</option>
          {[...(lookups.data?.[0] || []), ...(lookups.data?.[1] || [])].map(
            (v: Row) => (
              <option value={v.id} key={v.id}>
                {v.donor_id}
                {v.archived ? " (архів)" : ""}
              </option>
            ),
          )}
        </select>
        <select
          aria-label="Запчастина в аудиті"
          value={part}
          onChange={(e) => setPart(e.target.value)}
        >
          <option value="">Усі запчастини</option>
          {[...(lookups.data?.[2] || []), ...(lookups.data?.[3] || [])].map(
            (v: Row) => (
              <option value={v.id} key={v.id}>
                {v.name}
                {v.archived ? " (архів)" : ""}
              </option>
            ),
          )}
        </select>
        <select
          aria-label="Автор операції"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        >
          <option value="">Усі автори акаунта</option>
          {lookups.data?.[4] && (
            <option value={lookups.data[4].id}>{lookups.data[4].name}</option>
          )}
        </select>
        <label>
          Від
          <input
            aria-label="Дата від"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          До
          <input
            aria-label="Дата до"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
      </div>
      <State
        error={log.error || lookups.error || summary.error}
        loading={log.loading || summary.loading}
      />
      <section className="panel">
        {log.data?.items.length ? (
          <>
            <OperationTable rows={log.data.items} />
            <Pager total={log.data.total} page={page} setPage={setPage} />
          </>
        ) : (
          !log.loading && (
            <Empty title="Операцій за вибраними умовами немає">
              Змініть фільтри або проведіть першу складську операцію.
            </Empty>
          )
        )}
      </section>
      <p className="footnote">
        Оцінки складу враховують активні позиції. Архівні дані зберігаються в
        журналі. Вартість запасів не є фактичним доходом.
      </p>
    </>
  );
}
