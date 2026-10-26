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
  expectedStatus?: number,
): Promise<T> {
  const headers: Record<string, string> = { "X-CSRF-Token": csrf(), "X-Warehouse-Client":"5" };
  if (body && !(body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers,
    body:
      body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });
  // An account switch in this browser must not deliver a previous user's data.
  // Keep mutation results uncertain (not a definitive 4xx) so replay keys survive.
  if(!path.startsWith('/auth/')&&csrf()!==headers['X-CSRF-Token']){
    window.dispatchEvent(new Event('warehouse:permissions-changed'));
    throw new Error('Сесію змінено. Оновіть доступ перед продовженням.');
  }
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
    if(response.status===403&&!path.startsWith('/auth/'))window.dispatchEvent(new Event('warehouse:permissions-changed'));
    throw new ApiError(message, response.status);
  }
  if (expectedStatus !== undefined && response.status !== expectedStatus)
    throw new ApiError("Сервер не підтвердив готовність функції.", response.status);
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
// Keep stored decimal prices as strings; BigInt formats cents without a float round-trip.
export const money = (value: unknown, currency = "UAH") => {
  if(value===undefined)return 'Доступ обмежено';
  const text=String(value??'0'),match=/^(-?)(\d+)(?:\.(\d*))?$/.exec(text);
  if(!match)return new Intl.NumberFormat('uk-UA',{style:'currency',currency,currencyDisplay:'code',minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value||0));
  const fraction=(match[3]||'').padEnd(2,'0');
  const cents=BigInt(match[2])*100n+BigInt(fraction.slice(0,2))+(Number(fraction[2]||'0')>=5?1n:0n);
  return `${match[1]}${new Intl.NumberFormat('uk-UA',{maximumFractionDigits:0}).format(cents/100n)},${String(cents%100n).padStart(2,'0')} ${currency}`;
};
export const when = (value: string) =>
  new Date(value).toLocaleString("uk-UA", {
    dateStyle: "short",
    timeStyle: "short",
  });
export const labels: Record<string, string> = {
  photo_create: "Додано фото",
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
