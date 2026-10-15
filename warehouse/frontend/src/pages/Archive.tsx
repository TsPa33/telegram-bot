import { useState } from "react";
import { api, money, type Page, type Row } from "../api";
import { Empty, Pager } from "../components";

import { Confirm, Heading, State, useLoad, type Notify } from "../shared";
export default function Archive({ notify }: { notify: Notify }) {
  const [entity, setEntity] = useState("parts"),
    [page, setPage] = useState(0),
    [confirm, setConfirm] = useState<Row | null>(null);
  const { data, error, loading, reload } = useLoad(
    () => api<Page>(`/archive?entity=${entity}&limit=50&offset=${page * 50}`),
    [entity, page],
  );
  return (
    <>
      <Heading
        eyebrow="ІСТОРИЧНІ ДАНІ"
        title="Архів"
        description="Архівні записи збережені разом із залишками та зв’язками в історії."
      />
      <div className="tabs">
        {[
          { key: "parts", label: "Запчастини" },
          { key: "vehicles", label: "Автомобілі" },
          { key: "categories", label: "Категорії" },
        ].map((t) => (
          <button
            className={t.key === entity ? "active" : ""}
            key={t.key}
            onClick={() => {
              setEntity(t.key);
              setPage(0);
            }}
          >
            {t.label}
          </button>
        ))}
      </div>
      <State error={error} loading={loading} />
      <section className="panel">
        {data?.items.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Запис</th>
                    <th>Ідентифікатор</th>
                    <th>Збережені дані</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <b>{r.name || `${r.manufacturer} ${r.model}`}</b>
                      </td>
                      <td>
                        <code>
                          {r.donor_id ||
                            r.external_key ||
                            r.oem_number ||
                            r.id.slice(0, 8)}
                        </code>
                      </td>
                      <td>
                        {entity === "parts"
                          ? `Залишок: ${r.quantity}, резерв: ${r.reserved_quantity}`
                          : entity === "vehicles"
                            ? `${r.year} · ${r.acquisition_cost ? money(r.acquisition_cost) : "Вартість не вказана"}`
                            : r.source}
                      </td>
                      <td>
                        <button onClick={() => setConfirm(r)}>Відновити</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager total={data.total} page={page} setPage={setPage} />
          </>
        ) : (
          !loading && (
            <Empty title="Архів порожній">
              Архівовані записи можна буде знайти та відновити тут.
            </Empty>
          )
        )}
      </section>
      {confirm && (
        <Confirm
          title="Відновити запис?"
          text="Запис повернеться до активного списку. Пов’язані записи не змінюються автоматично."
          onClose={() => setConfirm(null)}
          onConfirm={async () => {
            await api(`/archive/${entity}/${confirm.id}?restore=true`, "POST");
            setConfirm(null);
            reload();
            notify("Запис відновлено");
          }}
        />
      )}
    </>
  );
}
