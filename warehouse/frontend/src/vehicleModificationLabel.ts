import type { Row } from "./api";
/** Stored provider ID is the selection; make/model/year alone never confirm it. */
export function vehicleModificationLabel(vehicle: Row, saved: Row[] = []) {
  if (!vehicle.ktype)
    return { label: "Модифікацію не вибрано", details: "", selected: false };
  const match = saved.find((m) => Number(m.ktype) === Number(vehicle.ktype));
  const engine = String(vehicle.engine || "").trim();
  const usable =
    engine &&
    !/^(потребує уточнення|не уточнено|не вказано|невідомо)$/iu.test(engine);
  const fields: [string, string][] = [
    ["displacement_cc", "см³"],
    ["power_kw", "кВт"],
    ["power_ps", "к.с."],
  ];
  return {
    label: match?.modification || (usable ? engine : "Модифікацію вибрано"),
    details: match
      ? fields
          .filter(
            ([key]) =>
              typeof match[key] === "number" && Number.isFinite(match[key]),
          )
          .map(([key, unit]) => `${match[key]} ${unit}`)
          .join(" · ")
      : "",
    selected: true,
  };
}
