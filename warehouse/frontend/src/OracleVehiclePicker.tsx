import {useEffect, useRef, useState} from 'react';
import {api, type Row} from './api';
import {DonorSummary, IntakeDisclosure, IntakeFeedback, PlanReady, displacement, measurement, modificationName} from './DonorIntakePresentation';

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

function productionPeriod(entry: Entry | null) {
  const dates = entry?.construction_interval?.trim().match(
    /^((?:(?:0?[1-9]|1[0-2])[./-])?\d{4}(?:[./]?(?:0[1-9]|1[0-2]))?)?\s*[-–—]\s*((?:(?:0?[1-9]|1[0-2])[./-])?\d{4}(?:[./]?(?:0[1-9]|1[0-2]))?)?$/,
  );
  const year = (date?: string) => Number(date?.match(/(?<!\d)(18\d{2}|19\d{2}|20\d{2}|2100)(?:[./]?[01]\d)?$/)?.[1]) || undefined;
  const start = year(dates?.[1]), end = year(dates?.[2]);
  return start && end && start > end ? {} : {start, end};
}

function inProductionYear(entry: Entry, year: string) {
  const {start, end} = productionPeriod(entry);
  return !/^\d{4}$/.test(year) || ((!start || Number(year) >= start) && (!end || Number(year) <= end));
}

function productionYears(model: Entry | null, variant: Entry | null) {
  const modelPeriod = productionPeriod(model);
  const variantPeriod = productionPeriod(variant);
  const start = variantPeriod.start ?? modelPeriod.start;
  const end = variantPeriod.end ?? modelPeriod.end;
  if (!(start || end)) return [];
  const first = Math.max(1886, start ?? 1886);
  const last = Math.min(2100, end ?? Math.max(first, new Date().getFullYear()));
  return Array.from({length: Math.max(0, last - first + 1)}, (_, index) => String(last - index));
}

