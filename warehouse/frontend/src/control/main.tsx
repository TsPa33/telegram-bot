import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider, ThemeSwitch } from "../Theme";
import { State } from "../shared";
import CompanyPreview from "./CompanyPreview";
import { api, date, states, coverageName, type Row, type Staff } from "./api";
import "../tokens.css";
import "../themes.css";
import "./style.css";

function Login({ onLogin }: { onLogin: (s: Staff) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="cc-login">
      <section>
        <small>CARPOT / STAFF</small>
        <h1>Control Center</h1>
        <p>
          Окремий доступ персоналу. Акаунт Warehouse не надає адміністративних
          прав.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.currentTarget));
            setBusy(true);
            setError("");
            try {
              const result = await api("/auth/login", "POST", data);
              sessionStorage.setItem("control.csrf", result.csrf);
              onLogin(result.staff);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Staff логін
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={120}
            />
          </label>
          <label>
            Пароль
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
            />
          </label>
          <label>
            MFA-код
            <input
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              required
            />
          </label>
          <State loading={busy} error={error} />
          <button disabled={busy}>{busy ? "Перевіряємо…" : "Увійти"}</button>
        </form>
        <small>Доступ створює оператор. Публічної реєстрації немає.</small>
      </section>
    </main>
  );
}
const initialFilters = {
  q: "",
  plan: "",
  status: "",
  linking: "",
  manager: "",
  sort: "name",
  registered_from: "",
};
function Workspace({ staff, logout }: { staff: Staff; logout: () => void }) {
  const [tab, setTab] = useState("overview"),
    [overview, setOverview] = useState<Row | null>(null),
    [page, setPage] = useState<Row | null>(null);
  const [tasks, setTasks] = useState<Row[]>([]),
    [staffOptions, setStaffOptions] = useState<Staff[]>([]),
    [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [revision, setRevision] = useState(0);
  const [filters, setFilters] = useState(initialFilters),
    [applied, setApplied] = useState(initialFilters),
    [cursor, setCursor] = useState("");
  const refresh = () => setRevision((v) => v + 1);
  useEffect(() => {
    if (staff.can_assign)
      api("/staff")
        .then(setStaffOptions)
        .catch((e) => setError(e.message));
  }, [staff.can_assign]);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    const query = new URLSearchParams(
      Object.entries(applied).filter(([, value]) => value),
    );
    if (cursor) query.set("cursor", cursor);
    // Preserve successful sections when another source temporarily fails.
    Promise.allSettled([api("/overview"), api("/companies?" + query), api("/tasks")])
      .then(([o, p, t]) => {
        if (!current) return;
        if (o.status === "fulfilled") setOverview(o.value);
        if (p.status === "fulfilled") setPage(p.value);
        if (t.status === "fulfilled") setTasks(t.value);
        const failed = [o, p, t].find((item) => item.status === "rejected");
        if (failed?.status === "rejected") setError(failed.reason?.message || "Не вдалося оновити дані");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [applied, cursor, revision]);
  const view = (changes: Partial<typeof initialFilters>) => {
    setFilters({ ...initialFilters, ...changes });
    setApplied({ ...initialFilters, ...changes });
    setCursor("");
    setTab("clients");
  };
  return (
    <div className="cc-shell">
      <aside>
        <small>CARPOT</small>
        <h1>Control Center</h1>
        <p>Warehouse First</p>
        <nav aria-label="Control Center">
          {[
            ["overview", "Огляд"],
            ["clients", "Клієнти"],
            ["queue", "Робоча черга"],
          ].map(([key, title]) => (
            <button
              key={key}
              aria-current={tab === key ? "page" : undefined}
              onClick={() => setTab(key)}
            >
              {title}
            </button>
          ))}
        </nav>
        <p>
          {staff.username}
          <small>{staff.role}</small>
        </p>
        <ThemeSwitch />
        <button
          onClick={async () => {
            try {
              await api("/auth/logout", "POST");
              sessionStorage.removeItem("control.csrf");
              logout();
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Вийти
        </button>
      </aside>
      <main>
        <header className="cc-top">
          <h2>
            {
              {
                overview: "Огляд Warehouse",
                clients: "Клієнтські компанії",
                queue: "Внутрішня робоча черга",
              }[tab]
            }
          </h2>
          <span className="cc-badge">
            {overview?.preview ? "Демонстраційний режим" : overview?.environment || "Перевіряємо середовище"}
          </span>
          <button onClick={refresh}>Оновити</button>
        </header>
        <State error={error} loading={loading} />
        {overview?.preview && <p className="cc-source" role="status">Тільки демонстраційні компанії. Реальні клієнти, платежі та фінансові дані не підключені.</p>}
        {overview && (
          <p className={"cc-source " + overview.source.state} role="status">
            {overview.source.state === "fresh"
              ? "Джерело оновлено"
              : overview.source.state === "stale"
                ? "Дані застаріли"
                : "Джерело недоступне"}{" "}
            · {coverageName[overview.source.coverage] || "Неповне покриття"} ·{" "}
            {date(overview.source.last_success)}. Час: Київ.
          </p>
        )}
        {tab === "overview" && overview && (
          <>
            <div className="cc-metrics">
              <article>
                <small>Workspaces у вашому scope</small>
                <strong>{overview.workspaces ?? "Немає даних"}</strong>
              </article>
              <article>
                <small>Перевірені Billing links</small>
                <strong>{overview.linked ?? "Немає даних"}</strong>
              </article>
              <article>
                <small>Непов’язані / непідтверджені</small>
                <strong>
                  {overview.workspaces === null
                    ? "Немає даних"
                    : overview.workspaces - overview.linked}
                </strong>
              </article>
            </div>
            <section className="cc-card">
              <h3>Стани доступу · snapshot</h3>
              {Object.keys(overview.states).length ? (
                Object.entries(overview.states).map(([key, count]) => (
                  <p key={key}>
                    {states[key] || "Невідомо"} <strong>{String(count)}</strong>
                  </p>
                ))
              ) : (
                <p>Покриття джерела ще не підтверджено.</p>
              )}
              <p>
                Trial і Grace не є підтвердженим paid revenue. Без entitlement
                projection доступ позначено неповним.
              </p>
            </section>
            <section className="cc-card">
              <h3>Потребують уваги</h3>
              <p>
                Paid coverage завершується за 14 днів:{" "}
                {overview.expiring_14d ?? "Немає даних"}. Конфлікти:{" "}
                {overview.conflicts ?? "Немає даних"}.
              </p>
              <button onClick={() => view({ status: "EXPIRED" })}>
                Завершені підписки
              </button>
              <button onClick={() => view({ linking: "conflict" })}>
                Конфлікти зв’язків
              </button>
              <button onClick={() => setTab("queue")}>Робоча черга</button>
            </section>
            <section className="cc-card">
              <h3>Фінансові показники</h3>
              <p>
                MRR і churn недоступні: методологію не затверджено. Cash
                collected недоступний: немає повної фінансової проєкції. Продажі
                запчастин і legacy success не включаються.
              </p>
            </section>
          </>
        )}
        {tab === "clients" && (
          <>
            <form
              className="cc-filters"
              onSubmit={(e) => {
                e.preventDefault();
                setCursor("");
                setApplied({ ...filters });
              }}
            >
              <label>
                Пошук
                <input
                  placeholder="Компанія або email власника"
                  value={filters.q}
                  onChange={(e) =>
                    setFilters({ ...filters, q: e.target.value })
                  }
                />
              </label>
              <label>
                Тариф
                <input
                  placeholder="Назва тарифу"
                  value={filters.plan}
                  onChange={(e) =>
                    setFilters({ ...filters, plan: e.target.value })
                  }
                />
              </label>
              <label>
                Стан
                <select
                  value={filters.status}
                  onChange={(e) =>
                    setFilters({ ...filters, status: e.target.value })
                  }
                >
                  <option value="">Усі</option>
                  {Object.entries(states).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Billing link
                <select
                  value={filters.linking}
                  onChange={(e) =>
                    setFilters({ ...filters, linking: e.target.value })
                  }
                >
                  <option value="">Усі</option>
                  <option value="linked">Пов’язано</option>
                  <option value="unlinked">Не пов’язано</option>
                  <option value="conflict">Конфлікт</option>
                </select>
              </label>
              {staff.can_assign && (
                <label>
                  Менеджер
                  <select
                    value={filters.manager}
                    onChange={(e) =>
                      setFilters({ ...filters, manager: e.target.value })
                    }
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
                  value={filters.registered_from}
                  onChange={(e) =>
                    setFilters({ ...filters, registered_from: e.target.value })
                  }
                />
              </label>
              <label>
                Сортування
                <select
                  value={filters.sort}
                  onChange={(e) =>
                    setFilters({ ...filters, sort: e.target.value })
                  }
                >
                  <option value="name">Назва</option>
                  <option value="registered">Дата реєстрації</option>
                </select>
              </label>
              <button>Застосувати</button>
            </form>
            <div className="cc-directory" aria-label="Компанії">
              {page?.items.length === 0 && !loading && (
                <p>Компаній за цими умовами немає. Враховується ваш scope.</p>
              )}
              {page?.items.map((c: Row) => (
                <button
                  className="cc-company"
                  key={c.id}
                  onClick={() => setSelected(c.id)}
                >
                  <strong>{c.display_name}</strong>
                  <span>
                    {c.access_incomplete
                      ? "Доступ: даних недостатньо"
                      : states[c.access.status] || c.access.status}
                  </span>
                  <span>{c.access.plan || "Тариф невідомий"}</span>
                  <span>{c.linking}</span>
                  <small>
                    {c.state === "stale"
                      ? "Застарілий snapshot"
                      : date(c.registered_at)}
                  </small>
                </button>
              ))}
            </div>
            <div className="cc-pagination">
              <button
                disabled={!cursor || loading}
                onClick={() => setCursor("")}
              >
                На початок
              </button>
              <button
                disabled={!page?.next_cursor || loading}
                onClick={() => setCursor(page?.next_cursor || "")}
              >
                Наступні
              </button>
            </div>
          </>
        )}
        {tab === "queue" && (
          <section className="cc-card">
            <p>Внутрішні дії персоналу. Legacy Support тут не інтегровано.</p>
            {tasks.length === 0 ? (
              <p>Дій у вашій черзі немає.</p>
            ) : (
              tasks.map((t) => (
                <article className="cc-task" key={t.id}>
                  <strong>{t.company_name}</strong>
                  <button onClick={() => setSelected(t.company_id)}>
                    {t.next_action}
                  </button>
                  <small>
                    Відповідальний: {t.assignee_name} ·{" "}
                    {t.due_at ? date(t.due_at) : "Без строку"}
                  </small>
                  <label>
                    Статус
                    <select
                      value={t.status}
                      onChange={async (e) => {
                        try {
                          await api("/tasks/" + t.id, "PATCH", {
                            next_action: t.next_action,
                            status: e.target.value,
                            due_at: t.due_at,
                          });
                          refresh();
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      <option value="open">Відкрита</option>
                      <option value="in_progress">У роботі</option>
                      <option value="done">Завершено</option>
                    </select>
                  </label>
                </article>
              ))
            )}
          </section>
        )}
      </main>
      {selected && (
        <CompanyPreview
          key={selected}
          id={selected}
          staff={staff}
          close={() => setSelected(null)}
          changed={refresh}
        />
      )}
    </div>
  );
}
function App() {
  const [staff, setStaff] = useState<Staff | null>(null),
    [state, setState] = useState("loading");
  useEffect(() => {
    api("/status")
      .then(() =>
        api("/auth/me")
          .then((s) => {
            setStaff(s);
            setState("ready");
          })
          .catch(() => setState("ready")),
      )
      .catch(() => setState("disabled"));
  }, []);
  return (
    <ThemeProvider>
      {state === "loading" ? (
        <main className="cc-login">
          <p role="status">Перевіряємо доступ…</p>
        </main>
      ) : state === "disabled" ? (
        <main className="cc-login">
          <section>
            <h1>Control Center недоступний</h1>
            <p>
              Контур вимкнено або сервіс не відповідає. Дані клієнтів не
              завантажено.
            </p>
          </section>
        </main>
      ) : staff ? (
        <Workspace staff={staff} logout={() => setStaff(null)} />
      ) : (
        <Login onLogin={setStaff} />
      )}
    </ThemeProvider>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
