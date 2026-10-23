import { ArrowLeft, ArrowRight, PackageOpen, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { type Row } from "./api";
export function Empty({
  title = "Тут поки порожньо",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <PackageOpen size={38} strokeWidth={1} />
      <h3>{title}</h3>
      <p>{children || "Додайте перший запис, щоб почати роботу."}</p>
    </div>
  );
}
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      aria-label={title}
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button aria-label="Закрити" className="icon-button" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export type Field = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  wide?: boolean;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
};
export function RecordForm({
  fields,
  initial = {},
  onSave,
  submit = "Зберегти",
}: {
  fields: Field[];
  initial?: Row;
  onSave: (data: Row) => Promise<void>;
  submit?: string;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    const data: Row = {};
    for (const f of fields) {
      const val = form.get(f.key);
      data[f.key] =
        f.type === "checkbox"
          ? val === "on"
          : f.type === "number" && val !== ""
            ? Number(val)
            : val;
      if (
        val === "" &&
        [
          "vin",
          "vehicle_id",
          "category_id",
          "subcategory_id",
          "serial_number",
          "acquisition_cost",
          "acquisition_date",
          "unit_cost",
          "selling_price",
        ].includes(f.key)
      )
        data[f.key] = null;
    }
    try {
      await onSave(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <div className="form-grid">
        {fields.map((f) => (
          <label className={f.wide ? "wide" : ""} key={f.key}>
            {f.label}
            {f.required ? " *" : ""}
            {f.options ? (
              <select
                name={f.key}
                required={f.required}
                defaultValue={initial[f.key] ?? ""}
              >
                {f.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                name={f.key}
                maxLength={10000}
                defaultValue={initial[f.key] ?? ""}
              />
            ) : (
              <input
                name={f.key}
                type={f.type || "text"}
                required={f.required}
                min={f.min}
                max={f.max}
                minLength={f.type === "password" ? 12 : undefined}
                maxLength={
                  f.type === "password" ? 128 : f.key === "vin" ? 17 : undefined
                }
                step={f.type === "number" ? f.step ?? "0.01" : undefined}
                defaultValue={
                  f.type === "checkbox" ? undefined : (initial[f.key] ?? "")
                }
                defaultChecked={
                  f.type === "checkbox" ? !!initial[f.key] : undefined
                }
              />
            )}{" "}
            {f.hint && <small>{f.hint}</small>}
          </label>
        ))}
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="form-footer">
        <span>* Обов’язкові поля</span>
        <button className="primary" disabled={busy}>
          {busy ? "Збереження…" : submit}
        </button>
      </div>
    </form>
  );
}
export function Pager({
  total,
  page,
  setPage,
}: {
  total: number;
  page: number;
  setPage: (n: number) => void;
}) {
  return (
    <div className="pager">
      <span>Усього записів: {total}</span>
      <div>
        <button
          aria-label="Попередня сторінка"
          disabled={!page}
          onClick={() => setPage(page - 1)}
        >
          <ArrowLeft size={16} />
        </button>
        <span>
          {page + 1} / {Math.max(1, Math.ceil(total / 50))}
        </span>
        <button
          aria-label="Наступна сторінка"
          disabled={(page + 1) * 50 >= total}
          onClick={() => setPage(page + 1)}
        >
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  const text: Record<string, string> = {
    unchecked: "Не перевірено",
    present: "Наявна",
    absent: "Відсутня",
    damaged: "Пошкоджена",
    planned: "Заплановано",
    dismantling: "Розбирання",
    completed: "Завершено",
  };
  return <span className={`badge ${value}`}>{text[value] || value}</span>;
}
