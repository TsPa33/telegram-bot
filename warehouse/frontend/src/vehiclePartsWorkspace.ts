import type { Row } from "./api";
export const workspaceSections = [
  "Двигун та його системи",
  "Трансмісія та привід",
  "Підвіска та ходова частина",
  "Кермове управління",
  "Гальмівна система",
  "Кузов та зовнішні деталі",
  "Салон та інтер’єр",
  "Електрика та електроніка",
  "Освітлення",
  "Кліматична система",
  "Системи безпеки",
  "Обладнання та витратні матеріали",
  "Потребують уточнення",
];
export const sectionOf = (r: Row) =>
  workspaceSections.includes(r.classification?.section)
    ? r.classification.section
    : "Потребують уточнення";
export function filterWorkspace(
  rows: Row[],
  { section = "all", q = "", stock = "all", data = "all", oem = "all" }: Row,
  parts: Map<number, Row>,
  receipts: Map<number, Row>,
  offers: Record<number, Row[]>,
) {
  const query = q.trim().toLocaleLowerCase("uk-UA");
  return rows.filter((r) => {
    const p = parts.get(r.pt_id),
      saved = receipts.get(r.pt_id),
      records = offers[r.pt_id] || [];
    return (
      (section === "all" || sectionOf(r) === section) &&
      (!query ||
        [
          r.name,
          r.name_uk,
          p?.name,
          p?.article_number,
          p?.article_brand,
          p?.oem_number,
          ...records.flatMap((a) => [a.article_nr, a.brand, a.part_name]),
        ].some((x) =>
          String(x || "")
            .toLocaleLowerCase("uk-UA")
            .includes(query),
        )) &&
      (stock === "all" ||
        (stock === "stored" && !!p) ||
        (stock === "new" && !p)) &&
      (data === "all" ||
        (data === "saved" && !!saved?.stored) ||
        (data === "missing" && !saved?.stored) ||
        (data === "uncertain" && saved?.status === "uncertain")) &&
      (oem === "all" ||
        (oem === "yes" && !!p?.oem_number) ||
        (oem === "no" && !p?.oem_number))
    );
  });
}
export function changeWorkspaceSelection(
  previous: number[],
  ids: number[],
  checked: boolean,
) {
  const set = new Set(previous);
  ids.forEach((id) => (checked ? set.add(id) : set.delete(id)));
  return [...set];
}
export const priceQuote = (cost: unknown, count: number) =>
  typeof cost === "number" &&
  Number.isInteger(cost) &&
  cost >= 0 &&
  Number.isInteger(count) &&
  count > 0
    ? { known: true, max: cost * count }
    : { known: false, max: null };
