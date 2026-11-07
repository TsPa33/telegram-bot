import { useContext, useRef, useState } from "react";
import { api, ApiError, type Row } from "./api";
import { TeamIdentity, useCan } from "./permissions";
/** Optional location editor inside the existing part card; preserves legacy text. */
export default function StockLocationFields({
  part,
  onSaved,
}: {
  part: Row;
  onSaved: (p: Row) => void;
}) {
  const who = useContext(TeamIdentity),
    can = useCan(),
    guard = useRef(false),
    scope =
      "warehouse.location:" +
      JSON.stringify([who?.id, who?.workspace_account_id, part.id]);
  const [fields, setFields] = useState<Record<string, string>>({}),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [pending, setPending] = useState<Row | null>(() => {
    try {
      const r = JSON.parse(sessionStorage.getItem(scope) || "null");
      return r?.scope === scope &&
        r.payload?.type === "transfer" &&
        r.payload?.quantity === 0 &&
        /^[a-f0-9-]{36}$/.test(r.payload?.request_key || "")
        ? r
        : null;
    } catch {
      return null;
    }
  });
  if (!can("inventory.transfer")) return null;
  async function save() {
    if (guard.current) return;
    guard.current = true;
    setBusy(true);
    setError("");
    try {
      const location = Object.entries(fields)
        .filter(([, v]) => v.trim())
        .map(([k, v]) => k + ": " + v.trim())
        .join(" · ");
      if (!pending && (!location || location.length > 120))
        throw Error("Вкажіть хоча б одне поле локації; разом до 120 символів.");
      const request = pending || {
        scope,
        payload: {
          type: "transfer",
          quantity: 0,
          location,
          reason,
          request_key: crypto.randomUUID(),
        },
      };
      sessionStorage.setItem(scope, JSON.stringify(request));
      setPending(request);
      const result = await api(
        "/parts/" + part.id + "/operations",
        "POST",
        request.payload,
      );
      sessionStorage.removeItem(scope);
      setPending(null);
      setFields({});
      setReason("");
      onSaved(result);
      window.dispatchEvent(new Event("warehouse:inventory-changed"));
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) {
        sessionStorage.removeItem(scope);
        setPending(null);
      }
      setError((e as Error).message);
    } finally {
      guard.current = false;
      setBusy(false);
    }
  }
  return (
    <details className="r1-secondary">
      <summary>Локація (необов’язково)</summary>
      <p>Збережена локація: {part.location || "Не вказано"}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        {["Склад", "Стелаж", "Полиця", "Комірка"].map((key) => (
          <label key={key}>
            {key}
            <input
              aria-label={"Локація: " + key}
              maxLength={100}
              disabled={busy || !!pending}
              value={fields[key] || ""}
              onChange={(e) =>
                setFields((v) => ({ ...v, [key]: e.target.value }))
              }
            />
          </label>
        ))}
        <label>
          Причина зміни локації
          <input
            aria-label="Причина зміни локації"
            required={!pending}
            minLength={3}
            maxLength={2000}
            disabled={busy || !!pending}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <button disabled={busy || part.archived}>
          {pending ? "Повторити збереження локації" : "Зберегти локацію"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
