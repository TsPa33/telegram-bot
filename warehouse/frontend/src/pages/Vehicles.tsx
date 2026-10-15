import { Archive as ArchiveIcon, Plus, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, money, type Page, type Row } from "../api";
import {
  Badge,
  Empty,
  Modal,
  Pager,
  RecordForm,
  type Field,
} from "../components";

import {
  choices,
  Confirm,
  Heading,
  option,
  State,
  useLoad,
  type Notify,
} from "../shared";
const vehicleFields: Field[] = [
  { key: "manufacturer", label: "Виробник", required: true },
  { key: "model", label: "Модель", required: true },
  { key: "generation", label: "Покоління" },
  {
    key: "year",
    label: "Рік",
    type: "number",
    required: true,
    min: 1886,
    max: 2100,
  },
  { key: "engine", label: "Двигун" },
  {
    key: "fuel_type",
    label: "Тип палива",
    options: ["", "Бензин", "Дизель", "Гібрид", "Електро", "Газ"].map((x) =>
      option(x, x || "Не вказано"),
    ),
  },
  {
    key: "transmission",
    label: "Коробка передач",
    options: ["", "Механічна", "Автоматична", "Роботизована", "Варіатор"].map(
      (x) => option(x, x || "Не вказано"),
    ),
  },
  { key: "vin", label: "VIN", hint: "17 символів, необов’язково" },
  { key: "donor_id", label: "Внутрішній ID донора", required: true },
  {
    key: "acquisition_date",
    label: "Дата придбання",
    type: "date",
    required: true,
  },
  {
    key: "acquisition_cost",
    label: "Вартість придбання, ₴",
    type: "number",
    min: 0,
  },
  {
    key: "status",
    label: "Статус",
    options: choices(["planned", "dismantling", "completed"]),
  },
  { key: "notes", label: "Примітки", type: "textarea", wide: true },
];
export default function Vehicles({ notify }: { notify: Notify }) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [page, setPage] = useState(0),
    [edit, setEdit] = useState<Row | null>(null),
    [detail, setDetail] = useState<Row | null>(null),
    [confirm, setConfirm] = useState<Row | null>(null);
  const { data, error, loading, reload } = useLoad(
    () =>
      api<Page>(
        `/vehicles?q=${encodeURIComponent(q)}&status=${status}&limit=50&offset=${page * 50}`,
      ),
    [q, status, page],
  );
  const navigate = useNavigate();
  return (
    <>
      <Heading
        eyebrow="ДОНОРСЬКИЙ ПАРК"
        title="Автомобілі-донори"
        description="Дані автомобілів, чеклісти демонтажу та оцінка запчастин."
      >
        <button
          className="primary"
          onClick={() => setEdit({ status: "dismantling" })}
        >
          <Plus size={17} />
          Додати автомобіль
        </button>
      </Heading>
      <div className="toolbar">
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Пошук автомобілів"
            placeholder="Виробник, модель, VIN або ID…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label="Статус автомобіля"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(0);
          }}
        >
          <option value="">Усі статуси</option>
          {choices(["planned", "dismantling", "completed"]).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <State error={error} loading={loading} />
      <section className="panel">
        {data?.items.length ? (
          <>
            <div className="table-wrap desktop-table">
              <table>
                <thead>
                  <tr>
                    <th>Автомобіль</th>
                    <th>ID донора</th>
                    <th>Двигун / КПП</th>
                    <th>Придбання</th>
                    <th>Статус</th>
                    <th>Дії</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <button
                          className="text-button strong"
                          onClick={() => setDetail(v)}
                        >
                          {v.manufacturer} {v.model}
                        </button>
                        <small>
                          {v.year} · {v.generation || "Покоління не вказане"}
                        </small>
                      </td>
                      <td>
                        <code>{v.donor_id}</code>
                        <small>{v.vin || "Без VIN"}</small>
                      </td>
                      <td>
                        {v.engine || "—"}
                        <small>{v.transmission || "—"}</small>
                      </td>
                      <td>
                        {v.acquisition_cost ? money(v.acquisition_cost) : "—"}
                        <small>{v.acquisition_date}</small>
                      </td>
                      <td>
                        <Badge value={v.status} />
                      </td>
                      <td>
                        <div className="row-actions">
                          <button onClick={() => setEdit(v)}>Змінити</button>
                          <button
                            onClick={() =>
                              navigate(`/inventory?vehicle_id=${v.id}`)
                            }
                          >
                            Запчастини
                          </button>
                          <button
                            aria-label={`Архівувати ${v.donor_id}`}
                            className="icon-button"
                            onClick={() => setConfirm(v)}
                          >
                            <ArchiveIcon size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mobile-cards">
              {data.items.map((v) => (
                <article className="inventory-card" key={v.id}>
                  <div>
                    <button
                      className="text-button strong"
                      onClick={() => setDetail(v)}
                    >
                      {v.manufacturer} {v.model}
                    </button>
                    <Badge value={v.status} />
                  </div>
                  <p>
                    {v.year} · {v.donor_id}
                  </p>
                  <small>
                    {v.engine || "Двигун не вказаний"} ·{" "}
                    {v.acquisition_cost
                      ? money(v.acquisition_cost)
                      : "Вартість не вказана"}
                  </small>
                  <div className="card-actions">
                    <button onClick={() => setEdit(v)}>Змінити</button>
                    <button
                      onClick={() => navigate(`/inventory?vehicle_id=${v.id}`)}
                    >
                      Запчастини
                    </button>
                    <button
                      aria-label={`Архівувати ${v.donor_id}`}
                      onClick={() => setConfirm(v)}
                    >
                      <ArchiveIcon size={16} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <Pager total={data.total} page={page} setPage={setPage} />
          </>
        ) : (
          !loading && (
            <Empty
              title={
                q || status
                  ? "Автомобілів за цими фільтрами немає"
                  : "Додайте першого донора"
              }
            >
              Збережіть дані автомобіля, щоб пов’язати з ним запчастини та
              витрати.
            </Empty>
          )
        )}
      </section>
      {edit && (
        <Modal
          title={edit.id ? "Редагувати автомобіль" : "Новий автомобіль-донор"}
          onClose={() => setEdit(null)}
        >
          <RecordForm
            initial={edit}
            fields={vehicleFields}
            onSave={async (d) => {
              await api(
                "/vehicles" + (edit.id ? "/" + edit.id : ""),
                edit.id ? "PUT" : "POST",
                d,
              );
              setEdit(null);
              reload();
              notify("Дані автомобіля збережено");
            }}
          />
        </Modal>
      )}
      {detail && (
        <Modal
          title={`${detail.manufacturer} ${detail.model} · ${detail.donor_id}`}
          onClose={() => setDetail(null)}
        >
          <VehicleDetail
            vehicle={detail}
            notify={notify}
            onInventory={() => navigate(`/inventory?vehicle_id=${detail.id}`)}
          />
        </Modal>
      )}
      {confirm && (
        <Confirm
          title="Архівувати автомобіль?"
          text="Донор залишиться в історії. Його запчастини не архівуються автоматично."
          onClose={() => setConfirm(null)}
          onConfirm={async () => {
            await api("/archive/vehicles/" + confirm.id, "POST");
            setConfirm(null);
            reload();
            notify("Автомобіль переміщено в архів");
          }}
        />
      )}
    </>
  );
}
function VehicleDetail({
  vehicle: v,
  notify,
  onInventory,
}: {
  vehicle: Row;
  notify: Notify;
  onInventory: () => void;
}) {
  const {
    data: d,
    error,
    loading,
  } = useLoad(() => api(`/vehicles/${v.id}/analytics`), [v.id]);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <dl className="details">
        {[
          ["Рік", v.year],
          ["Двигун", v.engine || "—"],
          ["VIN", v.vin || "Не вказано"],
          [
            "Придбання",
            v.acquisition_cost ? money(v.acquisition_cost) : "Не вказано",
          ],
          ["Дата", v.acquisition_date],
          ["Примітки", v.notes || "—"],
        ].map(([k, val]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{val}</dd>
          </div>
        ))}
      </dl>
      <State error={error} loading={loading} />
      {d && (
        <div className="detail-stats">
          <span>
            Позицій<strong>{d.positions}</strong>
          </span>
          <span>
            Одиниць<strong>{d.stock_units}</strong>
          </span>
          <span>
            Оцінка продажу<strong>{money(d.estimated_sales_value)}</strong>
          </span>
          <span>
            Потенційна маржа<strong>{money(d.potential_gross_margin)}</strong>
          </span>
        </div>
      )}
      <p className="notice">
        Стандартний чекліст — перелік можливих деталей, а не точний OEM-каталог.
        Усі нові позиції мають нульовий залишок. Повторне формування зберігає
        вашу роботу.
      </p>
      <div className="modal-actions">
        <button onClick={onInventory}>Відкрити запчастини</button>
        <button
          disabled={busy}
          className="primary"
          onClick={async () => {
            setBusy(true);
            try {
              const r = await api(`/vehicles/${v.id}/checklist`, "POST");
              notify(`Додано позицій: ${r.created}. Уже існує: ${r.existing}`);
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Сформувати список запчастин
        </button>
      </div>
    </>
  );
}
