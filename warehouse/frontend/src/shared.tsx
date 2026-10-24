import { Boxes, CarFront, ChartNoAxesCombined, Package } from "lucide-react";
import { useEffect, useState } from "react";
import { labels, money, when, type Row } from "./api";
import { Modal } from "./components";

export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [rev, setRev] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    loader()
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [...deps, rev]);
  return { data, error, loading, reload: () => setRev((r) => r + 1) };
}
export const option = (value: string, label: string) => ({ value, label });
export const choices = (keys: string[]) =>
  keys.map((k) => option(k, labels[k] || k));
export function State({ error, loading }: { error: string; loading: boolean }) {
  return (
    <>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {loading && (
        <div className="loading" role="status">
          <span />
          Завантаження даних…
        </div>
      )}
    </>
  );
}
export type Notify = (text: string) => void;
export function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export function Metrics({ d }: { d: Row }) {
  return (
    <div className="metrics">
      {[
        {
          label: "Донорські автомобілі",
          value: d.vehicles,
          icon: CarFront,
          sub: "Активні донори",
        },
        {
          label: "Позиції на складі",
          value: d.positions,
          icon: Package,
          sub: `${d.stock_units} одиниць загалом`,
        },
        {
          label: "Доступно до продажу",
          value: d.available_units,
          icon: Boxes,
          sub: `${d.reserved_units} одиниць у резерві`,
        },
        {
          label: "Оціночна вартість складу",
          value: money(d.estimated_sales_value),
          icon: ChartNoAxesCombined,
          sub: "За вказаними цінами продажу",
        },
      ].map((m) => (
        <article className="metric" key={m.label}>
          <div>
            <span>{m.label}</span>
            <m.icon size={18} />
          </div>
          <strong>{m.value}</strong>
          <small>{m.sub}</small>
        </article>
      ))}
    </div>
  );
}
export function Confirm({
  title,
  text,
  onClose,
  onConfirm,
  destructive = false,
}: {
  title: string;
  text: string;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  destructive?: boolean;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <p>{text}</p>
      {error && <div className="error">{error}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>Скасувати</button>
        <button
          className={destructive ? "destructive" : "primary"}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Підтвердити
        </button>
      </div>
    </Modal>
  );
}
export function OperationTable({ rows }: { rows: Row[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Операція / час</th>
            <th>Запис</th>
            <th>Залишок / резерв</th>
            <th>Причина</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>
                <b>{labels[r.type] || r.type}</b>
                <small>{when(r.created_at)}</small>
              </td>
              <td>
                {r.after.name ||
                  [r.after.manufacturer, r.after.model]
                    .filter(Boolean)
                    .join(" ") ||
                  "—"}
                <small>{r.after.number ? `№ ${r.after.number}` : r.after.donor_id ? "Автомобіль" : r.entity_id.slice(0, 8)}</small>
              </td>
              <td>
                {r.after.quantity !== undefined ? (
                  <>
                    <b>
                      {r.before.quantity ?? 0} → {r.after.quantity}
                    </b>
                    <small>
                      Резерв: {r.before.reserved_quantity ?? 0} →{" "}
                      {r.after.reserved_quantity}
                    </small>
                    {r.type === "transfer" && (
                      <small>
                        {r.before.location || "—"} → {r.after.location}
                      </small>
                    )}
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>
                {r.reason}
                <small>Автор: {r.actor_id.slice(0, 8)}</small>
                <details>
                  <summary>Деталі запису</summary>
                  <pre>
                    {JSON.stringify(
                      { before: r.before, after: r.after },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
