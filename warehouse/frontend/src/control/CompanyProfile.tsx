import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Box, Plus, StickyNote } from "lucide-react";
import { api, date, money, reasonName, type Row, type Staff } from "./api";
import { profileHref, sections, type Section } from "./model";
import {
  Badge,
  Empty,
  Feedback,
  PageHeader,
  Panel,
  PeriodBadge,
  useLoad,
  useRevision,
} from "./shared";
import { managerName } from "./Directory";
import { TaskComposer } from "./Tasks";
const titles: Record<Section, string> = {
  overview: "Огляд",
  products: "Продукти",
  people: "Працівники",
  finance: "Фінанси",
  activity: "Активність",
  notes: "Нотатки",
  history: "Історія",
};
function Quota({ company: c }: { company: Row }) {
  const rows = [
    {
      label: "Тарифна місткість автомобілів",
      used: c.usage?.vehicles,
      limit: c.access_incomplete ? null : c.access?.vehicle_capacity,
      note: "Квотні одиниці, а не всі автомобілі в історії",
    },
    {
      label: "Активні працівники",
      used: c.usage?.employees,
      limit: c.access_incomplete ? null : c.access?.employee_seats,
      note: "Без власника · лише активні облікові записи",
    },
  ];
  return (
    <div className="cc-panel-body">
      {rows.map((r) => {
        const known = typeof r.used === "number" && typeof r.limit === "number",
          over = known && r.used > r.limit,
          width = known
            ? r.limit > 0
              ? Math.min(100, (r.used / r.limit) * 100)
              : r.used > 0
                ? 100
                : 0
            : 0;
        return (
          <div className={"cc-quota " + (over ? "over" : "")} key={r.label}>
            <h3>{r.label}</h3>
            <strong>
              {r.used ?? "—"} <span>/ {r.limit ?? "—"}</span>
            </strong>
            <div className="cc-quota-track" aria-hidden="true">
              <div style={{ width: width + "%" }} />
            </div>
            <small>{r.note}</small>
            {over && <small>Понад ліміт на {r.used - r.limit}</small>}
          </div>
        );
      })}
      <p className="cc-quota-help">
        <AlertTriangle size={16} />
        <span>
          Квоту займають неархівні авто та донори із залишками або резервом,
          зокрема архівні. Кожен донор враховується один раз.
        </span>
      </p>
      <p className="cc-caption">
        Чинні додаткові пакети входять у дозволену місткість. Перевищення не є
        доказом несплати.
      </p>
    </div>
  );
}
function BusinessActivity({ company: c }: { company: Row }) {
  return (
    <Panel
      title="Бізнес-активність"
      subtitle="Час останньої складської операції"
    >
      {c.business_activity_at ? (
        <div className="cc-panel-body">
          <strong>{date(c.business_activity_at)}</strong>
          <p>Детальну стрічку подій не підключено.</p>
        </div>
      ) : (
        <Empty title="Операцію не зафіксовано">
          Відсутність запису не доводить, що клієнт неактивний.
        </Empty>
      )}
      <p className="cc-panel-foot">
        {c.business_activity_coverage === "warehouse stock operations only"
          ? "Покриття: складські операції Warehouse."
          : "Покриття бізнес-активності неповне."}{" "}
        Останній вхід показано окремо в розділі працівників.
      </p>
    </Panel>
  );
}
function People({ company }: { company: Row }) {
  const roles: Record<string, string> = {
    DIRECTOR: "Власник",
    MANAGER: "Менеджер",
    WORKER: "Працівник",
  };
  return (
    <Panel
      title="Власник і працівники"
      subtitle="Власник не займає місце працівника"
    >
      {Array.isArray(company.people) && company.people.length ? (
        <>
          <table className="cc-team-table">
            <thead>
              <tr>
                <th>Учасник</th>
                <th>Роль</th>
                <th>Стан облікового запису</th>
                <th>Останній вхід</th>
              </tr>
            </thead>
            <tbody>
              {company.people.map((p: Row) => (
                <tr key={p.id}>
                  <td>
                    {p.name || "Ім’я недоступне"}
                    <small>{p.email}</small>
                  </td>
                  <td>{roles[p.role] || p.role}</td>
                  <td>
                    <Badge tone={p.active ? "good" : "neutral"}>
                      {p.active ? "Активний" : "Вимкнений"}
                    </Badge>
                  </td>
                  <td>{date(p.last_login_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="cc-team-cards">
            {company.people.map((p: Row) => (
              <article className="cc-client-card" key={p.id}>
                <h3>{p.name || "Ім’я недоступне"}</h3>
                <p className="cc-wrap">{p.email}</p>
                <div className="cc-card-data">
                  <div>
                    <small>Роль</small>
                    {roles[p.role] || p.role}
                  </div>
                  <div>
                    <small>Останній вхід</small>
                    {date(p.last_login_at)}
                  </div>
                </div>
                <div className="cc-tagline">
                  <Badge tone={p.active ? "good" : "neutral"}>
                    {p.active ? "Активний" : "Вимкнений"}
                  </Badge>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : (
        <Empty title="Дані про працівників недоступні" />
      )}
      <p className="cc-panel-foot">
        Останній вхід — авторизація, а не підтвердження бізнес-дії.
      </p>
    </Panel>
  );
}
function Notes({ id, staff }: { id: string; staff: Staff }) {
  const [revision, refresh] = useRevision(),
    request = useLoad<Row[]>(
      "/companies/" + encodeURIComponent(id) + "/notes",
      revision,
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Panel
      title="Внутрішні нотатки"
      subtitle="Лише для команди · не надсилаються клієнту"
    >
      <div className="cc-panel-body">
        <Feedback
          loading={request.loading}
          error={request.error}
          retry={refresh}
        />
        {request.data &&
          (request.data.length ? (
            request.data.map((n) => (
              <article className="cc-note" key={n.id}>
                <p>{n.text}</p>
                <small>{date(n.created_at)}</small>
                {(n.staff_id === staff.id || ["Owner", "Administrator", "Moderator"].includes(staff.role)) && <details>
                  <summary>Редагувати нотатку</summary>
                  <form className="cc-form" onSubmit={async e => {
                    e.preventDefault(); setBusy(true); setError("");
                    const text = new FormData(e.currentTarget).get("text");
                    try { await api(`/companies/${encodeURIComponent(id)}/notes/${n.id}`, "PATCH", { text }); refresh(); }
                    catch(e) { setError((e as Error).message); } finally { setBusy(false); }
                  }}>
                    <label>Текст нотатки<textarea name="text" defaultValue={n.text} required maxLength={4000} /></label>
                    <button disabled={busy}>Зберегти зміни нотатки</button>
                  </form>
                </details>}
              </article>
            ))
          ) : (
            <Empty title="Нотаток поки немає" />
          ))}
        <form
          className="cc-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget,
              text = new FormData(form).get("text");
            setBusy(true);
            setError("");
            try {
              await api(
                "/companies/" + encodeURIComponent(id) + "/notes",
                "POST",
                { text },
              );
              form.reset();
              refresh();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Нова нотатка
            <textarea name="text" required maxLength={4000} />
          </label>
          <Feedback error={error} />
          <button className="cc-primary" disabled={busy}>
            {busy ? "Зберігаємо…" : "Зберегти нотатку"}
          </button>
        </form>
      </div>
    </Panel>
  );
}
function Finance({ id }: { id: string }) {
  const [value, setValue] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Panel
      title="Фінансовий контекст"
      subtitle="Наявний дозволений read-only контекст · без операцій із коштами"
    >
      <div className="cc-panel-body">
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            setValue(null);
            try {
              setValue(
                await api("/companies/" + encodeURIComponent(id) + "/finance"),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Оновити фінансовий контекст
        </button>
        <Feedback loading={busy} error={error} />
        {!value && !busy && !error && (
          <Empty title="Фінансовий контекст ще не завантажено">
            Чинний тарифний період не доводить оплату. Для перевірки
            скористайтеся наявним дозволеним джерелом.
          </Empty>
        )}
        {value &&
          (value.state === "fresh" ? (
            <>
              <p>
                Останні доступні записи · {value.environment}. Підсумки з
                неповної історії не обчислюються.
              </p>
              {Object.entries({
                invoices: "Рахунки",
                paid_periods: "Оплачені періоди",
                payments: "Підтверджені платежі",
                reversals: "Повернення",
                reviews: "Потребують звірки",
              }).map(([key, label]) => (
                <section className="cc-finance-section" key={key}>
                  <h3>{label}</h3>
                  {value[key]?.length ? (
                    value[key].map((r: Row) => (
                      <article className="cc-finance-record" key={r.id}>
                        <strong>{r.status || r.reason || "Запис"}</strong>
                        {!["reviews", "paid_periods"].includes(key) && (
                          <span>{money(r)}</span>
                        )}
                        <small>
                          {date(
                            r.created_at || r.starts_at || r.effective_from,
                          )}
                          {(r.ends_at || r.effective_until) &&
                            " → " + date(r.ends_at || r.effective_until)}
                        </small>
                      </article>
                    ))
                  ) : (
                    <p>У доступній вибірці записів немає.</p>
                  )}
                </section>
              ))}
            </>
          ) : (
            <Empty title="Фінансове джерело недоступне">
              {reasonName[value.reason] ||
                "Дані не підтверджено. Невідомі значення не замінюються нулями."}
            </Empty>
          ))}
      </div>
    </Panel>
  );
}
function Assignment({
  company,
  staffOptions,
  error: staffError,
  onSaved,
}: {
  company: Row;
  staffOptions: Staff[];
  error: string;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  return (
    <Panel title="Призначення менеджера або доступу">
      <div className="cc-panel-body">
        <Feedback error={staffError} />
        <form
          className="cc-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            setNotice("");
            const staff_id = new FormData(e.currentTarget).get("staff_id");
            try {
              await api(
                "/companies/" + encodeURIComponent(company.id) + "/assign",
                "POST",
                { staff_id },
              );
              setNotice("Призначення збережено");
              onSaved();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Співробітник
            <select
              name="staff_id"
              defaultValue={company.manager_id || ""}
              required
            >
              <option value="" disabled>
                Оберіть співробітника
              </option>
              {staffOptions
                .filter(
                  (s) => s.active && ["Manager", "Support"].includes(s.role),
                )
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.username} ·{" "}
                    {s.role === "Manager" ? "Менеджер" : "Підтримка"}
                  </option>
                ))}
            </select>
          </label>
          <p className="cc-caption">
            Менеджер замінює відповідального; підтримка отримує доступ до
            контексту компанії.
          </p>
          <button
            disabled={
              busy ||
              !staffOptions.some(
                (s) => s.active && ["Manager", "Support"].includes(s.role),
              )
            }
          >
            Призначити
          </button>
          <Feedback error={error} />
          {notice && <p role="status">{notice}</p>}
        </form>
      </div>
    </Panel>
  );
}
export default function CompanyProfile({
  id,
  section,
  staff,
  staffOptions,
  staffError,
  revision,
}: {
  id: string;
  section: Section;
  staff: Staff;
  staffOptions: Staff[];
  staffError: string;
  revision: number;
}) {
  const [localRevision, reload] = useRevision(),
    request = useLoad<Row>(
      "/companies/" + encodeURIComponent(id),
      revision + localRevision,
    ),
    [taskOpen, setTaskOpen] = useState(false),
    [taskNotice, setTaskNotice] = useState(""),
    tabs = useRef<HTMLElement>(null),
    heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (request.data && document.activeElement === document.body)
      heading.current?.focus({ preventScroll: true });
    const selected = tabs.current?.querySelector(
      "[aria-current=page]",
    ) as HTMLElement | null;
    if (selected && tabs.current) {
      const el = tabs.current;
      el.scrollLeft = selected.offsetLeft - el.offsetLeft - 12;
    }
  }, [section, request.data]);
  const c = request.data;
  return (
    <>
      <a className="cc-back" href="#/clients">
        ← Усі клієнти
      </a>
      <Feedback
        loading={request.loading}
        error={request.error}
        retry={reload}
      />
      {!c && <PageHeader title="Профіль клієнта" />}
      {taskNotice && (
        <p role="status">
          {taskNotice} <a href="#/queue">Відкрити чергу →</a>
        </p>
      )}
      {c && (
        <>
          <div className="cc-profile-head">
            <span className="cc-company-logo large">
              <Box size={23} />
            </span>
            <div>
              <small className="cc-eyebrow">ПРОФІЛЬ КЛІЄНТА</small>
              <h1 ref={heading} tabIndex={-1}>
                {c.display_name}
              </h1>
              <p>
                {c.owner_name || "Основний контакт недоступний"} ·{" "}
                {c.owner_email || "Email недоступний"}
              </p>
            </div>
            <div className="cc-actions">
              <a className="cc-button" href={profileHref(id, "notes")}>
                <StickyNote size={16} /> Нотатка
              </a>
              <button className="cc-primary" onClick={() => setTaskOpen(true)}>
                <Plus size={16} /> Завдання
              </button>
            </div>
          </div>
          {c.state === "stale" && (
            <p className="cc-stale" role="status">
              Дані профілю застаріли · отримано {date(c.fetched_at)}
            </p>
          )}
          <div className="cc-profile-summary">
            <div>
              <small>Тарифний період</small>
              <PeriodBadge company={c} />
            </div>
            <div>
              <small>Операційний доступ</small>
              <strong>Потребує перевірки</strong>
            </div>
            <div>
              <small>Тариф Warehouse</small>
              <strong>
                {c.access_incomplete
                  ? "Недостатньо даних"
                  : c.access?.plan || "Не визначено"}
              </strong>
            </div>
            <div>
              <small>Оплата</small>
              <strong>Не підтверджено джерелом</strong>
            </div>
          </div>
          <nav
            ref={tabs}
            className="cc-profile-tabs"
            aria-label="Розділи профілю"
          >
            {sections.map((key) =>
              key === "finance" && !staff.can_finance ? (
                <span key={key} className="cc-restricted">
                  Фінанси · немає доступу
                </span>
              ) : (
                <a
                  key={key}
                  href={profileHref(id, key)}
                  aria-current={section === key ? "page" : undefined}
                >
                  {titles[key]}
                </a>
              ),
            )}
          </nav>
          {section === "overview" && (
            <div className="cc-profile-grid">
              <div>
                <Panel
                  title="Використання тарифу"
                  subtitle="Warehouse · поточний тарифний контекст"
                >
                  <Quota company={c} />
                </Panel>
                <BusinessActivity company={c} />
              </div>
              <div>
                <Panel title="Відповідальний і контекст">
                  <dl className="cc-keyvalues cc-panel-body">
                    <dt>Менеджер</dt>
                    <dd>{managerName(c.manager_id, staff, staffOptions)}</dd>
                    <dt>Реєстрація</dt>
                    <dd>{date(c.registered_at)}</dd>
                    <dt>Дані отримано</dt>
                    <dd>{date(c.fetched_at)}</dd>
                  </dl>
                </Panel>
                <Panel title="Підключені продукти">
                  <div className="cc-panel-body">
                    <h3>Warehouse</h3>
                    <a href={profileHref(id, "products")}>
                      Деталі підключення →
                    </a>
                  </div>
                </Panel>
                {staff.can_assign && (
                  <Assignment
                    company={c}
                    staffOptions={staffOptions}
                    error={staffError}
                    onSaved={reload}
                  />
                )}
              </div>
            </div>
          )}
          {section === "products" && (
            <Panel title="Продукти клієнта">
              <div className="cc-panel-body">
                {c.links?.length ? (
                  c.links.map((l: Row) => (
                    <div
                      className="cc-product-row"
                      key={l.system + ":" + l.entity_type + ":" + l.source_id}
                    >
                      <strong>
                        {l.system === "warehouse"
                          ? "Warehouse"
                          : l.system === "billing"
                            ? "Фінансовий зв’язок"
                            : l.system}
                      </strong>
                      <Badge
                        tone={
                          l.status === "verified"
                            ? "good"
                            : l.status === "conflict"
                              ? "warn"
                              : "neutral"
                        }
                      >
                        {l.status === "verified"
                          ? "Перевірено"
                          : l.status === "conflict"
                            ? "Потребує перевірки"
                            : "Не підтверджено"}
                      </Badge>
                    </div>
                  ))
                ) : (
                  <p>Зв’язки продуктів не підтверджено.</p>
                )}
                <a href={profileHref(id)}>Переглянути ліміти в огляді →</a>
              </div>
              {["Telegram / Garage", "Sites", "Реферальна програма"].map(
                (p) => (
                  <div className="cc-product-row cc-planned" key={p}>
                    <span>{p}</span>
                    <Badge>Інтеграцію не підключено</Badge>
                  </div>
                ),
              )}
            </Panel>
          )}
          {section === "people" && <People company={c} />}{" "}
          {section === "finance" &&
            (staff.can_finance ? (
              <Finance key={id} id={id} />
            ) : (
              <Empty title="Фінансовий контекст недоступний вашій ролі" />
            ))}
          {section === "activity" && <BusinessActivity company={c} />}{" "}
          {section === "notes" && <Notes key={id} id={id} staff={staff} />}{" "}
          {section === "history" && (
            <Panel title="Історія змін профілю">
              <Empty title="Повну історію змін ще не підключено">
                Внутрішні нотатки доступні у своєму розділі. Журнал інших
                staff-подій не підміняє історію цієї компанії.
              </Empty>
            </Panel>
          )}
          {taskOpen && (
            <TaskComposer
              companyId={id}
              companyName={c.display_name}
              staff={staff}
              onClose={() => setTaskOpen(false)}
              onSaved={() => setTaskNotice("Завдання збережено")}
            />
          )}
        </>
      )}
    </>
  );
}
