import { useEffect, useState } from "react";
import { State } from "../shared";
import { api, type Row, type Staff } from "./api";

export default function Login({ onLogin }: { onLogin: (s: Staff) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [policy, setPolicy] = useState<Row | null>(null);
  useEffect(() => {
    let live = true;
    api("/status")
      .then((p) => {
        if (live) setPolicy(p);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, []);
  return (
    <main className="cc-login">
      <section>
        <small>CARPOT / АДМІНІСТРУВАННЯ</small>
        <h1>CarPot Global CRM</h1>
        <p>
          Окремий доступ персоналу. Акаунт Warehouse не надає адміністративних
          прав.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.currentTarget));
            if (!data.code) delete data.code;
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
            Логін
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
          {policy?.auth_mode === "mfa" && (
            <label>
              MFA-код
              <input
                name="code"
                aria-label="MFA-код"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
              />
              <small>Під час першого входу з тимчасовим паролем залиште порожнім.</small>
            </label>
          )}
          <State loading={busy || !policy} error={error} />
          <button disabled={busy || !policy}>
            {busy ? "Перевіряємо…" : "Увійти"}
          </button>
        </form>
        <small>Доступ створює власник CRM. Публічної реєстрації немає.</small>
      </section>
    </main>
  );
}
