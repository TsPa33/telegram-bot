export type Row = Record<string, any>;
export type Staff = {
  id: string;
  username: string;
  role: string;
  active: boolean;
  can_finance: boolean;
  can_assign: boolean;
};
export async function api(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/control" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET"
        ? { "X-Control-CSRF": sessionStorage.getItem("control.csrf") || "" }
        : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = response.status === 204 ? null : await response.json();
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Увійдіть із staff MFA"
        : typeof value?.detail === "string"
          ? value.detail
          : "Запит не виконано",
    );
  return value;
}
export const date = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("uk-UA", {
        timeZone: "Europe/Kyiv",
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Немає даних";
export const money = (row: Row) =>
  typeof row.amount_minor === "number"
    ? new Intl.NumberFormat("uk-UA", {
        style: "currency",
        currency: row.currency || "UAH",
      }).format(row.amount_minor / 100)
    : "Немає даних";
export const states: Record<string, string> = {
  ACTIVE: "Оплачено",
  TRIAL: "Пробний",
  GRACE: "Пільговий період",
  EXPIRED: "Завершено",
  FREE: "Безкоштовний",
  UNKNOWN: "Немає даних",
};

export const coverageName: Record<string, string> = {
  sweep_complete: "Повний прохід завершено",
  partial_sweep: "Оновлення триває",
  incomplete: "Неповне покриття",
};
export const reasonName: Record<string, string> = {
  no_verified_billing_binding: "Немає перевіреного зв’язку з Billing",
  staff_finance_peer_not_configured:
    "Фінансовий доступ сервісу ще не налаштовано",
  billing_read_failed: "Billing тимчасово недоступний",
  invalid_verified_binding: "Зв’язок потребує перевірки",
};
