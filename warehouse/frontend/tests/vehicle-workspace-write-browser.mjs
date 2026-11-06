// Explicit writes ONLY to the synthetic donor created by seed_vehicle_workspace.py.
import { chromium, expect as baseExpect } from "@playwright/test";
import fs from "node:fs";
import assert from "node:assert/strict";
if (process.env.WAREHOUSE_E2E !== "1") throw Error("Local synthetic only");
const origin = "http://127.0.0.1:5223",
  f = JSON.parse(fs.readFileSync("/tmp/vehicle-workspace-fixture.json"));
assert(f.synthetic);
const b = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    args: ["--no-sandbox"],
  }),
  expect = baseExpect.configure({ timeout: 20000 });
try {
  const c = await b.newContext({
    baseURL: origin,
    viewport: { width: 1440, height: 1000 },
  });
  assert.equal(
    (
      await c.request.post("/api/v1/auth/login", {
        data: { email: f.email, password: f.password },
      })
    ).status(),
    200,
  );
  const before = await (await c.request.get("/api/v1/parts/" + f.part)).json();
  const p = await c.newPage(),
    errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto("/vehicles?donor=" + f.vehicle.id);
  const workspace = p.locator(".vp-workspace"),
    first = workspace.locator(".vp-row:not(.vp-table-head)").first();
  await first
    .getByRole("button", { name: "Артикули та OEM", exact: true })
    .click();
  const manager = workspace.locator(".vp-manager");
  await expect(manager).toContainText("Specification: synthetic-only");
  await manager.locator(".vp-offer input").first().check();
  await manager
    .getByRole("button", { name: "Призначити артикул", exact: true })
    .click();
  await manager
    .getByRole("button", { name: "Підтвердити запис номера", exact: true })
    .click();
  await expect(first).toContainText("SYN-1-1");
  await expect(first).toContainText("Synthetic Brand");
  await manager
    .getByRole("button", { name: "Підтвердити OEM вручну", exact: true })
    .click();
  await manager
    .getByLabel("OEM / код запчастини", { exact: true })
    .fill("SYNTHETIC-OEM-ONLY");
  await manager
    .getByRole("button", { name: "Зберегти характеристики", exact: true })
    .click();
  await expect(first).toContainText("SYNTHETIC-OEM-ONLY");
  const after = await (await c.request.get("/api/v1/parts/" + f.part)).json();
  for (const key of [
    "quantity",
    "reserved",
    "selling_price",
    "currency",
    "vehicle_id",
    "compatibility_notes",
  ])
    assert.equal(after[key], before[key], key);
  assert.equal(after.article_provenance.fitment_confirmed, false);
  assert.equal(after.oem_provenance.source, "manual");
  // Explicitly receive one NEW synthetic type, then repeat via the existing idempotent API.
  const second = workspace.locator(".vp-row:not(.vp-table-head)").nth(1);
  await second.locator("input[type=checkbox]").check();
  await workspace
    .getByRole("button", { name: "Додати вибрані (1)", exact: true })
    .click();
  await workspace
    .getByRole("button", { name: "Підтвердити додавання", exact: true })
    .click();
  await expect(second).toContainText("Уже на складі");
  const saved = await (
    await c.request.get(
      "/api/v1/plan-parts/workspace?vehicle_id=" + f.vehicle.id,
    )
  ).json();
  const target = saved.parts.find((r) => r.pt_id === 2);
  assert(target);
  const csrf = (await c.cookies()).find(
    (r) => r.name === "warehouse_csrf",
  ).value;
  const retry = await c.request.post(
    "/api/v1/plan-parts/donor-parts/add-batch?vehicle_id=" + f.vehicle.id,
    {
      headers: { "X-CSRF-Token": csrf },
      data: {
        items: [{ ktype: 131094, pt_id: 2, ukrainian_name: "Генератор" }],
      },
    },
  );
  assert.equal(retry.status(), 200);
  const same = await (await c.request.get("/api/v1/parts/" + target.id)).json();
  assert.equal(same.quantity, 1);
  // Explicit quoted mock request (the local API uses MockTransport, zero real tokens).
  await second.locator("input[type=checkbox]").check();
  await second
    .getByRole("button", { name: "Артикули та OEM", exact: true })
    .click();
  await manager
    .getByRole("button", { name: /^Отримати артикули · до 2 токенів$/ })
    .click();
  const quote = workspace.getByRole("alertdialog", {
    name: "Підтвердження API-запиту",
    exact: true,
  });
  await expect(quote).toContainText("2 токенів");
  await quote
    .getByRole("button", {
      name: "Підтвердити максимальну вартість",
      exact: true,
    })
    .click();
  await expect(workspace.locator(".vp-notice")).toContainText(
    "Отримані дані збережено",
  );
  await second
    .getByRole("button", { name: "Артикули та OEM", exact: true })
    .click();
  await expect(manager.locator(".vp-offer")).toHaveCount(3);
  await p.reload();
  await workspace
    .locator(".vp-row:not(.vp-table-head)")
    .nth(1)
    .getByRole("button", { name: "Артикули та OEM", exact: true })
    .click();
  await expect(manager.locator(".vp-offer")).toHaveCount(3);
  await workspace
    .locator(".vp-row:not(.vp-table-head)")
    .first()
    .getByRole("button", { name: "Артикули та OEM", exact: true })
    .click();
  await manager
    .getByLabel("Українська назва", { exact: true })
    .fill("Стартер перевірений");
  await manager
    .getByRole("button", { name: "Зберегти українську назву", exact: true })
    .click();
  await expect(first).toContainText("Стартер перевірений");
  await p.reload();
  await expect(
    workspace.locator(".vp-row:not(.vp-table-head)").first(),
  ).toContainText("Стартер перевірений");
  await p.goto("/search");
  await expect(p.locator("body")).toContainText("Пошук запчастин");
  const search = p.getByRole("combobox", {
    name: "Пошук запчастин",
    exact: true,
  });
  await search.fill("SYNTHETIC-OEM-ONLY");
  await expect(
    p.locator(".ui11-codes").filter({ hasText: "SYNTHETIC-OEM-ONLY" }),
  ).toContainText("Synthetic Brand");
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    "/tmp/vehicle-workspace-browser/write-results.json",
    JSON.stringify({
      synthetic_only: true,
      quoted_mock_request: true,
      saved_after_reload: true,
      article_assignment: true,
      manual_oem: true,
      stock_protected: true,
      explicit_new_stock: true,
      batch_replay_no_duplicate: true,
      search_brand_oem: true,
      no_live_calls: true,
    }),
  );
  await c.close();
  console.log("PASS synthetic write workflow");
} finally {
  await b.close();
}
