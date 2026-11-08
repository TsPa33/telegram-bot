import type { Row } from "./api";

export type PlanChoice = "catalogue" | "professional" | "base";
/** Presentation only. Backend remains authoritative for coverage and all writes. */
export function verifiedOption(row?: Row) {
  return !!row && row.coverage_verified === true && row.taxonomy_status === "reviewed";
}
export function supportedModel(vehicle: Row) {
  const identity = `${vehicle.model || ""} ${vehicle.generation || ""}`;
  if (/XC90\s+II\b/i.test(identity)) return "13084";
  if (/XC60\s+II\b/i.test(identity)) return "37773";
  return "";
}
export function nextChoice(row?: Row): PlanChoice {
  return verifiedOption(row) ? "catalogue" : "base";
}
export function vehicleFacts(vehicle: Row) {
  return [vehicle.manufacturer, vehicle.model, vehicle.year, vehicle.engine,
    vehicle.fuel_type, vehicle.drive_type].filter(v => v && !/^(unknown|невідомо|не вказано)$/i.test(String(v))).join(" · ");
}
export function modificationTitle(row: Row, index: number) {
  return [row.modification?.description || (typeof row.modification==="string" ? row.modification : row.description) || "Комплектація",
    row.modification?.constructioninterval || row.year_from,
    row.engine_code, row.power_kw ? `${row.power_kw} кВт` : "",
    `варіант ${index + 1}`].filter(Boolean).join(" · ");
}
export function flowStep(saved: boolean, prepared: boolean) {
  return saved ? 3 : prepared ? 2 : 1;
}
export function userMessage(message: string) {
  if (/недостатн.{0,35}токен|insufficient.{0,35}token/i.test(message)) return "Недостатньо токенів. Поповніть баланс або виберіть безкоштовний стандартний план.";
  if (/SHA|snapshot|payload|PostgreSQL|K-Type|etag|API|cache|source_modification/i.test(message))
    return "Не вдалося завершити дію. Збережені дані залишилися на місці. Оновіть сторінку або перевірте комплектацію.";
  return message.replace(/plan\.parts/gi, "додатковий каталог");
}