function DirectorySelect({label, value, onChange, page, disabled, year, searchable, searchTerm, modelName, hint, wide, compact}: {
  label: string; value: Entry | null; onChange: (value: Entry | null) => void;
  page: ReturnType<typeof useDirectory>; disabled: boolean; year?: string; searchable?: boolean;
  searchTerm?: string; modelName?: string; hint?: string; wide?: boolean; compact?: boolean;
}) {
  const [filter, setFilter] = useState('');
  const items = page.items.filter(entry => (!year || inProductionYear(entry, year)) &&
    entry.name.toLocaleLowerCase().includes((searchTerm ?? filter).trim().toLocaleLowerCase()));
  if (value && !items.some(item => item.id === value.id)) items.unshift(value);
  const options = items.map(entry => ({entry, name: modelName ? modificationName(entry.name, modelName) : entry.name}));
  return <div className={'vin-directory-field'+(wide?' vin-field-wide':'')}>
    {searchable && page.items.length > 12 && <label>Пошук · {label.toLocaleLowerCase()}
      <input value={filter} disabled={disabled} onChange={e => setFilter(e.target.value)}/>
    </label>}
    <label>{label}
      <select value={value?.id ?? ''} disabled={disabled || !items.length}
        onChange={e => onChange(items.find(entry => entry.id === Number(e.target.value)) || null)}>
        <option value="">{page.loading ? 'Завантажуємо…' : hint || 'Оберіть зі списку'}</option>
        {options.map(({entry, name}) => <option key={entry.id} value={entry.id} title={entry.name}>
          {name}{entry.construction_interval && (compact
            ? options.some(other => other.entry !== entry && other.name === name) : !!year)
            ? ' · ' + entry.construction_interval.trim() : ''}
        </option>)}
      </select>
    </label>
    {page.error ? <IntakeFeedback kind="error"><p>Довідник тимчасово недоступний.</p>
      <button type="button" disabled={disabled} onClick={() => void page.load(page.next ?? 0)}>Повторити</button>
    </IntakeFeedback> : !disabled && !page.loading && !items.length && <p role="status">За цими умовами варіантів немає.</p>}
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
export default function OracleVehiclePicker({year, onYearChange, initialManufacturer = '', onChange, disabled}: {
  year: string; initialManufacturer?: string; onChange: (value: OracleVehicle | null) => void; disabled: boolean;
  onYearChange?: (year: string) => void;
}) {
  const [kind, setKind] = useState<Kind>('passenger');
  const [query, setQuery] = useState(initialManufacturer);
  const [search, setSearch] = useState(initialManufacturer);
  const [scope, setScope] = useState<'maker'|'model'|'variant'>('maker');
  const [modelFilter, setModelFilter] = useState('');
  const [variantFilter, setVariantFilter] = useState('');
  const [maker, setMaker] = useState<Entry | null>(null);
  const [model, setModel] = useState<Entry | null>(null);
  const [variant, setVariant] = useState<Entry | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [attempt, setAttempt] = useState(0);
  const directory = '/vehicles/vin/source-';
  const makers = useDirectory(directory + 'manufacturer-directory?kind=' + kind + '&name=' + encodeURIComponent(search));
  const models = useDirectory(maker ? directory + 'models?kind=' + kind + '&manufacturer_id=' + maker.id : '');
  const variants = useDirectory(model ? directory + 'modifications?kind=' + kind + '&model_id=' + model.id : '');
  const yearOptions = onYearChange ? productionYears(model, variant) : [];
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
    onYearChange?.('');
    setMaker(value);
    setModel(null);
    setVariant(null);
    setModelFilter('');
    setVariantFilter('');
    setScope('maker');
  }

  function chooseModel(value: Entry | null) {
    onChange(null);
    onYearChange?.('');
    setModel(value);
    setVariant(null);
    setVariantFilter('');
    if (scope === 'variant') setScope('model');
  }

  function chooseVariant(value: Entry | null) {
    onChange(null);
    if (year && onYearChange && !productionYears(model, value).includes(year)) onYearChange('');
    setVariant(value);
  }

  return <>
    {onYearChange && <div className="vin-catalogue-heading">
      <h3>Підбір із каталогу</h3>
      <IntakeDisclosure label="Пошук у каталозі" variant="link">
        <div className="vin-directory-search">
          <label>Шукати серед
            <select value={scope} disabled={disabled} onChange={e => setScope(e.target.value as typeof scope)}>
              <option value="maker">Марки</option>
              <option value="model" disabled={!maker}>Моделі</option>
              <option value="variant" disabled={!model}>Модифікації</option>
            </select>
          </label>
          {scope === 'maker' ? <label>Пошук марки
            <input value={query} maxLength={100} disabled={disabled} onChange={e => setQuery(e.target.value)}/>
          </label> : scope === 'model' ? <label>Пошук моделі
            <input value={modelFilter} maxLength={100} disabled={disabled} onChange={e => setModelFilter(e.target.value)}/>
          </label> : <label>Пошук модифікації
            <input value={variantFilter} maxLength={100} disabled={disabled} onChange={e => setVariantFilter(e.target.value)}/>
          </label>}
        </div>
      </IntakeDisclosure>
    </div>}
    <div className={'vin-fields'+(onYearChange?' vin-catalogue-fields':'')}>
      <label>Тип автомобіля
        <select value={kind} disabled={disabled} onChange={e => {chooseMaker(null); setKind(e.target.value as Kind);}}>
          <option value="passenger">Легковий</option><option value="commercial">Комерційний</option>
        </select>
      </label>
      {!onYearChange && <label>Пошук марки<input value={query} maxLength={100} disabled={disabled} onChange={e => {
        setQuery(e.target.value);
      }}/></label>}
      <DirectorySelect label="Марка" value={maker} onChange={chooseMaker} page={makers} disabled={disabled}/>
      {(maker || onYearChange) && <DirectorySelect key={kind + ':' + maker?.id} label="Модель" value={model} onChange={chooseModel}
        page={models} disabled={disabled || !maker} hint={maker?undefined:'Спочатку оберіть марку'}
        year={year} searchable={!onYearChange} searchTerm={onYearChange ? modelFilter : undefined} compact={!!onYearChange}/>}
      {onYearChange && <label className="vin-year">Рік автомобіля
        <select required value={year} disabled={disabled || !yearOptions.length} onChange={e => {
          onChange(null);
          onYearChange(e.target.value);
        }}>
          <option value="">{yearOptions.length ? 'Оберіть рік' : model ? 'Оберіть модифікацію' : 'Спочатку оберіть модель'}</option>
          {yearOptions.map(option => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>}
      {(model || onYearChange) && <DirectorySelect key={kind + ':variant:' + model?.id} label="Модифікація" value={variant}
        onChange={chooseVariant} page={variants} disabled={disabled || !model} hint={model?undefined:'Спочатку оберіть модель'}
        year={year} searchable={!onYearChange} searchTerm={onYearChange ? variantFilter : undefined}
        modelName={model?.name} wide={!!onYearChange} compact={!!onYearChange}/>}
    </div>
    {onYearChange && variant && !yearOptions.length && <p role="status">
      У каталозі відсутні роки виробництва. Цей автомобіль можна додати вручну.
    </p>}
    {variant && <>
      <DonorSummary title={[maker?.name, model?.name, validYear ? year : null].filter(Boolean).join(' · ')} facts={[
        ['Паливо', graph?.characteristics?.fuel_type],
        ['Привід', graph?.characteristics?.drive_type],
        ['Модифікація', modificationName(graph?.modification || variant.name, model?.name)],
        ['Об’єм', displacement(graph?.characteristics?.engine_displacement_l)],
        ['Потужність', measurement(graph?.characteristics?.engine_power_kw,'кВт')],
        ['Тип', kind === 'commercial' ? 'Комерційний' : 'Легковий'],
      ]}/>
      {!yearMatches ? <IntakeFeedback>Оберіть модифікацію, яку випускали в указаному році.</IntakeFeedback> :
        !graph ? <IntakeFeedback kind="loading">Готуємо план розбору…</IntakeFeedback> :
        graph.source_snapshot_sha ? <PlanReady counts={graph.counts}/> :
        <IntakeFeedback kind={graph.status === 'absent' ? 'note' : 'error'}>
          <p>{graphMessage[graph.status] || graphMessage.unavailable}</p>
          {graph.status !== 'absent' && <button type="button" disabled={disabled} onClick={() => setAttempt(n => n + 1)}>Повторити</button>}
        </IntakeFeedback>}
      {!!graph?.attributes?.length && <IntakeDisclosure label="Усі характеристики"><dl>
        {graph.attributes.map((item, i) => <div key={i}><dt>{item.attribute_type}</dt><dd>{item.display_value}</dd></div>)}
      </dl></IntakeDisclosure>}
    </>}
  </>;
}

export function CatalogueVehicleIntake({onCreated, onBack, saving, onSavingChange}: {
  onCreated: (row: Row) => void; onBack: () => void;
  saving: boolean; onSavingChange: (saving: boolean) => void;
}) {
  const [year, setYear] = useState('');
  const [selected, setSelected] = useState<OracleVehicle | null>(null);
  const [error, setError] = useState('');
  const request = useRef<string | null>(null);
  const writing = useRef(false);
  const validYear = /^\d{4}$/.test(year) && Number(year) >= 1886 && Number(year) <= 2100;
  return <form className="vin-intake" aria-label="Автомобіль із каталогу" onSubmit={async e => {
    e.preventDefault();
    if (!selected || !validYear || writing.current) return;
    writing.current = true;
    onSavingChange(true);
    setError('');
    request.current ||= crypto.randomUUID();
    try {
      const row = await api('/vehicles', 'POST', {
        intake_request_key: request.current, vin_intake_mode: 'catalogue',
        manufacturer: selected.manufacturer, model: selected.model, year: Number(year),
        source_identity: selected.identity, catalogue_graph_sha: selected.graph.source_snapshot_sha, status: 'planned',
      });
      onCreated(row);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      writing.current = false;
      onSavingChange(false);
    }
  }}>
    <div className="vin-content">
      <OracleVehiclePicker year={year} onYearChange={setYear} disabled={saving} onChange={setSelected}/>
      {error && <IntakeFeedback kind="error">{error}</IntakeFeedback>}
      {selected && !validYear && <IntakeFeedback>Вкажіть рік цього автомобіля.</IntakeFeedback>}
    </div>
    <div className="vin-footer"><div className="vin-actions">
      <button type="button" disabled={saving} onClick={onBack}>Скасувати</button>
      <button className="vin-submit" disabled={!selected || !validYear || saving}>{saving ? 'Зберігаємо…' : 'Додати автомобіль'}</button>
    </div></div>
  </form>;
}
