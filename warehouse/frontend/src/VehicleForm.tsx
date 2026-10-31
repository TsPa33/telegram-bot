import { useRef, useState } from "react";
import { api, type Row } from "./api";
import { RecordForm, type Field } from "./components";
import { useLoad } from "./shared";
import SearchSelect from "./SearchSelect";
import VehicleDirectoryPicker from './VehicleDirectoryPicker';

type Brand = {brand: string; mfa_id: number};
type Model = {ms_id: number; name: string; year_from: number | null; year_to: number | null};
type Modification = {ktype: number; modification: string; displacement_cc: number | null; power_kw: number | null; power_ps: number | null; year_from: number | null; year_to: number | null};
type Local = {complete: false; brands: {name: string; models: string[]}[]};

export default function VehicleForm({initial, fields, onSave}: {initial: Row; fields: Field[]; onSave: (data: Row) => Promise<void>}) {
  const [provider, setProvider] = useState(false);
  const [brand, setBrand] = useState(initial.manufacturer || ""), [model, setModel] = useState(initial.model || "");
  const [year, setYear] = useState(String(initial.year || "")), [engine, setEngine] = useState(initial.engine || "");
  const [brandId, setBrandId] = useState(""), [modelId, setModelId] = useState(""), [ktype, setKtype] = useState("");
  const [brands, setBrands] = useState<Brand[]>([]), [models, setModels] = useState<Model[]>([]), [mods, setMods] = useState<Modification[]>([]);
  const [busy, setBusy] = useState(false), [saving, setSaving] = useState(false), [error, setError] = useState("");
  const generation = useRef(0);
  const local = useLoad(() => api<Local>("/vehicle-catalog"), []);
  const directoryBrands = useLoad(() => api<string[]>('/vehicle-directory/brands'), []);
  const [directoryModels,setDirectoryModels]=useState<string[]>([]);
  const [selectedDirectory,setSelectedDirectory]=useState<Row|null>(null);
  useEffect(()=>{if(!brand||provider){setDirectoryModels([]);return;}let active=true;
   api<string[]>('/vehicle-directory/models?brand='+encodeURIComponent(brand)).then(rows=>{if(active)setDirectoryModels(rows)}).catch(()=>{if(active)setDirectoryModels([])});
   return()=>{active=false};
  },[brand,provider]);
  const brandOptions=[...new Set([...(local.data?.brands||[]).map(b=>b.name),...(directoryBrands.data||[])])].sort((a,b)=>a.localeCompare(b,'uk'));
  const modelOptions=[...new Set([...(local.data?.brands.find(b=>b.name===brand)?.models||[]),...directoryModels])].sort((a,b)=>a.localeCompare(b,'uk'));
  function resetModel() {generation.current++; setModel(""); setModelId(""); setYear(""); setEngine(""); setKtype(""); setMods([]);setSelectedDirectory(null);}
  async function lookup(resource: string, query = "") {
    const requestGeneration = generation.current;
    setBusy(true); setError("");
    try {
      const rows = await api<any[]>(`/plan-parts/${resource}/lookup${query}`, "POST");
      if(requestGeneration !== generation.current) return;
      if(resource === "brands") setBrands(rows);
      if(resource === "models") setModels(rows);
      if(resource === "modifications") setMods(rows);
      if(!rows.length) setError("Результатів немає. Скористайтеся локальним або ручним додаванням.");
    } catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  const chosenModel = models.find(m => String(m.ms_id) === modelId);
  const lower = provider ? chosenModel?.year_from ?? 1886 : 1886;
  const upper = provider ? chosenModel?.year_to ?? new Date().getFullYear() : new Date().getFullYear();
  const years = Array.from({length: Math.max(0, upper - lower + 1)}, (_, i) => upper - i);
  const matches = mods.filter(m => year && m.year_from !== null && m.year_from <= Number(year) && (m.year_to === null || m.year_to >= Number(year)));
  const selected = matches.find(m => String(m.ktype) === ktype);
  const valid = brand && model && /^\d{4}$/.test(year) && Number(year) >= 1886 && Number(year) <= 2100 && (!provider || ((!chosenModel?.year_from || Number(year) >= chosenModel.year_from) && (!chosenModel?.year_to || Number(year) <= chosenModel.year_to)));
  const primary = {manufacturer:brand, model, year:Number(year),
    engine: selectedDirectory?([selectedDirectory.displacement_l,selectedDirectory.fuel_type].filter(Boolean).join(' ')||engine):engine,
    ...(selectedDirectory?{
      engine_displacement_l:selectedDirectory.displacement_l?Number(selectedDirectory.displacement_l):null,
      fuel_type:selectedDirectory.fuel_type||'',
      engine_code:selectedDirectory.engine_codes?.length===1?selectedDirectory.engine_codes[0]:null,
      drive_type:selectedDirectory.drive_type||null,
    }:{}),
    ktype: provider ? selected?.ktype ?? null : ["manufacturer", "model", "year", "engine"].every(k => String(initial[k] ?? "") === String(({manufacturer:brand,model,year,engine} as Row)[k] ?? "")) ? initial.ktype ?? null : null};
  return <>
    <form className="quick-vehicle" onSubmit={async e => {
      e.preventDefault(); if(!valid || busy || saving) return;
      setSaving(true);setError("");
      try {await onSave(primary);} catch(e) {setError((e as Error).message);} finally {setSaving(false);}
    }}>
      <div className="form-grid">
        <SearchSelect label="Марка" required value={provider ? brandId : brand} disabled={busy || saving} manual={!provider}
          options={provider ? brands.map(b => ({value:String(b.mfa_id),label:b.brand})) : brandOptions.map(name=>({value:name,label:name}))}
          onChange={value => {resetModel();setModels([]);setBrandId(provider ? value : "");setBrand(provider ? brands.find(b => String(b.mfa_id) === value)?.brand || "" : value);}} />
        <SearchSelect key={`model-${brand}`} label="Модель" required value={provider ? modelId : model} disabled={!brand || busy || saving} manual={!provider}
          options={provider ? models.filter(m => m.name).map(m => ({value:String(m.ms_id),label:m.name})) : modelOptions.map(name=>({value:name,label:name}))}
          onChange={value => {generation.current++;setModelId(provider ? value : "");setModel(provider ? models.find(m => String(m.ms_id) === value)?.name || "" : value);setYear("");setEngine("");setKtype("");setMods([]);setSelectedDirectory(null);}} />
        <label>Рік випуску *<select aria-label="Рік випуску" required value={year} disabled={!model || busy || saving} onChange={e => {setYear(e.target.value);setKtype("");setEngine("");setSelectedDirectory(null);}}>
          <option value="">Оберіть…</option>
          {year && !years.includes(Number(year)) && <option value={year}>{year}</option>}
          {years.map(y => <option key={y} value={y}>{y}</option>)}
          {(!provider || !chosenModel?.year_from || !chosenModel?.year_to) && <option value="custom">Інший рік…</option>}
        </select></label>
        <SearchSelect key={`engine-${brand}-${model}-${year}`} label="Двигун / модифікація" value={provider ? ktype : engine} manual={!provider} disabled={!year || !model || busy || saving}
          options={matches.map(m => ({value:String(m.ktype),label:`${m.modification} · ${m.displacement_cc ?? "—"} см³ · ${m.power_kw ?? "—"} кВт / ${m.power_ps ?? "—"} к.с. · ${m.year_from ?? "?"}–${m.year_to ?? "кінець не вказано"} · K-Type ${m.ktype}`}))}
          onChange={value => {setKtype(provider ? value : "");setEngine(provider ? matches.find(m => String(m.ktype) === value)?.modification || "" : value);}} />
      </div>
      {!provider&&directoryBrands.data&&directoryBrands.data.length>0&&<VehicleDirectoryPicker brand={brand} model={model} year={year} onPick={setSelectedDirectory}/>}
      {(year === "custom" || (year && !years.includes(Number(year)))) && <label>Уточнити рік<input aria-label="Уточнити рік" type="number" min={1886} max={2100} value={year === "custom" ? "" : year} onChange={e => setYear(e.target.value)} /></label>}
      {provider && chosenModel && <small>Каталог: {chosenModel.year_from ?? "початок невідомий"}–{chosenModel.year_to ?? "кінець невідомий"}. Для року поза діапазоном скористайтеся локальним додаванням.</small>}
      <details className="vehicle-provider"><summary>Точний підбір Plan.Parts</summary>
        <label><input type="checkbox" checked={provider} disabled={busy || saving} onChange={e => {setProvider(e.target.checked);resetModel();setBrand("");setBrandId("");setModels([]);setError("");}} /> Використати Plan.Parts</label>
        <small>Лише явні запити; можуть витрачати токени. Локальне додавання працює без API.</small>
        {provider && <div className="modal-actions">
          <button type="button" disabled={busy} onClick={() => lookup("brands")}>Завантажити марки / повторити</button>
          <button type="button" disabled={busy || !brandId} onClick={() => lookup("models",`?mfa_id=${brandId}`)}>Завантажити моделі / повторити</button>
          <button type="button" disabled={busy || !modelId || !/^\d{4}$/.test(year)} onClick={() => lookup("modifications",`?ms_id=${modelId}`)}>Завантажити модифікації / повторити</button>
        </div>}
      </details>
      {!provider && brand.toLowerCase()==='volvo' && ['XC40','XC60','XC90'].includes(model.toUpperCase()) && <small>Довідник Aleto, якщо імпортований у ваш робочий простір, доступний у картці автомобіля. Сумісність за роком та комплектацією потребує перевірки.</small>}
      {!provider && <small>Довідник модифікацій — підказка, а не підтвердження сумісності деталей. Якщо конкретного авто немає, використайте ручне введення.</small>}
      {!provider && local.error && <small role="status">Довідник недоступний. Ручне введення працює. <button type="button" onClick={local.reload}>Повторити</button></small>}
      {busy && <p role="status">Завантаження Plan.Parts…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="modal-actions"><button className="primary" disabled={!valid || busy || saving}>{initial.id ? "Зберегти" : "Додати автомобіль"}</button></div>
    </form>
    {initial.id && <details><summary>Додаткові дані</summary>
      <RecordForm fields={fields.filter(f => !["manufacturer","model","year","engine"].includes(f.key))} initial={initial}
        onSave={values => onSave({manufacturer:initial.manufacturer,model:initial.model,year:initial.year,...values})} />
    </details>}
  </>;
}
