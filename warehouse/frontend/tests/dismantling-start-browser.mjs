// A/B/C regression against local synthetic API + PostgreSQL. Never use on staging.
import { chromium, expect as baseExpect } from "@playwright/test";
import assert from "node:assert/strict";
import fs from "node:fs";
if (process.env.WAREHOUSE_E2E !== "1")
  throw Error("Local synthetic fixtures only");
const origin = "http://127.0.0.1:5223",
  f = JSON.parse(fs.readFileSync("/tmp/vehicle-workspace-fixture.json"));
assert(f.synthetic);
const expect = baseExpect.configure({ timeout: 30000 }),
  b = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    args: ["--no-sandbox"],
  }),
  out = "/tmp/carpot-start-browser";
fs.mkdirSync(out, { recursive: true });
const results = [];
try {
  const c = await b.newContext({
    baseURL: origin,
    viewport: { width: 1440, height: 1000 },
  });
  const login = await c.request.post("/api/v1/auth/login", {
    data: { email: f.email, password: f.password },
  });
  assert.equal(login.status(), 200);
  const csrf = (await login.json()).csrf_token;
  const created = await c.request.post("/api/v1/vehicles", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      manufacturer: "ALFA ROMEO",
      model: "147",
      year: 2009,
      donor_id: "SYNTHETIC-START-" + crypto.randomUUID(),
      acquisition_date: "2026-01-01",
      acquisition_cost: "0",
      ktype: 123,
    },
  });
  assert.equal(created.status(), 201);
  const v = await created.json();
  const p = await c.newPage(),
    errors = [],
    lookups = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("request", (r) => {
    if (r.url().includes("/plan-parts/") && r.url().includes("/lookup"))
      lookups.push(r.url());
  });
  await p.goto("/vehicles?donor=" + v.id);
  await expect(
    p.getByRole("button", { name: "Розібрати на запчастини", exact: true }),
  ).toBeVisible();
  await expect(p.locator(".vp-category-grid")).toHaveCount(0);
  await expect(p.locator(".vp-manager")).toHaveCount(0);
  await p.screenshot({ path: out + "/new-1440.png" });
  await p
    .getByRole("button", { name: "Розібрати на запчастини", exact: true })
    .click();
  await p
    .getByRole("button", { name: /Професійний каталог plan.parts/ })
    .click();
  await expect(
    p.getByRole("button", {
      name: "Сформувати список Plan.Parts",
      exact: true,
    }),
  ).toBeVisible();
  await expect(p.locator(".vp-category-grid")).toHaveCount(0);
  await p.getByRole("button", { name: /Базовий CarPot/ }).click();
  await p
    .getByRole("button", { name: "Сформувати базовий список", exact: true })
    .click();
  await p
    .getByRole("button", { name: "Підтвердити створення списку", exact: true })
    .click();
  await expect(p.getByText(/Список збережено · \d+ деталей/)).toBeVisible();
  const url = "/api/v1/vehicles/" + v.id + "/virtual-dismantling",
    first = await (await c.request.get(url)).json();
  assert(first.items.length > 0);
  assert.equal(first.counts.received, 0);
  assert(
    first.items.every(
      (i) => !i.stock || i.stock.physical_location_kind !== "on_shelf",
    ),
  );
  await p.reload();
  await expect(
    p.getByText("Список збережено · " + first.items.length + " деталей", {
      exact: true,
    }),
  ).toBeVisible();
  const restored = await (await c.request.get(url)).json();
  assert.deepEqual(
    restored.items.map((r) => r.id),
    first.items.map((r) => r.id),
  );
  assert.equal(restored.counts.received, 0);
  results.push({
    A: "PASS",
    B: "PASS",
    base_items: first.items.length,
    no_physical_receipt: true,
    no_duplicate_on_reload: true,
  });
  await p.goto("/vehicles?donor=" + f.vehicle.id);
  const ws = p.locator(".vp-workspace");
  await expect(ws.locator(".vp-row:not(.vp-table-head)")).toHaveCount(60);
  await expect(
    ws.getByText("Список збережено · 96 деталей", { exact: true }),
  ).toBeVisible();
  assert.equal(lookups.length, 0);
  await p.reload();
  await expect(ws.locator(".vp-row:not(.vp-table-head)")).toHaveCount(60);
  assert.equal(lookups.length, 0);
  await p.setViewportSize({ width: 390, height: 844 });
  await p.screenshot({ path: out + "/saved-390.png" });
  assert(
    await p.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  );
  results.push({ C: "PASS", saved_types: 96, paid_lookups: 0 });
  const unknown = await c.request.post("/api/v1/vehicles", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      manufacturer: "ALFA ROMEO",
      model: "147",
      year: 2009,
      donor_id: "SYNTHETIC-NO-MODIFICATION-" + crypto.randomUUID(),
      acquisition_date: "2026-01-01",
      acquisition_cost: "0",
    },
  });
  assert.equal(unknown.status(), 201);
  await p.goto("/vehicles?donor=" + (await unknown.json()).id);
  await p
    .getByRole("button", { name: "Розібрати на запчастини", exact: true })
    .click();
  await p
    .getByRole("button", { name: /Професійний каталог plan.parts/ })
    .click();
  await expect(
    p.getByText("Потрібно вибрати модифікацію", { exact: true }),
  ).toBeVisible();
  await expect(p.locator(".vp-category-grid")).toHaveCount(0);
  await expect(
    p.getByRole("button", {
      name: "Сформувати список Plan.Parts",
      exact: true,
    }),
  ).toBeDisabled();
  assert.equal(lookups.length, 0);
  assert(
    !/PostgreSQL|snapshot|payload|K-Type/.test(
      await p.locator(".vp-workspace").innerText(),
    ),
  );
  await p.screenshot({ path: out + "/choose-modification-390.png" });
  assert.deepEqual(errors, []);
  results.push({ missing_modification: "PASS", no_js_errors: true });
  fs.writeFileSync(out + "/results.json", JSON.stringify(results, null, 2));
  await c.close();
  console.log(JSON.stringify(results));
} finally {
  await b.close();
}
