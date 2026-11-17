import { useState } from "react";
import { api, type Row } from "./api";

export default function SecuritySettings({ logout, passwordOnly, canRotateMfa }: { logout: () => void; passwordOnly: boolean; canRotateMfa: boolean }) {
  const [enroll, setEnroll] = useState<Row | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  return <section className="cc-card cc-security">
    <h3>Захист облікового запису</h3>
    <form aria-label="Звичайна зміна пароля" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError("");
      const body = Object.fromEntries(new FormData(e.currentTarget));
      try { await api("/auth/password", "POST", body); logout(); }
      catch(e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <p>Після зміни пароля всі ваші сесії буде завершено.</p>
      <label>Поточний пароль<input name="current_password" type="password" autoComplete="current-password" required/></label>
      <label>Новий пароль (від 12 символів)<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required/></label>
      {!passwordOnly && <label>Новий MFA-код<input name="mfa_code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required/></label>}
      <button disabled={busy}>Змінити пароль</button>
    </form>
    {!passwordOnly && canRotateMfa && <>
    <p>За потреби ви також можете замінити пароль і ключ MFA. Підключення Warehouse не потребує цієї дії.</p>
    {!enroll ? <button disabled={busy} onClick={async () => {
      setBusy(true); setError("");
      try { setEnroll(await api("/auth/enrollment", "POST")); }
      catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>Налаштувати новий ключ MFA</button> : <form aria-label="Зміна пароля та MFA" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError("");
      const body = Object.fromEntries(new FormData(e.currentTarget));
      try {
        await api("/auth/rotate", "POST", {...body, enrollment:enroll.enrollment});
        sessionStorage.removeItem("control.csrf"); setEnroll(null); logout();
      } catch(e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <p>Додайте новий запис «CarPot CRM» у Google Authenticator із ключем нижче (на основі часу). Старий запис поки збережіть.</p>
      <div className="cc-key">{enroll.seed}</div>
      <button type="button" onClick={async()=>{try{await navigator.clipboard.writeText(enroll.seed)}catch{setError("Виділіть і скопіюйте ключ вручну.")}}}>Скопіювати ключ</button>
      <small>Підтвердження дійсне 10 хвилин. Не надсилайте ключ у чат.</small>
      <label>Поточний пароль<input name="current_password" type="password" required autoComplete="current-password"/></label>
      <label>Код зі старого Authenticator<input name="current_code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required/></label>
      <label>Новий пароль (від 12 символів)<input name="new_password" type="password" minLength={12} maxLength={128} required autoComplete="new-password"/></label>
      <label>Код із нового Authenticator<input name="new_code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required/></label>
      <button className="cc-primary" disabled={busy}>Зберегти й увійти знову</button>
      <button type="button" disabled={busy} onClick={()=>setEnroll(null)}>Скасувати</button>
    </form>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
