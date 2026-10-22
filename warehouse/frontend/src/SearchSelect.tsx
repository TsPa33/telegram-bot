import { useEffect, useId, useRef, useState } from "react";

type Option = {value: string; label: string};
export default function SearchSelect({label, value, options, disabled = false, manual = false, required = false, onChange}: {
  label: string; value: string; options: Option[]; disabled?: boolean;
  manual?: boolean; required?: boolean; onChange: (value: string) => void;
}) {
  const id = useId(), input = useRef<HTMLInputElement>(null), typing = useRef(false);
  const selected = options.find(o => o.value === value)?.label || value;
  const [query, setQuery] = useState(selected), [open, setOpen] = useState(false), [active, setActive] = useState(-1);
  useEffect(() => {if(typing.current) {typing.current=false;return;} setQuery(selected); setOpen(false); setActive(-1);}, [selected]);
  const filtered = options.filter(o => o.label.toLocaleLowerCase().includes(query.toLocaleLowerCase())).slice(0, 60);
  const rows = manual && query.trim() && !options.some(o => o.label.toLocaleLowerCase() === query.trim().toLocaleLowerCase())
    ? [...filtered, {value: query.trim(), label: `Використати «${query.trim()}»`}]: filtered;
  const index = Math.max(0, Math.min(active, Math.max(0, rows.length - 1)));
  function choose(option: Option) {onChange(option.value); setQuery(option.label.startsWith("Використати «") ? option.value : option.label); setOpen(false);}
  return <div className="vehicle-combobox" onBlur={e => {if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);}}>
    <label htmlFor={id}>{label}{required ? " *" : ""}</label>
    <input ref={input} id={id} aria-label={label} role="combobox" autoComplete="off" aria-autocomplete="list"
      aria-expanded={open} aria-controls={`${id}-list`} aria-activedescendant={open && rows.length ? `${id}-${index}` : undefined}
      required={required} maxLength={100} disabled={disabled} value={query} placeholder="Оберіть або введіть…"
      onFocus={() => {setOpen(true); setActive(-1);}}
      onChange={e => {setQuery(e.target.value); setOpen(true); setActive(-1); if(value) {typing.current=true; onChange("");}}}
      onKeyDown={e => {
        if(e.key === "ArrowDown" || e.key === "ArrowUp") {e.preventDefault(); setOpen(true); setActive(n => Math.max(0, Math.min(rows.length - 1, n + (e.key === "ArrowDown" ? 1 : -1))));}
        if(e.key === "Escape") {e.preventDefault(); e.stopPropagation(); setOpen(false);}
        if(e.key === "Enter" && open) {e.preventDefault(); if(rows[index]) choose(rows[index]);}
      }} />
    {open && <ul id={`${id}-list`} role="listbox" aria-label={label}>
      {rows.map((option, n) => <li role="option" id={`${id}-${n}`} key={option.value} aria-selected={n === index}
        onMouseDown={e => e.preventDefault()} onClick={() => {choose(option); input.current?.focus();}}>{option.label}</li>)}
      {!rows.length && <li role="presentation">Немає варіантів</li>}
    </ul>}
  </div>;
}
