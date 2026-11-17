import test from "node:test";
import assert from "node:assert/strict";
import {
  parseRoute,
  directoryQuery,
  nextDirectoryHref,
  periodStatus,
  periodCount,
  profileHref,
  taskUrgency,
} from "../src/control/model.ts";
test("profile links preserve an encoded identity and reject unknown sections", () => {
  const id = "company with & / delimiter";
  const r = parseRoute(profileHref(id, "notes"));
  assert.equal(r.id, id);
  assert.equal(r.section, "notes");
  assert.equal(parseRoute("#/company/%E0%A4%A/notes").view, "missing");
  assert.equal(parseRoute("#/company/a/danger").view, "missing");
});
test("directory requests carry only allowed filters and server cursor, never page-local totals", () => {
  const q = new URLSearchParams({
    q: "A & B",
    status: "UNKNOWN",
    registered_from: "2026-11-01",
    manager: "staff-a",
    sort: "registered",
    cursor: "opaque+/=",
    limit: "999",
    finance: "yes",
  });
  const next = directoryQuery(q);
  assert.equal(next.get("limit"), "20");
  assert.equal(next.get("q"), "A & B");
  assert.equal(next.has("finance"), false);
  const href = nextDirectoryHref(q, "next+/=");
  const parsed = parseRoute(href);
  assert.equal(parsed.query.get("cursor"), "next+/=");
  assert.equal(parsed.query.get("status"), "UNKNOWN");
  assert.equal(parsed.query.get("registered_from"), "2026-11-01");
  assert.equal(
    parseRoute(nextDirectoryHref(parsed.query)).query.has("cursor"),
    false,
  );
});
test("missing authority always stays UNKNOWN, including a misleading FREE payload", () => {
  assert.equal(
    periodStatus({ access_incomplete: true, access: { status: "FREE" } }),
    "UNKNOWN",
  );
  assert.equal(
    periodStatus({ access_incomplete: false, access: { status: "FREE" } }),
    "FREE",
  );
  assert.equal(periodStatus({}), "UNKNOWN");
});
test("scoped metrics distinguish unavailable data from a known zero", () => {
  assert.equal(periodCount(null, ["ACTIVE"]), null);
  assert.equal(
    periodCount({ workspaces: null, states: { ACTIVE: 5 } }, ["ACTIVE"]),
    null,
  );
  assert.equal(periodCount({ workspaces: 0, states: {} }, ["ACTIVE"]), 0);
  assert.equal(
    periodCount(
      { workspaces: 8, states: { ACTIVE: 2, TRIAL: 1, GRACE: 1, UNKNOWN: 4 } },
      ["ACTIVE", "TRIAL", "GRACE"],
    ),
    4,
  );
});
test("urgency derives from real due time and Kyiv day, not stored synthetic priorities", () => {
  const now = Date.parse("2026-11-17T21:50:00Z");
  assert.equal(
    taskUrgency({ due_at: "2026-11-17T21:49:00Z" }, now).label,
    "Прострочено",
  );
  assert.equal(
    taskUrgency({ due_at: "2026-11-17T22:10:00Z" }, now).label,
    "За планом",
  );
  assert.equal(
    taskUrgency({ due_at: "2026-11-17T21:55:00Z" }, now).label,
    "Сьогодні",
  );
  assert.equal(
    taskUrgency({ status: "done", due_at: "2020-01-01" }, now).label,
    "Завершено",
  );
  assert.equal(taskUrgency({ due_at: null }, now).label, "Без строку");
  assert.equal(
    taskUrgency({ due_at: "invalid" }, now).label,
    "Строк невідомий",
  );
});
