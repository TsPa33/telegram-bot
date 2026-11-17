import { useState } from "react";
import { api, date, type Row, type Staff } from "./api";
import { Feedback, useLoad, useRevision } from "./shared";

const roles = ["Moderator", "Manager", "Support", "Administrator"];
function Confirmation({ passwordOnly }: { passwordOnly: boolean }) {
  return (
    <>
      <label>
        Причина
        <input name="reason" required minLength={3} maxLength={300} />
      </label>
      {passwordOnly ? (
        <label>
          Ваш поточний пароль
          <input
            name="current_password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
          />
        </label>
      ) : (
        <label>
          Новий MFA-код власника
          <input
            name="mfa_code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            required
            maxLength={6}
            autoComplete="one-time-code"
          />
        </label>
      )}
    </>
  );
}
export default function TeamSettings({
  staff,
  passwordOnly,
}: {
  staff: Staff;
  passwordOnly: boolean;
}) {
  const [revision, refresh] = useRevision(),
    request = useLoad<Staff[]>("/staff", revision);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [receipt, setReceipt] = useState<Row | null>(null),
    [selected, setSelected] = useState<Staff | null>(null);
  async function submit(
    form: HTMLFormElement,
    path: string,
    method: string,
    extra = {},
  ) {
    setBusy(true);
    setError("");
    setReceipt(null);
    try {
      const value = await api(path, method, {
        ...Object.fromEntries(new FormData(form)),
        ...extra,
      });
      if (value?.temporary_password) setReceipt(value);
      form.reset();
      setSelected(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="cc-card cc-security">
      <h2>Команда CRM</h2>
      <p>
        Moderator бачить усіх клієнтів, контакти, нотатки й робочу чергу.
        Фінансовий та адміністративний доступ відсутній.
      </p>
      <Feedback
        error={error || request.error}
        loading={request.loading}
        retry={refresh}
      />
      {receipt && (
        <div role="status" className="cc-activation-receipt">
          <h3>Доступ створено: {receipt.staff.username}</h3>
          <p>
            Одноразовий тимчасовий пароль показано лише зараз. Дійсний до{" "}
            {date(receipt.expires_at)}. Передайте його особисто захищеним
            каналом.
          </p>
          <code className="cc-key">{receipt.temporary_password}</code>
          <p>
            Після першого входу є 10 хвилин для зміни пароля
            {passwordOnly ? "." : " та підключення власного Authenticator."}{" "}
            Якщо активацію перервано, скиньте доступ знову.
          </p>
          <button onClick={() => setReceipt(null)}>Приховати пароль</button>
        </div>
      )}
      <form
        aria-label="Створити співробітника"
        className="cc-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(e.currentTarget, "/staff", "POST");
        }}
      >
        <h3>Новий персональний обліковий запис</h3>
        <label>
          Логін співробітника
          <input
            name="username"
            required
            minLength={3}
            maxLength={120}
            pattern="[a-zA-Z0-9][a-zA-Z0-9._\-]{2,119}"
            autoComplete="off"
          />
        </label>
        <small>
          Латинські літери, цифри, крапка, дефіс або підкреслення. Регістр не
          має значення.
        </small>
        <label>
          Роль
          <select name="role" defaultValue="Moderator">
            {roles
              .filter((r) => r !== "Administrator")
              .map((r) => (
                <option key={r}>{r}</option>
              ))}
          </select>
        </label>
        <Confirmation passwordOnly={passwordOnly} />
        <button disabled={busy}>Створити обліковий запис</button>
      </form>
      <h3>Персонал і статус доступу</h3>
      <ul className="cc-team-list">
        {request.data?.map((person) => (
          <li key={person.id}>
            <strong>{person.username}</strong> · {person.role} ·{" "}
            {person.active ? "Активний" : "Заблокований"}
            {person.must_change_password ? " · Очікує зміни пароля" : ""}
            {person.id !== staff.id && person.role !== "Owner" && (
              <button
                disabled={busy}
                onClick={() => {
                  setSelected(person);
                  setReceipt(null);
                }}
              >
                Керувати {person.username}
              </button>
            )}
          </li>
        ))}
      </ul>
      {selected && (
        <form
          key={selected.id}
          aria-label="Керування співробітником"
          className="cc-form"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget,
              values = new FormData(form);
            const reset =
              (e.nativeEvent as SubmitEvent).submitter?.getAttribute(
                "value",
              ) === "reset";
            const confirmation = Object.fromEntries(
              [...values].filter(([key]) =>
                ["reason", "current_password", "mfa_code"].includes(key),
              ),
            );
            if (reset) {
              setBusy(true);
              setError("");
              setReceipt(null);
              void api(`/staff/${selected.id}/reset`, "POST", confirmation)
                .then((value) => {
                  setReceipt(value);
                  setSelected(null);
                  refresh();
                })
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            } else
              void submit(form, `/staff/${selected.id}`, "PATCH", {
                active: values.get("active") === "on",
                finance: values.get("finance") === "on",
              });
          }}
        >
          <h3>Доступ: {selected.username}</h3>
          <label>
            Роль
            <select name="role" defaultValue={selected.role}>
              {roles.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <label>
            <input
              name="active"
              type="checkbox"
              defaultChecked={selected.active}
            />{" "}
            Активний доступ
          </label>
          <label>
            <input
              name="finance"
              type="checkbox"
              defaultChecked={selected.can_finance}
            />{" "}
            Фінансовий доступ (для Moderator і Support завжди вимкнений)
          </label>
          <Confirmation passwordOnly={passwordOnly} />
          <p>
            Збереження змін або скидання доступу завершує всі сесії
            співробітника. Скидання не розблоковує акаунт автоматично.
          </p>
          <button disabled={busy} value="save">
            Зберегти доступ
          </button>
          <button disabled={busy} value="reset">
            Скинути доступ
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setSelected(null)}
          >
            Скасувати
          </button>
        </form>
      )}
    </section>
  );
}
