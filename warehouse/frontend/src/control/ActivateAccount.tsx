import { useState } from "react";
import { api, type Row } from "./api";
import SecuritySettings from "./SecuritySettings";
export default function ActivateAccount({
  passwordOnly,
  logout,
}: {
  passwordOnly: boolean;
  logout: () => void;
}) {
  const [enroll, setEnroll] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="cc-login">
      <section>
        <h1>Активуйте особистий доступ</h1>
        <p>
          Змініть одноразовий пароль протягом 10 хвилин. Доступ до CRM
          відкриється після повторного входу.
        </p>
        {passwordOnly ? (
          <SecuritySettings logout={logout} passwordOnly canRotateMfa={false} />
        ) : (
          <>
            {!enroll ? (
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    setEnroll(await api("/auth/activation-enrollment", "POST"));
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Підключити власний Authenticator
              </button>
            ) : (
              <form
                aria-label="Активація персонального доступу"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError("");
                  const body = Object.fromEntries(
                    new FormData(e.currentTarget),
                  );
                  try {
                    await api("/auth/password", "POST", {
                      ...body,
                      enrollment: enroll.enrollment,
                    });
                    setEnroll(null);
                    logout();
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <p>
                  Додайте в Authenticator запис CarPot CRM із цим ключем на
                  основі часу:
                </p>
                <code className="cc-key">{enroll.seed}</code>
                <label>
                  Тимчасовий пароль
                  <input
                    type="password"
                    name="current_password"
                    required
                    autoComplete="current-password"
                    maxLength={128}
                  />
                </label>
                <label>
                  Новий пароль (від 12 символів)
                  <input
                    type="password"
                    name="new_password"
                    required
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                  />
                </label>
                <label>
                  Код із нового Authenticator
                  <input
                    name="mfa_code"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    required
                    maxLength={6}
                  />
                </label>
                <button disabled={busy}>Активувати й увійти знову</button>
              </form>
            )}
          </>
        )}
        {error && <p role="alert">{error}</p>}
        <button
          disabled={busy}
          onClick={async () => {
            try {
              await api("/auth/logout", "POST");
              setEnroll(null);
              logout();
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Завершити активацію пізніше
        </button>
        <small>
          Після виходу або завершення 10 хвилин власник має скинути доступ для
          нової спроби.
        </small>
      </section>
    </main>
  );
}
