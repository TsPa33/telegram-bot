import {CarFront, Check, ChevronDown, CircleAlert, LoaderCircle} from 'lucide-react';
import type {ReactNode} from 'react';

export function DonorSummary({title, facts}: {title: string; facts: [string, unknown][]}) {
  const known = facts.filter(([, value]) => value != null && String(value).trim());
  return <section className="vin-summary" aria-label="Зведення автомобіля">
    <div className="vin-summary-heading">
      <span className="vin-summary-icon" aria-hidden="true"><CarFront size={24}/></span>
      <h3>{title}</h3>
    </div>
    {!!known.length && <dl className="vin-summary-facts">
      {known.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}
    </dl>}
  </section>;
}

export function PlanReady({counts, construction = false}: {counts?: {categories: number; positions: number}; construction?: boolean}) {
  return <div className="vin-ready" role="status">
    <span className="vin-ready-icon" aria-hidden="true"><Check size={22}/></span>
    <div className="vin-ready-copy">
      <strong>План розбору готовий</strong>
      <p>{construction ? "Master доповнить план конструктивними позиціями під час додавання" : "Каталог сформовано з вибраної модифікації"}</p>
    </div>
    {counts && <div className="vin-ready-counts">
      <span>Категорії: <b>{counts.categories}</b></span>
      <span>{construction ? "Типи Oracle" : "Запчастини"}: <b>{counts.positions}</b></span>
    </div>}
  </div>;
}

export type ConstructionFacts = {kind?: string; body?: string; side_doors?: number};
const bodyOptions = {
  sedan: 'Седан', hatch: 'Хетчбек', suv: 'Позашляховик', coupe: 'Купе', wagon: 'Універсал',
  convertible: 'Кабріолет', van: 'Фургон', pickup: 'Пікап', tractor: 'Сідельний тягач', truck: 'Вантажний автомобіль',
};
export function ConstructionFields({value, onChange, disabled, showKind = true}: {
  value: ConstructionFacts; onChange: (value: ConstructionFacts) => void; disabled: boolean; showKind?: boolean;
}) {
  const bodies = value.kind === 'heavy_truck' ? ['tractor', 'truck'] as const :
    Object.keys(bodyOptions).filter(body => body !== 'tractor' && body !== 'truck') as (keyof typeof bodyOptions)[];
  return <div className="vin-fields">
    {showKind && <label>Клас автомобіля
      <select value={value.kind || ''} disabled={disabled} onChange={e => onChange({kind: e.target.value || undefined})}>
        <option value="">Невідомо</option><option value="passenger">Легковий</option>
        <option value="lcv">Легкий комерційний</option><option value="heavy_truck">Вантажний</option>
      </select>
    </label>}
    <label>Тип кузова
      <select value={value.body || ''} disabled={disabled} onChange={e => onChange({...value, body: e.target.value || undefined, side_doors: undefined})}>
        <option value="">Невідомо</option>{bodies.map(body => <option key={body} value={body}>{bodyOptions[body]}</option>)}
      </select>
    </label>
    {value.body && ['sedan', 'hatch', 'suv', 'wagon', 'convertible'].includes(value.body) && <label>Бічні двері
      <select value={value.side_doors || ''} disabled={disabled} onChange={e => onChange({...value, side_doors: Number(e.target.value) || undefined})}>
        <option value="">Невідомо</option><option value="2">2</option><option value="4">4</option>
      </select>
    </label>}
  </div>;
}

export function IntakeFeedback({children, kind = 'note'}: {
  children: ReactNode; kind?: 'note' | 'loading' | 'error';
}) {
  const Icon = kind === 'loading' ? LoaderCircle : CircleAlert;
  return <div className={'vin-feedback vin-feedback-' + kind} role={kind === 'error' ? 'alert' : 'status'}>
    <Icon size={18} aria-hidden="true"/>
    <div>{children}</div>
  </div>;
}

export function IntakeDisclosure({label, children, variant = 'panel'}: {
  label: string; children: ReactNode; variant?: 'panel' | 'link';
}) {
  return <details className={'vin-disclosure vin-disclosure-' + variant}>
    <summary>{label}<ChevronDown size={16} aria-hidden="true"/></summary>
    <div className="vin-disclosure-body">{children}</div>
  </details>;
}

export function ModelYearOptions({current}: {current?: string}) {
  const lastYear = Math.min(2100, new Date().getFullYear() + 1);
  const reportedYear = Number(current);
  const outsideRange = current && (!/^\d{4}$/.test(current) || reportedYear < 1886 || reportedYear > 2100);
  return <>
    <option value="">{current === undefined ? 'Оберіть рік' : 'Рік не вказано'}</option>
    {outsideRange && <option>{current}</option>}
    {Array.from({length: lastYear - 1886 + 1}, (_, index) => lastYear - index).map(year =>
      <option key={year} value={year}>{year}</option>)}
    {lastYear < 2100 && <optgroup label="Майбутні модельні роки">
      {Array.from({length: 2100 - lastYear}, (_, index) => lastYear + index + 1).map(year =>
        <option key={year} value={year}>{year}</option>)}
    </optgroup>}
  </>;
}

export function modificationName(description: string, model?: string) {
  const name = description.replace(/\s+/g, ' ').trim();
  const prefix = model?.replace(/\s+/g, ' ').trim();
  if (!prefix || name.slice(0, prefix.length).toLocaleLowerCase('uk') !== prefix.toLocaleLowerCase('uk')) return name;
  const tail = name.slice(prefix.length);
  return /^\s|^[·,:–—]/.test(tail) ? tail.replace(/^[\s·,:–—]+/, '') || name : name;
}

export function measurement(value: unknown, unit: string) {
  if (value == null || String(value).trim() === '') return undefined;
  const label = String(value).trim();
  return /^\d+([.,]\d+)?$/.test(label) ? `${label} ${unit}` : label;
}

export function displacement(value: unknown) {
  const label = String(value ?? '').trim();
  const match = /^(\d+(?:[.,]\d+)?)\s*(cc|ccm|cm[³3]|см[³3]|l|л)?$/i.exec(label);
  if (!match) return label;
  const amount = Number(match[1].replace(',', '.'));
  const cubicCentimeters = match[2] ? !/^[lл]$/i.test(match[2]) : amount >= 100;
  const liters = cubicCentimeters ? amount / 1000 : amount;
  return `${new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 3}).format(liters)} л`;
}
