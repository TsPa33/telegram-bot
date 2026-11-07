import { useContext, useRef, useState } from "react";
import { api, ApiError, type Row } from "./api";
import { TeamIdentity, useCan } from "./permissions";
export default function InventoryQuantity({
  part: p,
  onSaved,
}: {
  part: Row;
  onSaved: (r: Row) => void;
}) {
  const who = useContext(TeamIdentity),
    can = useCan(),
    guard = useRef(false);
  const scope =
    "warehouse.quantity:" +
    JSON.stringify([who?.id, who?.workspace_account_id, p.id]);
  const [pending, setPending] = useState<Row | null>(() => {
    try {
      const r = JSON.parse(sessionStorage.getItem(scope) || "null");
      return r?.scope === scope &&
        ["receipt", "write_off", "correction"].includes(r.payload?.type) &&
        /^[a-f0-9-]{36}$/.test(r.payload?.request_key || "")
        ? r
        : null;
    } catch {
      return null;
    }
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mode, setMode] = useState(""),
    [quantity, setQuantity] = useState(String(p.quantity)),
    [reason, setReason] = useState("");
  async function send(payload?: Row) {
    if (guard.current) return;
    guard.current = true;
    setBusy(true);
    setError("");
    try {
      const request = pending || {
        scope,
        payload: { ...payload, request_key: crypto.randomUUID() },
      };
      sessionStorage.setItem(scope, JSON.stringify(request));
      setPending(request);
      const result = await api(
        "/parts/" + p.id + "/operations",
        "POST",
        request.payload,
      );
      sessionStorage.removeItem(scope);
      setPending(null);
      setMode("");
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
    <div className="inventory-quantity" aria-label={"Залишок " + p.name}>
      <div>
        <button
          type="button"
          aria-label={"Списати 1 шт. " + p.name}
          disabled={
            busy ||
            !!pending ||
            p.archived ||
            p.quantity - p.reserved_quantity < 1 ||
            !can("inventory.write_off")
          }
          onClick={() => {
            setMode("write_off");
            setReason("");
          }}
        >
          −
        </button>
        <b>{p.quantity} шт.</b>
        <button
          type="button"
          aria-label={"Додати 1 шт. " + p.name}
          disabled={
            busy || !!pending || p.archived || !can("inventory.adjust_quantity")
          }
          onClick={() =>
            void send({
              type: "receipt",
              quantity: 1,
              reason: "Додаткове надходження зі списку складу",
            })
          }
        >
          +
        </button>
        {can("inventory.adjust_quantity") && (
          <button
            type="button"
            aria-label={"Уточнити залишок " + p.name}
            disabled={busy || !!pending || p.archived}
            onClick={() => {
              setMode("correction");
              setQuantity(String(p.quantity));
              setReason("");
            }}
          >
            …
          </button>
        )}
      </div>
      {mode && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send({
              type: mode,
              quantity: mode === "write_off" ? 1 : Number(quantity),
              reason,
            });
          }}
        >
          {mode === "correction" && (
            <label>
              Новий залишок
              <input
                aria-label="Новий залишок"
                type="number"
                step="1"
                min={p.reserved_quantity}
                max="1000000"
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </label>
          )}
          <label>
            Причина
            <input
              aria-label="Причина зміни залишку"
              required
              minLength={3}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <button disabled={busy || !!pending}>Зберегти</button>
          <button
            type="button"
            disabled={busy || !!pending}
            onClick={() => setMode("")}
          >
            Скасувати
          </button>
        </form>
      )}
      {pending && !busy && (
        <button type="button" onClick={() => void send()}>
          Повторити збережений запит
        </button>
      )}
      {error && <small role="alert">{error}</small>}
    </div>
  );
}
