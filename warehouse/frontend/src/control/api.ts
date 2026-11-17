export type Row = Record<string, any>;
export type Staff = {
  id: string;
  username: string;
  role: string;
  active: boolean;
  can_finance: boolean;
  can_assign: boolean;
};
let expectedStaff: string | null = null;
const storageKey = "control.csrf";
const readProof = () => sessionStorage.getItem(storageKey) || "";

function clearSession(){expectedStaff=null;sessionStorage.removeItem(storageKey);window.dispatchEvent(new Event('control:session-invalid'));}
async function recoverProof() {
  const response = await fetch("/api/control/auth/csrf", {
    credentials: "same-origin", cache: "no-store",headers:expectedStaff?{'X-Control-Staff':expectedStaff}:{},
  });
  if (!response.ok){if(response.status===401)clearSession();throw new Error("Сесію завершено. Увійдіть повторно.");}
  const value = await response.json();
  if (!expectedStaff || value.staff_id !== expectedStaff)
    throw new Error("Обліковий запис змінився. Оновіть сторінку.");
  sessionStorage.setItem(storageKey, value.csrf);
  return value.csrf as string;
}

export async function api(path: string, method = "GET", body?: unknown) {
  const actor=expectedStaff;
  const assertActor=path!=="/auth/login"&&path!=="/auth/me"&&path!=="/status";
  const write = !["GET", "HEAD", "OPTIONS"].includes(method);
  const protectedWrite = write && path !== "/auth/login";
  const send = (csrf: string) => fetch("/api/control" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(assertActor&&actor?{'X-Control-Staff':actor}:{}),
      ...(protectedWrite ? { "X-Control-CSRF": csrf } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  // Logout may use an empty proof initially; a 401 is already signed out.
  let proof = protectedWrite ? readProof() || (path === "/auth/logout" ? "" : await recoverProof()) : "";
  let response = await send(proof);
  let value = response.status === 204 ? null : await response.json();
  // Only retry an explicit rejection before the action handler ran.
  // Never retry a timeout, general 403, or ambiguous write outcome.
  if (protectedWrite && response.status === 403 && value?.detail === "Недійсний CSRF-токен") {
    proof = await recoverProof();
    response = await send(proof);
    value = response.status === 204 ? null : await response.json();
  }
  if(assertActor&&actor!==expectedStaff)throw new Error('Staff-сесію змінено. Застарілу відповідь відхилено.');
  if(response.status===401&&path!=="/auth/login")clearSession();
  if (path === "/auth/logout" && response.status === 401) {
    expectedStaff = null;
    sessionStorage.removeItem(storageKey);
    return null;
  }
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Сесію завершено. Увійдіть повторно."
        : typeof value?.detail === "string"
          ? value.detail
          : "Запит не виконано",
    );
  if (path === "/auth/login") {
    expectedStaff = value.staff.id;
    sessionStorage.setItem(storageKey, value.csrf);
  } else if (path === "/auth/me") {
    expectedStaff = value.id;
  } else if (path === "/auth/logout" || path === "/auth/rotate" || path === "/auth/password") {
    expectedStaff = null;
    sessionStorage.removeItem(storageKey);
  }
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
  ACTIVE: "Чинний",
  TRIAL: "Пробний",
  GRACE: "Пільговий період",
  EXPIRED: "Завершено",
  FREE: "Без чинного періоду",
  UNKNOWN: "Недостатньо даних",
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
