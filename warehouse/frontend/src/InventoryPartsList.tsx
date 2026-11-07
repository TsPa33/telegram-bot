import {partRowInteraction} from "./partRowInteraction";
import InventoryQuantity from "./InventoryQuantity";
import { useCan } from "./permissions";
import type { ReactNode } from "react";
import { Package } from "lucide-react";
import { type Row } from "./api";
import { PriceSummary } from "./CompactParts";
import { SellerPriceEditor } from "./MarketPricing";
import { inventoryStockKind } from "./inventoryPresentation";
const states: Record<string, string> = {
  available: "В наявності",
  reserved: "Зарезервована",
  empty: "Без залишку",
  excluded: "Виключена",
  archived: "Архівна",
};
export function InventoryTableHead({
  dashboard = false,
  sort = "name",
  onSort,
}: {
  dashboard?: boolean;
  sort?: string;
  onSort?: (key: string) => void;
} = {}) {
  return (
    <div
      className={"ui3-table-head" + (dashboard ? " r115-table-head" : "")}
      aria-label="Колонки складу"
    >
      <span>
        {onSort ? (
          <button
            type="button"
            onClick={() => onSort("name")}
            aria-label="Сортувати за назвою"
          >
            Запчастина {sort === "name" ? "↕" : ""}
          </button>
        ) : (
          "Запчастина"
        )}
      </span>
      <span>Автомобіль</span>
      <span>
        {onSort ? (
          <button
            type="button"
            onClick={() => onSort("quantity")}
            aria-label="Сортувати за залишком"
          >
            Залишок {sort === "quantity" ? "↕" : ""}
          </button>
        ) : (
          "Залишок"
        )}
      </span>
      {dashboard && <span>OEM / Артикул</span>}

      {!dashboard && <span>Ринкова ціна</span>}
      <span>
        {onSort ? (
          <button
            type="button"
            onClick={() => onSort("price")}
            aria-label="Сортувати за власною ціною"
          >
            Моя ціна {sort === "price" ? "↕" : ""}
          </button>
        ) : (
          "Моя ціна"
        )}
      </span>
      <span>Дії</span>
    </div>
  );
}
export function InventoryPartRow({
  part: p,
  categories,
  vehicle,
  market,
  marketError,
  selected,
  canSelect,
  onSelect,
  onOpen,
  onSaved,
  actions,
  photo,
  extra,
  dashboard = false,
}: {
  part: Row;
  categories: Row[];
  vehicle?: Row;
  market?: Row;
  marketError?: string;
  selected: boolean;
  canSelect: boolean;
  onSelect: (checked: boolean) => void;
  onOpen: () => void;
  onSaved: (p: Row) => void;
  actions: ReactNode;
  photo?: ReactNode;
  extra?: ReactNode;
  dashboard?: boolean;
}) {
  const can = useCan();
  const category = categories.find((c) => c.id === p.category_id),
    sub = categories.find((c) => c.id === p.subcategory_id),
    kind = inventoryStockKind(p);
  return (
    <article
      {...partRowInteraction}
      className={"ui3-part" + (dashboard ? " r115-part" : "")}
      aria-label={p.name}
    >
      <div className="ui3-identity">
        {canSelect && (
          <input
            type="checkbox"
            aria-label={`Вибрати ${p.name}`}
            checked={selected}
            onChange={(e) => onSelect(e.target.checked)}
          />
        )}
        {photo || (
          <span className="ui3-photo" role="img" aria-label="Фото відсутнє">
            <Package size={22} strokeWidth={1.3} />
          </span>
        )}
        <div>
          <button className="ux1-part-name" title={p.name} onClick={onOpen}>
            {p.name}
          </button>
          <small>
            {category?.name || "Потребує уточнення"} ›{" "}
            {sub?.name || "Підкатегорію уточнити"}
          </small>
          {extra}
        </div>
      </div>
      <div className="ui3-donor">
        {vehicle ? (
          <>
            <span>
              {vehicle.manufacturer} {vehicle.model}
            </span>
            <small>
              {vehicle.year} · №{vehicle.number}
            </small>
          </>
        ) : (
          <span>{p.vehicle_id ? "Автомобіль донора" : "Без автомобіля"}</span>
        )}
      </div>
      <div className="ui3-stock">
        <span className={"ux1-status " + kind}>{states[kind]}</span>
        <InventoryQuantity key={p.id} part={p} onSaved={onSaved} />
        <small>
          {p.physical_location_kind === "on_vehicle"
            ? "На автомобілі"
            : p.physical_location_kind === "on_shelf"
              ? "На складі"
              : "Розташування не уточнене"}
        </small>
        {p.quantity_basis === "assumed" && (
          <small>Кількість потребує перевірки</small>
        )}
        {p.reserved_quantity > 0 && (
          <small>
            Резерв: {p.reserved_quantity} · Вільно:{" "}
            {p.assortment_enabled === false ? 0 : p.available_quantity}
          </small>
        )}
      </div>
      {dashboard && (
        <div className="r115-codes">
          <strong>OEM: {p.oem_number || "Не визначено"}</strong>
          <small>
            {p.article_number || "Артикул не призначено"}
            {p.article_number && p.article_brand ? " · " + p.article_brand : ""}
          </small>
        </div>
      )}
      {!dashboard && (
        <div className="ui3-market">
          {!can("catalog.view") ? (
            <span className="ux1-muted">Ринкові ціни недоступні</span>
          ) : marketError ? (
            <span className="ux1-muted">Не вдалося завантажити ціни</span>
          ) : (
            <PriceSummary g={market} showRelated />
          )}
        </div>
      )}
      <div className="ui3-own">
        <SellerPriceEditor part={p} compact onSaved={onSaved} />
      </div>
      <div className="ui3-actions">{actions}</div>
    </article>
  );
}
