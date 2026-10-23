export type Row = Record<string, any>;
export type Page = { items: Row[]; total: number };
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export const csrf = () =>
  decodeURIComponent(
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("warehouse_csrf="))
      ?.split("=")[1] || "",
  );
export async function api<T = Row>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { "X-CSRF-Token": csrf() };
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers,
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let message = "Не вдалося виконати запит. Спробуйте ще раз.";
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : data.detail
              ?.map((d: Row) => `${d.loc?.slice(1).join(".")}: ${d.msg}`)
              .join("; ") || message;
    } catch {
      /* network response has no JSON */
    }
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("warehouse:logout"));
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export async function all(path: string): Promise<Row[]> {
  const rows: Row[] = [];
  let offset = 0;
  for (;;) {
    const page = await api<Page>(
      `${path}${path.includes("?") ? "&" : "?"}limit=200&offset=${offset}`,
    );
    rows.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || !page.items.length) return rows;
  }
}
export const money = (value: unknown) =>
  new Intl.NumberFormat("uk-UA", {
    style: "currency",
    currency: "UAH",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
export const when = (value: string) =>
  new Date(value).toLocaleString("uk-UA", {
    dateStyle: "short",
    timeStyle: "short",
  });
export const labels: Record<string, string> = {
  receipt: "Надходження",
  write_off: "Списання",
  sale: "Продаж",
  dismantled: "Демонтовано",
  dismantling_plan: "План розбору",
  dismantling_catalog_import: "Імпорт власного каталогу",
  dismantling_start: "Початок розбору",
  dismantling_status: "Перевірка демонтажу",
  dismantling_receipt: "Оприбуткування з розбору",
  reserve: "Резервування",
  release: "Зняття резерву",
  correction: "Коригування",
  transfer: "Переміщення",
  archive: "Архівування",
  restore: "Відновлення",
  vehicle_create: "Додано донора",
  vehicle_update: "Зміна донора",
  part_create: "Додано позицію",
  part_update: "Зміна картки",
  checklist_create: "Створення чекліста",
  category_import: "Імпорт категорії",
  unchecked: "Не перевірено",
  present: "Наявна",
  absent: "Відсутня",
  damaged: "Пошкоджена",
  used: "Вживана",
  new: "Нова",
  refurbished: "Відновлена",
  planned: "Заплановано",
  dismantling: "Розбирання",
  completed: "Завершено",
  category: "Категорія",
  subcategory: "Підкатегорія",
  part: "Запчастина",
};
