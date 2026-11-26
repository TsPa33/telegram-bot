import {useEffect, useRef, useState} from 'react';
import {api, type Row} from './api';

type Kind = 'passenger' | 'commercial';
type Entry = {id: number; name: string; construction_interval?: string};
type Graph = {
  status: string;
  source_snapshot_sha: string | null;
  modification?: string;
  counts?: {categories: number; positions: number};
  characteristics?: Record<string, string>;
  attributes?: {attribute_type: string; display_value: string}[];
};
export type OracleVehicle = {manufacturer: string; model: string; identity: Row; graph: Graph};
type DirectoryPage = {items: Entry[]; next_after: number | null};

function useDirectory(path: string) {
  const [view, setView] = useState({path: '', items: [] as Entry[], next: null as number | null,
    loading: false, error: false});
  const request = useRef<AbortController | null>(null);
  async function load(after = 0) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setView(old => ({path, items: after ? old.items : [], next: after ? old.next : null, loading: true, error: false}));
    try {
      const page = await api<DirectoryPage>(path + '&after=' + after, 'GET', undefined, undefined, {signal: controller.signal});
      if (!controller.signal.aborted) {
        setView(old => ({...old, items: after ? [...old.items, ...page.items] : page.items,
          next: page.next_after, loading: false}));
      }
    } catch {
      if (!controller.signal.aborted) setView(old => ({...old, loading: false, error: true}));
    }
  }

  useEffect(() => {
    if (path) void load();
    return () => request.current?.abort();
  }, [path]);

  return view.path === path ? {...view, load} :
    {items: [], next: null, loading: !!path, error: false, load};
}

function inProductionYear(entry: Entry, year: string) {
  const years = entry.construction_interval?.match(/(?:19|20)\d{2}/g)?.map(Number) || [];
  return !/^\d{4}$/.test(year) || !years.length ||
    (Number(year) >= years[0] && (years.length < 2 || Number(year) <= years[1]));
}

function DirectorySelect({label, value, onChange, page, disabled, year, searchable}: {
  label: string; value: Entry | null; onChange: (value: Entry | null) => void;
  page: ReturnType<typeof useDirectory>; disabled: boolean; year?: string; searchable?: boolean;
}) {
  const [filter, setFilter] = useState('');
  const items = page.items.filter(entry => (!year || inProductionYear(entry, year)) &&
    entry.name.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()));
  if (value && !items.some(item => item.id === value.id)) items.unshift(value);
  return <div className="vin-directory-field">
    {searchable && page.items.length > 12 && <label>Пошук · {label.toLocaleLowerCase()}
      <input value={filter} disabled={disabled} onChange={e => setFilter(e.target.value)}/>
    </label>}
    <label>{label}
      <select value={value?.id ?? ''} disabled={disabled || !items.length}
        onChange={e => onChange(items.find(entry => entry.id === Number(e.target.value)) || null)}>
        <option value="">{page.loading ? 'Завантажуємо…' : 'Оберіть зі списку'}</option>
        {items.map(entry => <option key={entry.id} value={entry.id}>
          {entry.name}{year && entry.construction_interval ? ' · ' + entry.construction_interval : ''}
        </option>)}
      </select>
    </label>
    {page.error ? <p role="alert">Довідник тимчасово недоступний.{' '}
      <button type="button" disabled={disabled} onClick={() => void page.load(page.next ?? 0)}>Повторити</button>
    </p> : !disabled && !page.loading && !items.length && <p role="status">За цими умовами варіантів немає.</p>}
    {!page.error && page.next !== null && <button type="button" disabled={disabled || page.loading}
      onClick={() => void page.load(page.next!)}>{page.loading ? 'Завантажуємо…' : 'Показати ще'}</button>}
  </div>;
}

const graphMessage: Record<string, string> = {
  absent: 'Для цієї модифікації запчастин у каталозі немає.',
  unavailable: 'Каталог запчастин тимчасово недоступний.',
  unsupported: 'Каталог запчастин тимчасово недоступний.',
  identity_mismatch: 'Модифікація змінилася в каталозі. Повторіть вибір.',
  unverified: 'Не вдалося підтвердити запчастини для цієї модифікації.',
};
const characteristicLabels: Record<string, string> = {
  fuel_type: 'Паливо', engine_displacement_l: 'Об’єм двигуна', engine_code: 'Двигун',
  engine_power_kw: 'Потужність', drive_type: 'Привід',
};

