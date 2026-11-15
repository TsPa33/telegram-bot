import { useEffect, useRef, useState } from "react";
import { State } from "../shared";
import {
  api,
  date,
  money,
  states,
  reasonName,
  type Row,
  type Staff,
} from "./api";

export default function CompanyPreview({
  id,
  staff,
  close,
  changed,
}: {
  id: string;
  staff: Staff;
  close: () => void;
  changed: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const launcher = useRef(document.activeElement as HTMLElement | null);
  const [company, setCompany] = useState<Row | null>(null);
  const [notes, setNotes] = useState<Row[]>([]);
  const [finance, setFinance] = useState<Row | null>(null);
  const [people, setPeople] = useState<Staff[]>([]);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      launcher.current?.focus();
    };
  }, []);
  useEffect(() => {
    let current = true;
    Promise.all([
      api("/companies/" + id),
      api("/companies/" + id + "/notes"),
      staff.can_assign ? api("/staff") : Promise.resolve([]),
    ])
      .then(([c, n, s]) => {
        if (current) {
          setCompany(c);
          setNotes(n);
          setPeople(s);
        }
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [id, staff.can_assign]);
  async function work(
    action: () => Promise<unknown>,
    message = "Збережено лише у внутрішньому Control Center",
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
      changed();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="cc-preview"
      aria-labelledby="company-title"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <header>
        <button
          className="cc-close"
          onClick={close}
          aria-label="Закрити профіль"
        >
          Закрити ×
        </button>
        <small>WAREHOUSE / КОМПАНІЯ</small>
        <h2 id="company-title">
          {company?.display_name || "Профіль компанії"}
        </h2>
      </header>
      <State error={error} loading={!company && !error} />
      {notice && <p role="status">{notice}</p>}
      {company && (
        <>
          <p>
            <span className="cc-badge">{company.environment}</span>{" "}
            {company.state === "stale" ? "Дані потребують оновлення" : "Оновлено"} ·{" "}
            {date(company.fetched_at)}
          </p>
          <section>
            <h3>Доступ і ліміти</h3>
            <p>
              {company.access_incomplete
                ? "Дані про тариф ще не отримано."
                : `${states[company.access.status] || company.access.status} · ${company.access.plan || "Тариф невідомий"}`}
            </p>
            <p>Завершення періоду: {date(company.access.period_end)}</p>
            <dl>
              <dt>Автомобілі / місткість</dt>
              <dd>
                {company.usage?.vehicles ?? "—"} /{" "}
                {company.access_incomplete
                  ? "—"
                  : company.access.vehicle_capacity}
              </dd>
              <dt>Працівники / місця</dt>
              <dd>
                {company.usage?.employees ?? "—"} /{" "}
                {company.access_incomplete
                  ? "—"
                  : company.access.employee_seats}
              </dd>
            </dl>
            <p>
              Бізнес-активність: {date(company.business_activity_at)}
              <small>
                {company.business_activity_coverage ===
                "warehouse stock operations only"
                  ? "Лише складські операції Warehouse"
                  : "Покриття активності неповне"}
              </small>
            </p>
          </section>
          <section>
            <h3>Власник і працівники</h3>
            {company.people.map((p: Row) => (
              <article key={p.id}>
                <strong>{p.name}</strong>
                <span>
                  {({DIRECTOR:"Власник",MANAGER:"Менеджер",WORKER:"Працівник"} as Record<string,string>)[p.role] || p.role} · {p.active ? "Активний" : "Вимкнений"}
                </span>
                <span>{p.email}</span>
                <small>
                  Останній вхід: {date(p.last_login_at)}. Вхід не означає
                  бізнес-активність.
                </small>
              </article>
            ))}
          </section>
          <section>
            <h3>Підключені продукти</h3>
            {company.links.map((l: Row) => (
              <p key={l.system + l.entity_type}>
                {l.system === "warehouse" ? "Warehouse" : l.system === "billing" ? "Оплати" : l.system} · <strong>{l.status==="verified"?"Підключено":l.status==="conflict"?"Потребує перевірки":"Не підключено"}</strong>
              </p>
            ))}
            {!company.links.some((l: Row) => l.system === "billing") && (
              <p>Фінансовий акаунт ще не підключено.</p>
            )}
          </section>
          {staff.can_assign && (
            <section>
              <h3>Відповідальний / доступ</h3>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  void work(async () => {
                    await api("/companies/" + id + "/assign", "POST", {
                      staff_id: data.get("staff_id"),
                    });
                    setCompany(await api("/companies/" + id));
                  });
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
                    {people
                      .filter((p) => p.active && ["Manager", "Support"].includes(p.role))
                      .map((p) => (
                        <option value={p.id} key={p.id}>
                          {p.username} · {p.role}
                        </option>
                      ))}
                  </select>
                </label>
                <button disabled={busy}>Призначити</button>
              </form>
            </section>
          )}
          <section>
            <h3>Фінанси · лише перегляд</h3>
            {!staff.can_finance ? (
              <p>Фінансові суми недоступні. Статус доступу показано вище.</p>
            ) : (
              <>
                <button
                  disabled={busy}
                  onClick={() =>
                    void work(
                      async () =>
                        setFinance(await api("/companies/" + id + "/finance")),
                      "Фінансовий контекст оновлено",
                    )
                  }
                >
                  Оновити фінансовий контекст
                </button>
                {finance &&
                  (finance.state === "fresh" ? (
                    <>
                      <p>
                        {finance.environment} · останні доступні записи.
                        Підсумки з неповної історії не обчислюються.
                      </p>
                      {Object.entries({
                        invoices: "Рахунки",
                        paid_periods: "Оплачені періоди",
                        payments: "Підтверджені платежі",
                        reversals: "Повернення / reversals",
                        reviews: "Потребують звірки",
                      }).map(([key, title]) => (
                        <div key={key}>
                          <h4>{title}</h4>
                          {finance[key]?.length ? (
                            finance[key].map((r: Row) => (
                              <article key={r.id}>
                                <strong>{r.status || r.reason || r.id}</strong>
                                {key !== "reviews" &&
                                  key !== "paid_periods" && (
                                    <span>{money(r)}</span>
                                  )}
                                <small>
                                  {date(
                                    r.created_at ||
                                      r.starts_at ||
                                      r.effective_from,
                                  )}
                                  {(r.ends_at || r.effective_until) &&
                                    " → " +
                                      date(r.ends_at || r.effective_until)}
                                </small>
                              </article>
                            ))
                          ) : (
                            <p>Записів немає в доступній вибірці.</p>
                          )}
                        </div>
                      ))}
                    </>
                  ) : (
                    <p role="status">
                      Недоступно:{" "}
                      {reasonName[finance.reason] || "Джерело недоступне"} ·{" "}
                      {finance.environment || "Environment невідомий"}
                    </p>
                  ))}
              </>
            )}
          </section>
          <section>
            <h3>Внутрішні нотатки</h3>
            <p>Ніколи не надсилаються клієнтам.</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget,
                  text = new FormData(form).get("text");
                void work(async () => {
                  await api("/companies/" + id + "/notes", "POST", { text });
                  setNotes(await api("/companies/" + id + "/notes"));
                  form.reset();
                });
              }}
            >
              <label>
                Нова нотатка
                <textarea name="text" required maxLength={4000} />
              </label>
              <button disabled={busy}>Зберегти нотатку</button>
            </form>
            {notes.map((n) => (
              <article key={n.id}>
                <p className="cc-note">{n.text}</p>
                <small>{date(n.created_at)}</small>
              </article>
            ))}
          </section>
          <section>
            <h3>Наступна внутрішня дія</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget,
                  data = new FormData(form),
                  due = String(data.get("due") || "");
                void work(async () => {
                  await api("/companies/" + id + "/tasks", "POST", {
                    next_action: data.get("action"),
                    status: "open",
                    due_at: due ? new Date(due).toISOString() : null,
                  });
                  form.reset();
                });
              }}
            >
              <label>
                Дія
                <input name="action" required maxLength={500} />
              </label>
              <label>
                Строк · локальний час пристрою
                <input name="due" type="datetime-local" />
              </label>
              <button disabled={busy}>Додати до моєї черги</button>
            </form>
          </section>
        </>
      )}
    </dialog>
  );
}
