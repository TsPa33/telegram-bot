import { useState } from "react";
import { api, type Row } from "./api";
import { RecordForm, type Field } from "./components";

type Brand = { brand: string; mfa_id: number };
type Model = { ms_id: number; name: string | null; year_from?: number | null; year_to?: number | null };
type Modification = {
  ktype: number; modification: string; model_series: string | null;
  displacement_cc: number | null; power_kw: number | null; power_ps: number | null;
  year_from: number | null; year_to: number | null;
};

function SearchSelect({ label, value, options, disabled, onChange }: {
  label: string; value: string; options: { value: string; label: string }[];
  disabled: boolean; onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState("");
  return <label>{label}
    <input aria-label={`Пошук: ${label}`} placeholder="Пошук…" value={search}
      disabled={disabled} onChange={e => setSearch(e.target.value)} />
    <select aria-label={label} value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>
      <option value="">Оберіть…</option>
      {options.filter(o => o.value === value || o.label.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
        .map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </label>;
}

export default function VehicleForm({ initial, fields, onSave }: {
  initial: Row; fields: Field[]; onSave: (data: Row) => Promise<void>;
}) {
  const [manual, setManual] = useState(!!initial.id);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [mods, setMods] = useState<Modification[]>([]);
  const [brandId, setBrandId] = useState("");
  const [modelId, setModelId] = useState("");
  const [year, setYear] = useState("");
  const [ktype, setKtype] = useState("");
  const [modelName, setModelName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState("");
  async function lookup(resource: string, query = "") {
    setBusy(true); setError("");
    try {
      const rows = await api<any[]>(`/plan-parts/${resource}/lookup${query}`, "POST");
      if (resource === "brands") { setBrands(rows); setLoaded("brands"); }
      if (resource === "models") { setModels(rows); setLoaded("models"); }
      if (resource === "modifications") { setMods(rows); setLoaded("modifications"); }
      if (!rows.length) setError("Результатів немає. Змініть вибір або додайте авто вручну.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const selectedBrand = brands.find(b => String(b.mfa_id) === brandId);
  const selectedModel = models.find(m => String(m.ms_id) === modelId);
  const validYear = /^\d{4}$/.test(year) && Number(year) >= (selectedModel?.year_from ?? 1886)
    && Number(year) <= (selectedModel?.year_to ?? 2100);
  const matches = mods.filter(m => validYear && m.year_from !== null && m.year_from <= Number(year)
    && (m.year_to === null || Number(year) <= m.year_to));
  const selected = matches.find(m => String(m.ktype) === ktype);
  const name = selectedModel?.name || selected?.model_series || modelName.trim();
  return <>
    <div className="toolbar">
      <button type="button" disabled={busy} onClick={() => { setManual(!manual); setKtype(""); }}>
        {manual ? "Обрати через Plan.Parts" : "Додати вручну"}
      </button>
    </div>
    {manual ? <RecordForm fields={fields} initial={initial} onSave={d => {
      const unchanged = ["manufacturer", "model", "year", "engine", "generation", "fuel_type", "transmission"].every(k => String(d[k] ?? "") === String(initial[k] ?? ""));
      return onSave({ ...d, ktype: unchanged ? initial.ktype ?? null : null });
    }} /> : <>
      <p>Кожне завантаження — явний запит до Plan.Parts і може бути платним. Автоматичних запитів немає.</p>
      <button type="button" disabled={busy} onClick={() => lookup("brands")}>Завантажити марки / повторити</button>
      <div className="form-grid">
        <SearchSelect label="Марка" value={brandId} disabled={busy} options={brands.map(b => ({value:String(b.mfa_id),label:b.brand}))}
          onChange={id => { setBrandId(id); setModelId(""); setModels([]); setMods([]); setKtype(""); setModelName(""); setLoaded(""); setError(""); }} />
        <SearchSelect label="Модель" value={modelId} disabled={busy || !brandId}
          options={models.map(m => ({value:String(m.ms_id),label:(m.name || `Модель ID ${m.ms_id}`)
            + (m.year_from ? ` · ${m.year_from}–${m.year_to ?? "кінець не вказано"}` : "")}))}
          onChange={id => { setModelId(id); setMods([]); setKtype(""); setModelName(""); setLoaded(""); setError(""); }} />
        <label>Рік<input aria-label="Рік" type="number" min={selectedModel?.year_from ?? 1886} max={selectedModel?.year_to ?? 2100} step="1" value={year}
          disabled={busy} onChange={e => { setYear(e.target.value); setKtype(""); }} /></label>
      </div>
      <div className="toolbar">
        <button type="button" disabled={busy || !brandId} onClick={() => lookup("models", `?mfa_id=${brandId}`)}>Завантажити моделі / повторити</button>
        <button type="button" disabled={busy || !modelId || !validYear} onClick={() => lookup("modifications", `?ms_id=${modelId}`)}>Завантажити модифікації / повторити</button>
      </div>
      {busy && <p role="status">Завантаження Plan.Parts…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {loaded === "modifications" && validYear && !matches.length && !busy && <p role="status">Немає модифікацій із підтвердженим періодом виробництва для цього року.</p>}
      <SearchSelect label="Модифікація / двигун" value={ktype} disabled={busy || !validYear}
        options={matches.map(m => ({value:String(m.ktype),label:`${m.modification} · ${m.displacement_cc ?? "—"} см³ · ${m.power_kw ?? "—"} кВт / ${m.power_ps ?? "—"} к.с. · ${m.year_from ?? "?"}–${m.year_to ?? "кінець не вказано"} · K-Type ${m.ktype}`}))}
        onChange={setKtype} />
      {matches.length > 1 && <p>Знайдено кілька модифікацій. Підтвердьте потрібну вручну.</p>}
      {selected && selectedBrand && <>
        {!selectedModel?.name && !selected.model_series && <label>Назва моделі
          <input aria-label="Назва моделі" value={modelName} maxLength={100} onChange={e => setModelName(e.target.value)} />
          <small>Поле назви моделі постачальника ще не налаштоване. Вкажіть назву або перейдіть до ручного додавання.</small>
        </label>}
        <p>{selectedBrand.brand} · {name || `ID ${modelId}`} · {year} · K-Type {selected.ktype}</p>
        {name && <RecordForm key={`${brandId}:${modelId}:${year}:${ktype}:${name}`} initial={initial}
          fields={fields.filter(f => !["manufacturer", "model", "year", "engine", "generation"].includes(f.key))}
          onSave={d => onSave({ ...d, manufacturer:selectedBrand.brand, model:name, year:Number(year),
            engine:selected.modification, generation:"", ktype:selected.ktype })} />}
      </>}
    </>}
  </>;
}