export default function OracleVehiclePicker({year, initialManufacturer = '', onChange, disabled}: {
  year: string; initialManufacturer?: string; onChange: (value: OracleVehicle | null) => void; disabled: boolean;
}) {
  const [kind, setKind] = useState<Kind>('passenger');
  const [query, setQuery] = useState(initialManufacturer);
  const [search, setSearch] = useState(initialManufacturer);
  const [maker, setMaker] = useState<Entry | null>(null);
  const [model, setModel] = useState<Entry | null>(null);
  const [variant, setVariant] = useState<Entry | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [attempt, setAttempt] = useState(0);
  const directory = '/vehicles/vin/source-';
  const makers = useDirectory(directory + 'manufacturer-directory?kind=' + kind + '&name=' + encodeURIComponent(search));
  const models = useDirectory(maker ? directory + 'models?kind=' + kind + '&manufacturer_id=' + maker.id : '');
  const variants = useDirectory(model ? directory + 'modifications?kind=' + kind + '&model_id=' + model.id : '');
  const validYear = /^\d{4}$/.test(year) && Number(year) >= 1886 && Number(year) <= 2100;
  const yearMatches = !variant || inProductionYear(variant, year);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setGraph(null);
    onChange(null);
    if (!maker || !model || !variant || !yearMatches) return;
    const controller = new AbortController();
    const identity = {kind, manufacturer_id: maker.id, model_id: model.id, source_modification_id: variant.id, confirmed: true};
    const params = new URLSearchParams({kind, manufacturer_id: String(maker.id), model_id: String(model.id),
      modification_id: String(variant.id), manufacturer: maker.name, model: model.name});
    if (validYear) params.set('year', year);
    api<Graph>(directory + 'graph?' + params, 'GET', undefined, undefined, {signal: controller.signal})
      .then(result => {
        if (controller.signal.aborted) return;
        setGraph(result);
        if (result.source_snapshot_sha) onChange({manufacturer: maker.name, model: model.name, identity, graph: result});
      })
      .catch(() => {
        if (!controller.signal.aborted) setGraph({status: 'unavailable', source_snapshot_sha: null});
      });
    return () => controller.abort();
  }, [kind, maker, model, variant, year, yearMatches, validYear, attempt, onChange]);

  function chooseMaker(value: Entry | null) {
    onChange(null);
    setMaker(value);
    setModel(null);
    setVariant(null);
  }

  function chooseModel(value: Entry | null) {
    onChange(null);
    setModel(value);
    setVariant(null);
  }

  return <>
    <div className="vin-fields">
      <label>Тип автомобіля
        <select value={kind} disabled={disabled} onChange={e => {chooseMaker(null); setKind(e.target.value as Kind);}}>
          <option value="passenger">Легковий</option><option value="commercial">Комерційний</option>
        </select>
      </label>
      <label>Пошук марки<input value={query} maxLength={100} disabled={disabled} onChange={e => {
        setQuery(e.target.value);
      }}/></label>
      <DirectorySelect label="Марка" value={maker} onChange={chooseMaker} page={makers} disabled={disabled}/>
      {maker && <DirectorySelect key={kind + maker.id} label="Модель" value={model} onChange={chooseModel}
        page={models} disabled={disabled} year={year} searchable/>}
      {model && <DirectorySelect key={kind + ':' + model.id} label="Модифікація" value={variant}
        onChange={value => {onChange(null); setVariant(value);}} page={variants} disabled={disabled} year={year} searchable/>}
    </div>
    {variant && <div className="vin-summary">
      <strong>{[maker?.name, model?.name, validYear ? year : null].filter(Boolean).join(' · ')}</strong>
      <p>{graph?.modification || variant.name}</p>
      {!!Object.keys(graph?.characteristics || {}).length && <dl>
        {Object.entries(characteristicLabels).flatMap(([field, label]) => graph?.characteristics?.[field] ?
          [<div key={field}><dt>{label}</dt><dd>{graph.characteristics[field]}</dd></div>] : [])}
      </dl>}
      {!!graph?.attributes?.length && <details><summary>Усі характеристики</summary><dl>
        {graph.attributes.map((item, i) => <div key={i}><dt>{item.attribute_type}</dt><dd>{item.display_value}</dd></div>)}
      </dl></details>}
      {!yearMatches ? <p role="status">Оберіть модифікацію, яку випускали в указаному році.</p> :
        !graph ? <p role="status">Готуємо план розбору…</p> :
        graph.source_snapshot_sha ? <p className="vin-ready" role="status">План розбору готовий
          {graph.counts && <> · Категорії {graph.counts.categories} · Запчастини {graph.counts.positions}</>}</p> :
        <p role={graph.status === 'absent' ? 'status' : 'alert'}>{graphMessage[graph.status] || graphMessage.unavailable}{' '}
          {graph.status !== 'absent' && <button type="button" disabled={disabled} onClick={() => setAttempt(n => n + 1)}>Повторити</button>}
        </p>}
    </div>}
  </>;
}

export function CatalogueVehicleIntake({vin, onCreated, onBack}: {
  vin?: string; onCreated: (row: Row) => void; onBack: () => void;
}) {
  const [year, setYear] = useState('');
  const [selected, setSelected] = useState<OracleVehicle | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const request = useRef<string | null>(null);
  const writing = useRef(false);
  const validYear = /^\d{4}$/.test(year) && Number(year) >= 1886 && Number(year) <= 2100;
  return <form className="vin-intake" aria-label="Автомобіль із каталогу" onSubmit={async e => {
    e.preventDefault();
    if (!selected || !validYear || writing.current) return;
    writing.current = true;
    setBusy(true);
    setError('');
    request.current ||= crypto.randomUUID();
    try {
      const row = await api('/vehicles', 'POST', {
        intake_request_key: request.current, vin_intake_mode: 'catalogue',
        vin: vin && /^[A-HJ-NPR-Z0-9]{17}$/.test(vin) ? vin : undefined,
        manufacturer: selected.manufacturer, model: selected.model, year: Number(year),
        source_identity: selected.identity, catalogue_graph_sha: selected.graph.source_snapshot_sha, status: 'planned',
      });
      onCreated(row);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }}>
    <label className="vin-year">Рік автомобіля<input required inputMode="numeric" maxLength={4}
      value={year} disabled={busy} onChange={e => {setSelected(null); setYear(e.target.value);}}/></label>
    <OracleVehiclePicker year={year} disabled={busy} onChange={setSelected}/>
    {error && <p role="alert">{error}</p>}
    {selected && !validYear && <p role="status">Вкажіть рік цього автомобіля.</p>}
    <div className="vin-footer"><div className="vin-actions">
      <button className="primary" disabled={!selected || !validYear || busy}>{busy ? 'Зберігаємо…' : 'Додати автомобіль'}</button>
      <button type="button" disabled={busy} onClick={onBack}>Скасувати</button>
    </div></div>
  </form>;
}
