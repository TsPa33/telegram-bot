import { useState } from "react";
import { api, labels, type Row } from "./api";
import { Modal, RecordForm } from "./components";
import { State, useLoad } from "./shared";

export default function VehicleChecklist({ vehicle }: { vehicle: Row }) {
  const [offset, setOffset] = useState(0), [history, setHistory] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [edit, setEdit] = useState<Row | null>(null);
  const path = `/vehicles/${vehicle.id}/plan-parts-checklist`;
  const { data, error, loading, reload } = useLoad(() => api(`${path}?limit=50&offset=${offset}&include_history=${history}`), [vehicle.id, offset, history]);
  async function load(refresh = false) {
    if (refresh && !window.confirm("Оновити каталог через Plan.Parts? Запит може витрачати API-токени. Ваші перевірки й українські назви збережуться.")) return;
    setBusy(true); setMessage("");
    try {
      const result = await api(`${path}?refresh=${refresh}`, "POST");
      setMessage(`Додано: ${result.created}. Оновлено: ${result.updated}. ${result.provider_requested ? "Отримано з Plan.Parts." : "Використано збережений список."}`);
      setOffset(0); reload();
    } catch (e) { setMessage((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section>
    <h3>Потенційні запчастини — Plan.Parts</h3>
    <p className="notice">Це перелік можливих типів деталей, а не підтверджена комплектація чи складські залишки. Категорії та українські переклади API не надає; назви можна перекласти вручну. Кількість артикулів не є кількістю деталей на складі.</p>
    {!vehicle.ktype && <p>Спочатку виберіть і збережіть конкретний K-Type автомобіля.</p>}
    {!vehicle.archived && <div className="modal-actions">
      <button disabled={busy || !vehicle.ktype} onClick={() => load()}>Завантажити чекліст за K-Type</button>
      {data?.synced && <button disabled={busy} onClick={() => load(true)}>Оновити з Plan.Parts</button>}
    </div>}
    {busy && <p role="status">Завантаження…</p>}
    {message && <p role="status">{message}</p>}
    <State error={error} loading={loading} />
    {error && <button onClick={reload}>Повторити читання</button>}
    {data && <>
      <label><input type="checkbox" checked={history} onChange={e => {setHistory(e.target.checked); setOffset(0);}} /> Показати попередні K-Type (лише перегляд)</label>
      <p>Пунктів: {data.total}. Попередніх: {data.historical_total}.</p>
      {data.items.map((item: Row) => <article key={item.id}>
        <strong>{item.name_uk || item.name_en}</strong>
        {item.name_uk && <p>{item.name_en}</p>}
        <p>Plan.Parts · PT {item.pt_id} · K-Type {item.ktype} · Артикулів у каталозі: {item.article_count}</p>
        <p>{labels[item.status]} {item.notes && `— ${item.notes}`}</p>
        {!vehicle.archived && item.ktype === data.ktype && <button onClick={() => setEdit(item)}>Перевірити / перекласти</button>}
      </article>)}
      <div className="modal-actions">
        <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Попередні 50</button>
        <button disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Наступні 50</button>
      </div>
    </>}
    {edit && <Modal title="Перевірка потенційної деталі" onClose={() => setEdit(null)}>
      <p>{edit.name_en} · PT {edit.pt_id}</p>
      <RecordForm initial={edit} fields={[
        {key: "status", label: "Результат перевірки", options: ["unchecked", "present", "absent", "damaged"].map(value => ({value, label: labels[value]}))},
        {key: "name_uk", label: "Українська назва"},
        {key: "notes", label: "Примітки", type: "textarea"},
      ]} onSave={async values => {await api(`${path}/${edit.id}`, "PATCH", values); setEdit(null); reload();}} />
      <p>Збереження перевірки не створює залишків. Надходження деталей оформлюйте окремо у складі.</p>
    </Modal>}
  </section>;
}
