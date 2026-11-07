import { useContext, useState } from "react";
import { api, type Row } from "./api";
import { TeamIdentity, useCan } from "./permissions";
export default function CategoryRepair({ vehicle: v }: { vehicle: Row }) {
  const who = useContext(TeamIdentity);
  const can = useCan(),
    [report, setReport] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  if (
    who?.role !== "DIRECTOR" ||
    !v.ktype ||
    !can("inventory.adjust_quantity") ||
    !can("dismantling.manage")
  )
    return null;
  const path = "/plan-parts/donor-parts/classification/";
  async function preview() {
    setBusy(true);
    setError("");
    try {
      setReport(
        await api(
          path +
            "preview?vehicle_id=" +
            v.id +
            "&ktype=" +
            v.ktype +
            "&provision=true",
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (!report) return;
    setBusy(true);
    setError("");
    try {
      const r = await api(
        path + "apply?vehicle_id=" + v.id + "&ktype=" + v.ktype,
        "POST",
        { token: report.token, provision: true },
      );
      setReport({ ...r, finished: true });
      window.dispatchEvent(new Event("warehouse:inventory-changed"));
      window.dispatchEvent(new Event("warehouse:categories-changed"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="r1-secondary">
      <summary>Уточнити категорії цього автомобіля</summary>
      <p>
        Однозначні типи отримають корпоративну категорію. Призначені раніше
        категорії, залишки та ціни збережуться.
      </p>
      <button disabled={busy} onClick={() => void preview()}>
        Перевірити категорії
      </button>
      {report && (
        <div role="status">
          Однозначних: {report.counts.matched}. Для уточнення:{" "}
          {report.counts.review}. Уже призначено: {report.counts.protected}.
          {report.nodes.length > 0 && (
            <p>
              Буде підготовлено відсутні корпоративні категорії та підкатегорії:{" "}
              {report.nodes.length}. Це окреме налаштування довідника, без
              створення складських позицій.
            </p>
          )}
          {!report.finished ? (
            <button disabled={busy} onClick={() => void apply()}>
              Застосувати перевірені категорії
            </button>
          ) : (
            <p>Категорії збережено.</p>
          )}
          <details>
            <summary>Переглянути відповідності</summary>
            {report.decisions.map((d: Row) => (
              <p key={d.part_id}>
                {d.name} → {d.proposed.section || "Потребує уточнення"}
                {d.status === "protected"
                  ? " · поточну категорію збережено"
                  : ""}
              </p>
            ))}
          </details>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
