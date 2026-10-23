import { useState } from "react";
import { api, labels, money, type Row } from "./api";
import { Modal, RecordForm } from "./components";
import { State, useLoad } from "./shared";

type Group = {name: string; items: Row[]};
export default function Dismantling({vehicle, onChange, onInventory}: {vehicle: Row; onChange: () => void; onInventory: () => void}) {
  const path = `/vehicles/${vehicle.id}/dismantling`;
  const {data, error, loading, reload} = useLoad(() => api(path), [vehicle.id]);
  const [query, setQuery] = useState(""), [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [receiving, setReceiving] = useState<Row[] | null>(null);
  function done() {reload(); onChange();}
  async function action(ids: string[], name: string) {
    setBusy(true); setMessage("");
    try {const r = await api(path+"/actions", "POST", {ids, action:name}); setMessage(`Оновлено: ${r.updated}. Без змін: ${r.skipped}. Залишки не змінено.`);setSelected([]);done();return true;}
    catch(e) {setMessage((e as Error).message);return false;} finally {setBusy(false);}
  }
  const items: Row[] = data?.items || [];
  const filtered = items.filter(row => `${row.category_name} ${row.subcategory_name} ${row.name} ${row.position}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const groups = new Map<string, Map<string, Group>>();
  for(const item of filtered) {
    if(!groups.has(item.category_key)) groups.set(item.category_key, new Map());
    const sub = groups.get(item.category_key)!;
    if(!sub.has(item.subcategory_key)) sub.set(item.subcategory_key, {name:item.subcategory_name, items:[]});
    sub.get(item.subcategory_key)!.items.push(item);
  }
  const canEdit = data && !data.archived && !vehicle.archived;
  const chosen = items.filter(item => selected.includes(item.id) && !item.received_at);
  const title = (item: Row) => item.name+(item.position ? ` · ${item.position}` : "");
  function toggle(ids: string[], checked: boolean) {setSelected(values => checked ? [...new Set([...values,...ids])] : values.filter(id => !ids.includes(id)));}
  return <section className="dismantling-workspace" aria-label="Робочий екран розбору">
    <h3>Розбір автомобіля</h3>
    <State error={error} loading={loading} />
    {error && <button onClick={reload}>Повторити читання розбору</button>}
    {data && <>
      <p>Статус: <strong>{labels[data.status]}</strong></p>
      <div className="detail-stats" aria-label="Показники розбору">
        <span>Потенційних позицій<strong>{data.potential_positions}</strong></span>
        <span>Демонтованих позицій<strong>{data.dismantled_positions}</strong></span>
        <span>Позицій на складі<strong>{data.stock_positions}</strong></span>
        <span>Продано одиниць<strong>{data.sold_units}</strong></span>
      </div>
      <small>Продажі — лише операції «Продаж». Списання не вважаються продажами.</small>
      <div className="modal-actions">
        {canEdit && <button className="primary" disabled={busy} onClick={async () => {
          setBusy(true);setMessage("");
          try {const r = await api(path+"/start", "POST");setMessage(r.created ? `Створено потенційних позицій: ${r.created}.` : "Продовжуємо збережений розбір.");done();}
          catch(e) {setMessage((e as Error).message);} finally {setBusy(false);}
        }}>{items.length ? "Продовжити розбір" : "Почати розбір"}</button>}
        <button onClick={onInventory}>Склад цього автомобіля</button>
      </div>
      {message && <p role="status">{message}</p>}
      {!!items.length && <>
        <p className="notice">Універсальний список: комплектацію не підтверджено. Лише явне оприбуткування змінює склад.</p>
        <label className="standalone-field">Пошук деталей<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label>
        {canEdit && chosen.length > 0 && <div className="dismantling-bulk">
          <p>Вибрано позицій: {chosen.length}</p>
          <div className="modal-actions">
            <button disabled={busy || !chosen.length} onClick={() => action(chosen.map(i => i.id),"dismantled")}>Демонтовано вибрані</button>
            <button disabled={busy || !chosen.length} onClick={() => action(chosen.map(i => i.id),"absent")}>Відсутні вибрані</button>
            <button disabled={busy || !chosen.length} onClick={() => action(chosen.map(i => i.id),"damaged")}>Пошкоджені вибрані</button>
            <button disabled={busy || !chosen.length} onClick={() => setReceiving(chosen)}>Оприбуткувати вибрані ({chosen.length})</button>
          </div>
        </div>}
        {!filtered.length && <p>Деталей за цим пошуком немає.</p>}
        {[...groups].map(([category, subs]) => <details key={category} open={query ? true : undefined}>
          <summary>{[...subs.values()][0].items[0].category_name} · {[...subs.values()].reduce((n,s) => n+s.items.length,0)}</summary>
          {[...subs].map(([key, sub]) => {
            const available = sub.items.filter(i => !i.received_at).map(i => i.id);
            return <section key={key} className="dismantling-subcategory">
              <h4>{sub.name}</h4>
              {canEdit && !!available.length && <label className="dismantling-select"><input type="checkbox" aria-label={`Вибрати підкатегорію ${sub.name}`} checked={available.every(id => selected.includes(id))} disabled={busy} onChange={e => toggle(available,e.target.checked)} /> Вибрати підкатегорію ({available.length})</label>}
              {sub.items.map(item => <article className="dismantling-item" key={item.id}>
                <div className="dismantling-item-title">
                  {canEdit && !item.received_at && <input type="checkbox" aria-label={`Вибрати ${title(item)}`} disabled={busy} checked={selected.includes(item.id)} onChange={e => toggle([item.id],e.target.checked)} />}
                  <strong>{title(item)}</strong>
                </div>
                <p>{labels[item.status]}{item.condition && ` · ${labels[item.condition]}`} · {item.received_at ? `Оприбутковано: ${item.quantity} од.` : "На склад не оприбутковано"}</p>
                {item.stock && <p>Залишок: {item.stock.quantity} · Стан: {labels[item.stock.condition]} · Місце: {item.stock.location || "не вказано"} · Ціна: {item.stock.selling_price == null ? "не вказано" : money(item.stock.selling_price)}{item.stock.archived && " · Позицію архівовано"}</p>}
                {canEdit && !item.received_at && <div className="modal-actions">
                  <button disabled={busy} onClick={async () => {if(await action([item.id],"dismantled")) setReceiving([item]);}}>Демонтовано</button>
                  <button disabled={busy} onClick={() => action([item.id],"absent")}>Відсутня</button>
                  <button disabled={busy} onClick={() => action([item.id],"damaged")}>Пошкоджена</button>
                  <button disabled={busy} onClick={() => action([item.id],"unchecked")}>Не перевірено</button>
                  <button disabled={busy || item.status === "absent"} onClick={() => setReceiving([item])}>Оприбуткувати на склад</button>
                </div>}
              </article>)}
            </section>;
          })}
        </details>)}
      </>}
    </>}
    {receiving && <Modal title="Підтвердити оприбуткування" onClose={() => setReceiving(null)}>
      <p>Позицій: {receiving.length}. Кількість нижче — для кожної позиції.</p>
      <p>{receiving.length === 1 ? title(receiving[0]) : "Вибрані деталі будуть оприбутковані однією транзакцією."}</p>
      <RecordForm submit="Оприбуткувати на склад" initial={{quantity:1,condition:""}} fields={[
        {key:"quantity",label:"Кількість",type:"number",required:true,min:1,max:1000000,step:1},
        {key:"condition",label:"Стан",options:[{value:"",label:"Типово: вживана; для пошкодженої — пошкоджена"},...["used","new","damaged","refurbished"].map(value => ({value,label:labels[value]}))]},
        {key:"location",label:"Місце на складі"},
        {key:"selling_price",label:"Ціна одиниці, ₴",type:"number",min:0},
      ]} onSave={async values => {
        const result = await api(path+"/actions", "POST", {...values,condition:values.condition || null,action:"receipt",ids:receiving.map(item => item.id)});
        setReceiving(null);setSelected([]);setMessage(`Оприбутковано позицій: ${result.updated}. Уже оброблено: ${result.skipped}.`);done();
      }} />
    </Modal>}
  </section>;
}
