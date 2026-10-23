import {
  Archive as ArchiveIcon,
  Plus,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { all, api, labels, money, type Page, type Row } from "../api";
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
function partFields(vehicles: Row[], categories: Row[]): Field[] {
  return [
    { key: "name", label: "Назва запчастини", required: true, wide: true },
    {
      key: "vehicle_id",
      label: "Донор",
      options: [
        option("", "Без донора"),
        ...vehicles.map((v) =>
          option(v.id, `№ ${v.number ?? "—"} · ${v.manufacturer} ${v.model}`),
        ),
      ],
    },
    {
      key: "category_id",
      label: "Категорія",
      options: [
        option("", "Без категорії"),
        ...categories
          .filter((c) => c.kind !== "part")
          .map((c) => option(c.id, c.name + " · " + c.external_key)),
      ],
    },
    {
      key: "subcategory_id",
      label: "Підкатегорія",
      options: [
        option("", "Не вказано"),
        ...categories
          .filter((c) => c.parent_id)
          .map((c) =>
            option(
              c.id,
              (categories.find((p) => p.id === c.parent_id)?.name || "") +
                " / " +
                c.name,
            ),
          ),
      ],
      hint: "Має бути прямим дочірнім елементом вибраної категорії",
    },
    {
      key: "condition",
      label: "Стан",
      options: choices(["used", "new", "damaged", "refurbished"]),
    },
    { key: "oem_number", label: "OEM-номер" },
    { key: "article_number", label: "Артикул" },
    {
      key: "unit_cost",
      label: "Собівартість одиниці, ₴",
      type: "number",
      min: 0,
    },
    {
      key: "selling_price",
      label: "Ціна продажу одиниці, ₴",
      type: "number",
      min: 0,
    },
    { key: "location", label: "Місце зберігання" },
    {
      key: "availability",
      label: "Перевірка наявності",
      options: choices(["unchecked", "present", "absent", "damaged"]),
    },
    {
      key: "individually_tracked",
      label: "Індивідуальний облік",
      type: "checkbox",
      hint: "Не більше 1 одиниці; потрібен унікальний серійний номер",
    },
    { key: "serial_number", label: "Серійний номер" },
    {
      key: "compatibility_notes",
      label: "Примітки щодо сумісності",
      type: "textarea",
      wide: true,
    },
    { key: "description", label: "Опис", type: "textarea", wide: true },
    {
      key: "internal_notes",
      label: "Внутрішні примітки",
      type: "textarea",
      wide: true,
    },
  ];
}
export default function Inventory({ notify }: { notify: Notify }) {
  const [params, setParams] = useSearchParams(),
    vehicleId = params.get("vehicle_id") || "";
  const [q, setQ] = useState(""),
    [availability, setAvailability] = useState(""),
    [category, setCategory] = useState(""),
    [condition, setCondition] = useState(""),
    [stockOnly, setStockOnly] = useState(false),
    [page, setPage] = useState(0),
    [edit, setEdit] = useState<Row | null>(null),
    [detail, setDetail] = useState<Row | null>(null),
    [confirm, setConfirm] = useState<Row | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [bulk, setBulk] = useState(false);
  const lookup = useLoad(
    () => Promise.all([all("/vehicles"), all("/categories")]),
    [],
  );
  const vehicles = lookup.data?.[0] || [],
    categories = lookup.data?.[1] || [];
  const query = new URLSearchParams({
    q,
    limit: "50",
    offset: String(page * 50),
    in_stock: String(stockOnly),
  });
  if (vehicleId) query.set("vehicle_id", vehicleId);
  if (availability) query.set("availability", availability);
  if (category) query.set("category_id", category);
  if (condition) query.set("condition", condition);
  const { data, error, loading, reload } = useLoad(
    () => api<Page>("/parts?" + query),
    [query.toString()],
  );
  useEffect(() => {
    setPage(0);
    setSelected([]);
  }, [q, vehicleId, availability, category, condition, stockOnly]);
  function refresh() {
    setSelected([]);
    reload();
  }
  return (
    <>
      <Heading
        eyebrow="СКЛАДСЬКИЙ ОБЛІК"
        title="Запчастини та залишки"
        description="Фактична наявність, резерви та розміщення кожної деталі."
      >
        <button
          disabled={lookup.loading || !!lookup.error}
          className="primary"
          onClick={() =>
            setEdit({
              condition: "used",
              availability: "unchecked",
              vehicle_id: vehicleId,
            })
          }
        >
          <Plus size={17} />
          Додати запчастину
        </button>
      </Heading>
      <div className="toolbar">
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Пошук запчастин"
            placeholder="Назва, OEM, артикул, місце…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select
          aria-label="Фільтр донора"
          value={vehicleId}
          onChange={(e) =>
            setParams(e.target.value ? { vehicle_id: e.target.value } : {})
          }
        >
          <option value="">Усі донори</option>
          {vehicles.map((v) => (
            <option key={v.id} value={v.id}>
              № {v.number ?? "—"} · {v.manufacturer} {v.model}
            </option>
          ))}
        </select>
        <select
          aria-label="Фільтр наявності"
          value={availability}
          onChange={(e) => setAvailability(e.target.value)}
        >
          <option value="">Будь-яка наявність</option>
          {choices(["unchecked", "present", "absent", "damaged"]).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="toolbar secondary-toolbar">
        <SlidersHorizontal size={16} />
        <select
          aria-label="Категорія запчастини"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">Усі категорії</option>
          {categories
            .filter((c) => c.kind !== "part")
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </select>
        <select
          aria-label="Стан запчастини"
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
        >
          <option value="">Будь-який стан</option>
          {choices(["used", "new", "damaged", "refurbished"]).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <label className="check-inline">
          <input
            type="checkbox"
            checked={stockOnly}
            onChange={(e) => setStockOnly(e.target.checked)}
          />
          Лише з залишком
        </label>
        <span className="muted">{data?.total || 0} позицій</span>
      </div>
      {selected.length > 0 && (
        <div className="selection-bar">
          <b>Обрано: {selected.length}</b>
          <button onClick={() => setBulk(true)}>Масова операція</button>
          <button onClick={() => setSelected([])}>Зняти вибір</button>
        </div>
      )}
      <State error={error || lookup.error} loading={loading} />
      <section className="panel">
        {data?.items.length ? (
          <>
            <div className="table-wrap desktop-table">
              <table>
                <thead>
                  <tr>
                    <th>
                      <input
                        aria-label="Обрати всі позиції сторінки"
                        type="checkbox"
                        checked={
                          data.items.length > 0 &&
                          data.items.every((p) => selected.includes(p.id))
                        }
                        onChange={(e) =>
                          setSelected(
                            e.target.checked ? data.items.map((p) => p.id) : [],
                          )
                        }
                      />
                    </th>
                    <th>Запчастина</th>
                    <th>Донор / місце</th>
                    <th>Залишок</th>
                    <th>Резерв</th>
                    <th>Доступно</th>
                    <th>Ціна</th>
                    <th>Наявність</th>
                    <th>Дії</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <input
                          aria-label={`Обрати ${p.name}`}
                          type="checkbox"
                          checked={selected.includes(p.id)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? [...selected, p.id]
                                : selected.filter((id) => id !== p.id),
                            )
                          }
                        />
                      </td>
                      <td>
                        <button
                          className="text-button strong"
                          onClick={() => setDetail(p)}
                        >
                          {p.name}
                        </button>
                        <small>
                          {p.oem_number ||
                            p.article_number ||
                            "Без OEM / артикула"}{" "}
                          · {labels[p.condition]}
                        </small>
                      </td>
                      <td>
                        {vehicles.find((v) => v.id === p.vehicle_id)
                          ?.number ? `№ ${vehicles.find((v) => v.id === p.vehicle_id)?.number}` : "—"}
                        <small>{p.location || "Місце не вказане"}</small>
                      </td>
                      <td>
                        <b>{p.quantity}</b>
                      </td>
                      <td>{p.reserved_quantity}</td>
                      <td>
                        <b className={p.available_quantity ? "available" : ""}>
                          {p.available_quantity}
                        </b>
                      </td>
                      <td>
                        {p.selling_price === null
                          ? "—"
                          : money(p.selling_price)}
                      </td>
                      <td>
                        <Badge value={p.availability} />
                      </td>
                      <td>
                        <div className="row-actions">
                          <button onClick={() => setEdit(p)}>Змінити</button>
                          <button onClick={() => setDetail(p)}>Операція</button>
                          <button
                            aria-label={`Архівувати ${p.name}`}
                            className="icon-button"
                            onClick={() => setConfirm(p)}
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
              {data.items.map((p) => (
                <article className="inventory-card" key={p.id}>
                  <div>
                    <div className="check-inline">
                      <input
                        aria-label={`Обрати ${p.name}`}
                        type="checkbox"
                        checked={selected.includes(p.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, p.id]
                              : selected.filter((id) => id !== p.id),
                          )
                        }
                      />
                      <button
                        className="text-button strong"
                        onClick={() => setDetail(p)}
                      >
                        {p.name}
                      </button>
                    </div>
                    <Badge value={p.availability} />
                  </div>
                  <p>
                    {p.oem_number || p.article_number || "Без OEM / артикула"} ·{" "}
                    {labels[p.condition]}
                  </p>
                  <small>
                    {vehicles.find((v) => v.id === p.vehicle_id)?.number ? `№ ${vehicles.find((v) => v.id === p.vehicle_id)?.number}` : "Без донора"}{" "}
                    · {p.location || "Місце не вказане"}
                  </small>
                  <div className="card-balances">
                    <span>
                      Залишок<b>{p.quantity}</b>
                    </span>
                    <span>
                      Резерв<b>{p.reserved_quantity}</b>
                    </span>
                    <span>
                      Доступно<b>{p.available_quantity}</b>
                    </span>
                    <span>
                      Ціна
                      <b>
                        {p.selling_price === null
                          ? "—"
                          : money(p.selling_price)}
                      </b>
                    </span>
                  </div>
                  <div className="card-actions">
                    <button onClick={() => setEdit(p)}>Змінити</button>
                    <button onClick={() => setDetail(p)}>Операція</button>
                    <button
                      aria-label={`Архівувати ${p.name}`}
                      onClick={() => setConfirm(p)}
                    >
                      <ArchiveIcon size={16} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <Pager
              total={data.total}
              page={page}
              setPage={(n) => {
                setPage(n);
                setSelected([]);
              }}
            />
          </>
        ) : (
          !loading && (
            <Empty
              title={
                q ||
                vehicleId ||
                category ||
                condition ||
                availability ||
                stockOnly
                  ? "Позицій за цими фільтрами немає"
                  : "Склад ще не заповнений"
              }
            >
              Додайте запчастину вручну або сформуйте чекліст у картці донора.
              Залишки з’являються тільки після надходження.
            </Empty>
          )
        )}
      </section>
      {edit && (
        <Modal
          title={edit.id ? "Картка запчастини" : "Нова запчастина"}
          onClose={() => setEdit(null)}
        >
          <div className="notice">
            Кількість змінюється лише складськими операціями. Нова позиція має
            нульовий залишок.
          </div>
          <RecordForm
            fields={partFields(vehicles, categories)}
            initial={edit}
            onSave={async (d) => {
              await api(
                "/parts" + (edit.id ? "/" + edit.id : ""),
                edit.id ? "PUT" : "POST",
                d,
              );
              setEdit(null);
              refresh();
              notify("Картку запчастини збережено");
            }}
          />
        </Modal>
      )}
      {detail && (
        <Modal title={detail.name} onClose={() => setDetail(null)}>
          <PartDetail
            part={detail}
            onChanged={() => {
              setDetail(null);
              refresh();
              notify("Складську операцію проведено");
            }}
          />
        </Modal>
      )}
      {confirm && (
        <Confirm
          title="Архівувати запчастину?"
          text="Історія та залишки будуть збережені. Позиції з активним резервом спершу потребують зняття резерву."
          onClose={() => setConfirm(null)}
          onConfirm={async () => {
            await api("/archive/parts/" + confirm.id, "POST");
            setConfirm(null);
            refresh();
          }}
        />
      )}
      {bulk && (
        <Modal
          title={`Масова операція · ${selected.length} позицій`}
          onClose={() => setBulk(false)}
        >
          <RecordForm
            fields={[
              {
                key: "action",
                label: "Операція",
                options: [
                  option("transfer", "Перемістити"),
                  option("archive", "Архівувати"),
                ],
              },
              {
                key: "location",
                label: "Нове місце зберігання",
                hint: "Обов’язково для переміщення",
              },
              { key: "reason", label: "Причина", required: true, wide: true },
            ]}
            onSave={async (d) => {
              await api("/parts/bulk-actions", "POST", { ...d, ids: selected });
              setBulk(false);
              refresh();
              notify("Масову операцію проведено");
            }}
          />
        </Modal>
      )}
    </>
  );
}
export function StockForm({ part, onDone }: { part: Row; onDone: () => void }) {
  const [type, setType] = useState("receipt");
  return (
    <>
      <div className="stock-summary">
        <span>
          Залишок<b>{part.quantity}</b>
        </span>
        <span>
          Резерв<b>{part.reserved_quantity}</b>
        </span>
        <span>
          Доступно<b>{part.available_quantity}</b>
        </span>
      </div>
      <label className="standalone-field">
        Тип операції
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {choices([
            "receipt",
            "write_off",
            "sale",
            "reserve",
            "release",
            "correction",
            "transfer",
          ]).map((o) => (
            <option value={o.value} key={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      {type === "correction" && (
        <p className="notice">
          Вкажіть новий абсолютний залишок, а не різницю. Він не може бути
          меншим за резерв.
        </p>
      )}
      <RecordForm
        key={type}
        fields={[
          type === "transfer"
            ? { key: "location", label: "Нове місце", required: true }
            : {
                key: "quantity",
                label: type === "correction" ? "Новий залишок" : "Кількість",
                type: "number",
                required: true,
                min: type === "correction" ? 0 : 1,
                max: 1000000,
              },
          {
            key: "reason",
            label: "Причина операції",
            required: true,
            wide: true,
          },
        ]}
        submit="Провести операцію"
        onSave={async (d) => {
          await api(`/parts/${part.id}/operations`, "POST", { ...d, type });
          onDone();
        }}
      />
    </>
  );
}
function PartDetail({ part, onChanged }: { part: Row; onChanged: () => void }) {
  const photos = useLoad(
      () => api<Row[]>(`/parts/${part.id}/photos`),
      [part.id],
    ),
    settings = useLoad(() => api("/settings"), []);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <dl className="details">
        {[
          ["OEM", part.oem_number || "—"],
          ["Артикул", part.article_number || "—"],
          ["Стан", labels[part.condition]],
          ["Серійний №", part.serial_number || "—"],
          ["Розміщення", part.location || "—"],
          [
            "Ціна",
            part.selling_price === null ? "—" : money(part.selling_price),
          ],
          ["Сумісність", part.compatibility_notes || "—"],
          ["Опис", part.description || "—"],
          ["Внутрішні примітки", part.internal_notes || "—"],
        ].map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <h3>Фото запчастини</h3>
      <State error={photos.error || settings.error} loading={photos.loading} />
      <div className="photos">
        {photos.data?.map((p) => (
          <a key={p.id} href={p.url} target="_blank" rel="noreferrer">
            <img alt={part.name} src={p.url} />
          </a>
        ))}
      </div>
      {settings.data?.photos_enabled ? (
        <label className="upload-inline">
          {busy ? "Завантаження…" : "Додати фото (JPEG, PNG, WebP до 5 МБ)"}
          <input
            aria-label="Фото запчастини"
            disabled={busy}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true);
              setError("");
              try {
                const fd = new FormData();
                fd.append("file", file);
                await api(`/parts/${part.id}/photos`, "POST", fd);
                photos.reload();
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
                e.target.value = "";
              }
            }}
          />
        </label>
      ) : (
        <p className="muted">
          Фото доступні після налаштування окремого сховища Warehouse.
        </p>
      )}
      {error && <div className="error">{error}</div>}
      <h3 className="divider-title">Нова складська операція</h3>
      <StockForm part={part} onDone={onChanged} />
    </>
  );
}
