import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { api, date, type Row, type Staff } from "./api";
import { profileHref, taskStatuses, taskUrgency } from "./model";
import {
  Badge,
  Empty,
  Feedback,
  PageHeader,
  Panel,
  useDialog,
  useLoad,
  useRevision,
} from "./shared";
export function TaskComposer({
  companyId,
  companyName,
  staff,
  onClose,
  onSaved,
}: {
  companyId: string;
  companyName: string;
  staff: Staff;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const dialog = useDialog(true, () => {
    if (!busy) onClose();
  });
  return (
    <dialog ref={dialog} className="cc-dialog" aria-labelledby="task-title">
      <header>
        <h2 id="task-title">Нове завдання</h2>
        <button
          className="cc-icon-button"
          onClick={onClose}
          aria-label="Закрити завдання"
          disabled={busy}
        >
          ×
        </button>
      </header>
      <p>{companyName}</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget),
            due = String(f.get("due") || "");
          setBusy(true);
          setError("");
          try {
            await api(
              "/companies/" + encodeURIComponent(companyId) + "/tasks",
              "POST",
              {
                next_action: f.get("action"),
                status: "open",
                due_at: due ? new Date(due).toISOString() : null,
              },
            );
            onSaved();
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Наступна дія
          <input name="action" maxLength={500} required autoFocus />
        </label>
        <label>
          Строк · локальний час пристрою
          <input type="datetime-local" name="due" />
        </label>
        <p className="cc-caption">
          У черзі строк відображається за Києвом. Відповідальний:{" "}
          {staff.username}. Створення завдання не надсилає повідомлення клієнту.
        </p>
        <Feedback error={error} />
        <button className="cc-primary" disabled={busy}>
          {busy ? "Зберігаємо…" : "Додати до моєї черги"}
        </button>
      </form>
    </dialog>
  );
}
export function TaskSummary({ tasks }: { tasks: Row[] }) {
  return (
    <>
      {tasks
        .filter((t) => t.status !== "done")
        .slice(0, 3)
        .map((t) => (
          <a
            className="cc-attention-row"
            href={profileHref(t.company_id)}
            key={t.id}
          >
            <div>
              <strong>{t.company_name}</strong>
              <small>{t.next_action}</small>
            </div>
            <Badge tone={taskUrgency(t).tone}>{taskUrgency(t).label}</Badge>
          </a>
        ))}
      {!tasks.some((t) => t.status !== "done") && (
        <Empty title="У доступній вибірці немає відкритих завдань" />
      )}
    </>
  );
}
export default function WorkQueue({ revision }: { revision: number }) {
  const [localRevision, reload] = useRevision(),
    request = useLoad<Row[]>("/tasks", revision + localRevision),
    [filter, setFilter] = useState("all"),
    [error, setError] = useState(""),
    [saving, setSaving] = useState<string | null>(null),
    [notice, setNotice] = useState("");
  const controls = useRef(new Map<string, HTMLSelectElement>()),
    pendingFocus = useRef<string | null>(null);
  const tasks = request.data || [],
    visible = tasks.filter((t) =>
      filter === "all" || filter === "overdue"
        ? filter === "overdue"
          ? taskUrgency(t).label === "Прострочено"
          : true
        : t.status === filter,
    );
  useEffect(() => {
    if (request.loading || !request.data || !pendingFocus.current) return;
    const id = pendingFocus.current;
    const node = [...controls.current.entries()].find(
      ([key, el]) => key.startsWith(id) && el.getClientRects().length,
    )?.[1];
    const target =
      node ||
      document.querySelector<HTMLElement>(
        ".cc-work-filters [aria-pressed=true]",
      );
    target?.focus();
    pendingFocus.current = null;
  }, [request.loading, request.data]);
  async function change(task: Row, status: string) {
    setSaving(task.id);
    setError("");
    setNotice("");
    try {
      await api("/tasks/" + encodeURIComponent(task.id), "PATCH", {
        next_action: task.next_action,
        status,
        due_at: task.due_at,
      });
      pendingFocus.current = task.id;
      reload();
      setNotice("Статус завдання збережено");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  }
  const statusControl = (t: Row, variant: string) => (
    <label className="cc-task-status">
      <span className="cc-sr-only">Статус завдання: {t.next_action}</span>
      <select
        aria-label={`Статус завдання: ${t.next_action}`}
        ref={(node) => {
          const key = t.id + variant;
          if (node) {
            controls.current.set(key, node);
          } else controls.current.delete(key);
        }}
        value={t.status}
        disabled={Boolean(saving)}
        onChange={(e) => void change(t, e.target.value)}
      >
        {Object.entries(taskStatuses).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <>
      <PageHeader
        title="Робоча черга"
        subtitle="Завдання команди з дозволеного вам контексту."
        action={
          <a className="cc-button" href="#/clients">
            <Plus size={16} /> Завдання з профілю клієнта
          </a>
        }
      />
      <div
        className="cc-work-filters"
        role="group"
        aria-label="Фільтри завдань"
      >
        {[
          ["all", "Усі"],
          ["open", "Відкриті"],
          ["in_progress", "У роботі"],
          ["overdue", "Прострочені"],
          ["done", "Завершені"],
        ].map(([k, v]) => (
          <button
            aria-pressed={filter === k}
            key={k}
            onClick={() => setFilter(k)}
          >
            {v}
          </button>
        ))}
      </div>
      <Feedback
        loading={request.loading}
        error={request.error}
        retry={reload}
      />
      <Feedback error={error} />
      {notice && <p role="status">{notice}</p>}
      {request.data && (
        <Panel
          title="Завдання команди"
          subtitle="Доступна вибірка до 100 останніх завдань · час Києва"
        >
          {visible.length ? (
            <>
              <table className="cc-task-table">
                <thead>
                  <tr>
                    <th>Наступна дія / клієнт</th>
                    <th>Відповідальний</th>
                    <th>Терміновість</th>
                    <th>Строк</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <a href={profileHref(t.company_id)}>{t.next_action}</a>
                        <small>{t.company_name}</small>
                      </td>
                      <td>{t.assignee_name}</td>
                      <td>
                        <Badge tone={taskUrgency(t).tone}>
                          {taskUrgency(t).label}
                        </Badge>
                      </td>
                      <td>{t.due_at ? date(t.due_at) : "Без строку"}</td>
                      <td>{statusControl(t, "table")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="cc-task-cards">
                {visible.map((t) => (
                  <article className="cc-client-card" key={t.id}>
                    <a href={profileHref(t.company_id)}>
                      <small>{t.company_name}</small>
                      <h3>{t.next_action}</h3>
                    </a>
                    <div className="cc-card-data">
                      <div>
                        <small>Відповідальний</small>
                        {t.assignee_name}
                      </div>
                      <div>
                        <small>Строк · Київ</small>
                        {t.due_at ? date(t.due_at) : "Без строку"}
                      </div>
                    </div>
                    <div className="cc-tagline">
                      <Badge tone={taskUrgency(t).tone}>
                        {taskUrgency(t).label}
                      </Badge>
                      {statusControl(t, "card")}
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <Empty title="Завдань за цими умовами немає">
              Нове завдання можна додати з профілю клієнта.
            </Empty>
          )}
        </Panel>
      )}
      <p className="cc-caption">
        Терміновість розрахована зі строку. Завдання та статуси не змінюють
        тариф, фінансові записи або права клієнта.
      </p>
    </>
  );
}
