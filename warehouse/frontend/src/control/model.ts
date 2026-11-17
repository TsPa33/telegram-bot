import type { Row } from "./api";
export const sections = [
  "overview",
  "products",
  "people",
  "finance",
  "activity",
  "notes",
  "history",
] as const;
export type Section = (typeof sections)[number];
export type Route = {
  view: "overview" | "clients" | "company" | "queue" | "security" | "missing";
  id?: string;
  section?: Section;
  query: URLSearchParams;
};
export const filterKeys = [
  "q",
  "plan",
  "status",
  "linking",
  "manager",
  "registered_from",
  "sort",
] as const;
export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "") || "overview",
    [path, search = ""] = raw.split("?");
  const parts = path.split("/"),
    query = new URLSearchParams(search);
  if (parts[0] === "company" && parts[1]) {
    try {
      const section = parts[2] || "overview";
      return sections.includes(section as Section)
        ? {
            view: "company",
            id: decodeURIComponent(parts[1]),
            section: section as Section,
            query,
          }
        : { view: "missing", query };
    } catch {
      return { view: "missing", query };
    }
  }
  return {
    view: ["overview", "clients", "queue", "security"].includes(parts[0])
      ? (parts[0] as Route["view"])
      : "missing",
    query,
  };
}
export const profileHref = (id: string, section: Section = "overview") =>
  `#/company/${encodeURIComponent(id)}/${section}`;
export function directoryQuery(query: URLSearchParams): URLSearchParams {
  const value = new URLSearchParams();
  for (const key of [...filterKeys, "cursor"] as const) {
    const v = query.get(key);
    if (v) value.set(key, v);
  }
  value.set("limit", "20");
  if (!value.has("sort")) value.set("sort", "name");
  return value;
}
export function nextDirectoryHref(
  query: URLSearchParams,
  cursor?: string,
): string {
  const next = directoryQuery(query);
  next.delete("limit");
  if (cursor) next.set("cursor", cursor);
  else next.delete("cursor");
  return "#/clients?" + next;
}
export function periodStatus(company: Row): string {
  return company.access_incomplete
    ? "UNKNOWN"
    : company.access?.status || "UNKNOWN";
}
export function periodCount(
  overview: Row | null,
  statuses: string[],
): number | null {
  if (!overview || overview.workspaces == null || !overview.states) return null;
  return statuses.reduce((n, k) => n + Number(overview.states[k] || 0), 0);
}
export function taskUrgency(
  task: Row,
  at = Date.now(),
): { label: string; tone: string } {
  if (task.status === "done") return { label: "Завершено", tone: "neutral" };
  if (!task.due_at) return { label: "Без строку", tone: "neutral" };
  const due = Date.parse(task.due_at);
  if (!Number.isFinite(due))
    return { label: "Строк невідомий", tone: "neutral" };
  if (due < at) return { label: "Прострочено", tone: "danger" };
  const day = (n: number) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Kyiv" }).format(n);
  return day(due) === day(at)
    ? { label: "Сьогодні", tone: "warn" }
    : { label: "За планом", tone: "neutral" };
}
export const taskStatuses: Record<string, string> = {
  open: "Відкрите",
  in_progress: "У роботі",
  done: "Завершено",
};
