import { useState, type MouseEvent } from "react";
import { Box } from "lucide-react";
import { date, states, type Row, type Staff } from "./api";
import {
  directoryQuery,
  filterKeys,
  nextDirectoryHref,
  profileHref,
  type Route,
} from "./model";
import {
  Badge,
  Empty,
  Feedback,
  Freshness,
  PageHeader,
  PeriodBadge,
  ProductBadge,
  useLoad,
  useRevision,
} from "./shared";
export function managerName(id: string | null, staff: Staff, options: Staff[]) {
  return !id
    ? "Не призначено"
    : id === staff.id
      ? staff.username
      : options.find((s) => s.id === id)?.username || "Призначено";
}
export function ClientCollection({
  items,
  staff,
  staffOptions,
}: {
  items: Row[];
  staff: Staff;
  staffOptions: Staff[];
}) {
  const open = (e: MouseEvent<HTMLTableRowElement>, id: string) => {
    if (
      !(e.target as HTMLElement).closest("a,button,input,select") &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.shiftKey
    )
      location.hash = profileHref(id);
  };
  return (
    <>
      <table className="cc-client-table">
        <thead>
          <tr>
            <th>Компанія / клієнт</th>
            <th>Основний контакт</th>
            <th>Продукти</th>
            <th>Тариф</th>
            <th>Тарифний стан</th>
            <th>Реєстрація</th>
            <th>Бізнес-активність</th>
            <th>Відповідальний</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} data-client={c.id} onClick={(e) => open(e, c.id)}>
              <td>
                <a className="cc-company-link" href={profileHref(c.id)}>
                  <span className="cc-company-logo">
                    <Box size={17} />
                  </span>
                  {c.display_name}
                </a>
                {c.state === "stale" && (
                  <small>Дані потребують оновлення</small>
                )}
              </td>
              <td>
                {c.owner_name || "Контакт недоступний"}
                <small>{c.owner_email || "Email недоступний"}</small>
              </td>
              <td>
                <ProductBadge />
              </td>
              <td>
                {c.access_incomplete
                  ? "Немає даних"
                  : c.access?.plan || "Не визначено"}
              </td>
              <td>
                <PeriodBadge company={c} />
              </td>
              <td>{date(c.registered_at)}</td>
              <td>
                {date(c.business_activity_at)}
                <small>Складські операції</small>
              </td>
              <td>{managerName(c.manager_id, staff, staffOptions)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="cc-client-cards cc-responsive-cards">
        {items.map((c) => (
          <a
            className="cc-client-card"
            aria-label={c.display_name}
            key={c.id}
            href={profileHref(c.id)}
          >
            <h3>
              <span className="cc-company-logo">
                <Box size={17} />
              </span>
              {c.display_name}
            </h3>
            <div className="cc-card-data">
              <div>
                <small>Основний контакт</small>
                {c.owner_name || "Недоступний"}
                <small>{c.owner_email || "Email недоступний"}</small>
              </div>
              <div>
                <small>Тариф</small>
                {c.access_incomplete
                  ? "Немає даних"
                  : c.access?.plan || "Не визначено"}
              </div>
              <div>
                <small>Бізнес-активність</small>
                {date(c.business_activity_at)}
              </div>
              <div>
                <small>Відповідальний</small>
                {managerName(c.manager_id, staff, staffOptions)}
              </div>
              <div>
                <small>Реєстрація</small>
                {date(c.registered_at)}
              </div>
            </div>
            <div className="cc-tagline">
              <PeriodBadge company={c} />
              <ProductBadge />
              {c.state === "stale" && <Badge tone="warn">Дані застаріли</Badge>}
            </div>
          </a>
        ))}
      </div>
    </>
  );
}
export default function Directory({
  route,
  staff,
  staffOptions,
  staffError,
  revision,
}: {
  route: Route;
  staff: Staff;
  staffOptions: Staff[];
  staffError: string;
  revision: number;
}) {
  const [localRevision, retry] = useRevision();
  const query = directoryQuery(route.query),
    request = useLoad<Row>("/companies?" + query, revision + localRevision);
  const [draft, setDraft] = useState(() =>
    Object.fromEntries(filterKeys.map((k) => [k, route.query.get(k) || ""])),
  );
  function apply() {
    const next = new URLSearchParams();
    for (const k of filterKeys) if (draft[k]) next.set(k, draft[k]);
    location.hash = "#/clients?" + next;
  }
  return (
    <>
      <PageHeader
        title="Клієнти"
        subtitle="Доступні вам компанії Warehouse та їхній тарифний контекст."
        action={<ProductBadge />}
      />
      <form
        className="cc-filters"
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <label className="cc-search">
          Пошук
          <input
            aria-label="Пошук клієнта"
            placeholder="Компанія або email власника"
            maxLength={120}
            value={draft.q}
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
          />
        </label>
        <label>
          Тариф
          <select
            value={draft.plan}
            onChange={(e) => setDraft({ ...draft, plan: e.target.value })}
          >
            <option value="">Усі тарифи</option>
            <option value="standard">Standard</option>
            <option value="premium">Premium</option>
          </select>
        </label>
        <label>
          Тарифний стан
          <select
            value={draft.status}
            onChange={(e) => setDraft({ ...draft, status: e.target.value })}
          >
            <option value="">Усі стани</option>
            {Object.entries(states).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Фінансовий зв’язок
          <select
            value={draft.linking}
            onChange={(e) => setDraft({ ...draft, linking: e.target.value })}
          >
            <option value="">Усі</option>
            <option value="linked">Перевірений</option>
            <option value="unlinked">Не підтверджено</option>
            <option value="conflict">Конфлікт</option>
          </select>
        </label>
        {staff.can_assign && (
          <label>
            Менеджер
            <select
              value={draft.manager}
              onChange={(e) => setDraft({ ...draft, manager: e.target.value })}
            >
              <option value="">Усі</option>
              {staffOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.username}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Зареєстровано від · Київ
          <input
            type="date"
            value={draft.registered_from}
            onChange={(e) =>
              setDraft({ ...draft, registered_from: e.target.value })
            }
          />
        </label>
        <label>
          Сортування
          <select
            value={draft.sort || "name"}
            onChange={(e) => setDraft({ ...draft, sort: e.target.value })}
          >
            <option value="name">За назвою</option>
            <option value="registered">За датою реєстрації ↑</option>
          </select>
        </label>
        <button className="cc-primary">Застосувати</button>
        <a className="cc-button" href="#/clients">
          Скинути
        </a>
      </form>
      <Feedback
        error={
          staffError
            ? "Не вдалося завантажити відповідальних: " + staffError
            : ""
        }
      />
      <Feedback loading={request.loading} error={request.error} retry={retry} />
      {request.data && (
        <>
          <Freshness source={request.data.source} />
          <div className="cc-table-panel">
            {request.data.items.length ? (
              <ClientCollection
                items={request.data.items}
                staff={staff}
                staffOptions={staffOptions}
              />
            ) : (
              <Empty title="Клієнтів за цими умовами немає">
                Спробуйте інший пошук або змініть фільтри.
              </Empty>
            )}
          </div>
          <div className="cc-pagination">
            <span>
              У цій вибірці: {request.data.items.length} · до 20 записів на
              сторінці
            </span>
            <div>
              <>
                {route.query.get("cursor") ? (
                  <a
                    className="cc-button"
                    href={nextDirectoryHref(route.query)}
                  >
                    На початок
                  </a>
                ) : (
                  <span className="cc-button disabled" aria-disabled="true">
                    На початок
                  </span>
                )}
              </>
              {request.data.next_cursor ? (
                <a
                  className="cc-button"
                  href={nextDirectoryHref(
                    route.query,
                    request.data.next_cursor,
                  )}
                >
                  Наступні →
                </a>
              ) : (
                <span className="cc-muted">Кінець вибірки</span>
              )}
            </div>
          </div>
        </>
      )}
      <p className="cc-caption">
        Тарифний стан не підтверджує оплату. Бізнес-активність охоплює лише
        складські операції; останній вхід показано окремо у профілі.
      </p>
    </>
  );
}
