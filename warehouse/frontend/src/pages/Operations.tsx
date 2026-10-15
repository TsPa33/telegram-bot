import {
  ArrowDownLeft,
  ArrowUpRight,
  Boxes,
  ClipboardList,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { all } from "../api";
import { Empty } from "../components";

import { Heading, State, useLoad, type Notify } from "../shared";
import { StockForm } from "./Inventory";
export default function Operations({ notify }: { notify: Notify }) {
  const {
    data: parts,
    error,
    loading,
    reload,
  } = useLoad(() => all("/parts"), []);
  const [id, setId] = useState("");
  const part = parts?.find((p) => p.id === id);
  return (
    <>
      <Heading
        eyebrow="КОНТРОЛЬ РУХУ ЗАПАСІВ"
        title="Операції зі складом"
        description="Надходження, списання, резерви, коригування та переміщення."
      />
      <div className="two-column">
        <section className="panel padded">
          <div className="panel-title">
            <h2>Нова операція</h2>
            <ArrowDownLeft size={19} />
          </div>
          <State error={error} loading={loading} />
          {parts?.length ? (
            <>
              <label className="standalone-field">
                Запчастина
                <select
                  aria-label="Запчастина для операції"
                  value={id}
                  onChange={(e) => setId(e.target.value)}
                >
                  <option value="">Оберіть позицію</option>
                  {parts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ·{" "}
                      {p.oem_number || p.article_number || p.id.slice(0, 8)} ·{" "}
                      {p.location || "Без місця"} · залишок {p.quantity}
                    </option>
                  ))}
                </select>
              </label>
              {part && (
                <StockForm
                  key={
                    part.id +
                    ":" +
                    part.quantity +
                    ":" +
                    part.reserved_quantity +
                    ":" +
                    part.location
                  }
                  part={part}
                  onDone={() => {
                    reload();
                    notify("Операцію проведено та записано в історію");
                  }}
                />
              )}
            </>
          ) : (
            !loading && (
              <Empty title="Ще немає запчастин">
                <Link to="/inventory">Додайте позицію до складу</Link>, потім
                проведіть її надходження.
              </Empty>
            )
          )}
        </section>
        <section className="panel padded">
          <h2>Точність кожного руху</h2>
          <div className="rules">
            <span>
              <ShieldCheck />
              <div>
                <b>Транзакційний облік</b>
                <p>Одночасні зміни захищено блокуванням запису в базі.</p>
              </div>
            </span>
            <span>
              <Boxes />
              <div>
                <b>Залишки без розбіжностей</b>
                <p>
                  Резерв не перевищує залишок. Зарезервовані одиниці не можна
                  списати.
                </p>
              </div>
            </span>
            <span>
              <ClipboardList />
              <div>
                <b>Незмінна історія</b>
                <p>
                  Кожна завершена операція зберігає автора, причину, час і
                  обидва баланси.
                </p>
              </div>
            </span>
          </div>
          <Link to="/analytics" className="button">
            Переглянути журнал <ArrowUpRight size={16} />
          </Link>
        </section>
      </div>
    </>
  );
}
