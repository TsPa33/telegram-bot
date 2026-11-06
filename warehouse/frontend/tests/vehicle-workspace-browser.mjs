// Actual built application + guarded local API/PostgreSQL + MockTransport. No live source.
import { chromium, expect as baseExpect } from "@playwright/test";
import fs from "node:fs";
import assert from "node:assert/strict";
const origin =
  process.env.WAREHOUSE_WORKSPACE_ORIGIN || "http://127.0.0.1:5223";
if (
  process.env.WAREHOUSE_E2E !== "1" ||
  new URL(origin).hostname !== "127.0.0.1"
)
  throw Error("Local synthetic only");
const f = JSON.parse(fs.readFileSync("/tmp/vehicle-workspace-fixture.json"));
assert(f.synthetic);
const out =
  process.env.WAREHOUSE_SCREENSHOTS || "/tmp/vehicle-workspace-browser";
fs.mkdirSync(out, { recursive: true });
const expect = baseExpect.configure({ timeout: 20000 }),
  b = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    args: ["--no-sandbox"],
  }),
  results = [];
try {
  const auth = await b.newContext({ baseURL: origin });
  const response = await auth.request.post("/api/v1/auth/login", {
    data: { email: f.email, password: f.password },
  });
  assert.equal(response.status(), 200);
  const state = await auth.storageState();
  await auth.close();
  for (const width of process.env.ONLY_WIDTH
    ? [Number(process.env.ONLY_WIDTH)]
    : [1440, 1280, 768, 390, 375]) {
    const c = await b.newContext({
      baseURL: origin,
      storageState: state,
      viewport: { width, height: 1000 },
    });
    const p = await c.newPage(),
      errors = [],
      paid = [],
      external = [];
    p.on("pageerror", (e) => errors.push(e.message));
    p.on("request", (r) => {
      if (r.url().includes("/plan-parts/") && r.url().includes("/lookup"))
        paid.push(r.url());
      if (!r.url().startsWith(origin) && !r.url().startsWith("data:"))
        external.push(r.url());
    });
    await p.goto("/vehicles?donor=" + f.vehicle.id);
    await p.waitForTimeout(700);

    const workspace = p.getByRole("region", {
      name: "Розбір і запчастини",
      exact: true,
    });
    await expect(workspace).toBeVisible();
    await expect(workspace.locator(".vp-row:not(.vp-table-head)")).toHaveCount(
      60,
    );
    await workspace
      .getByRole("button", { name: /Електрика та електроніка/ })
      .click();
    await expect(workspace.locator(".vp-row:not(.vp-table-head)")).toHaveCount(
      48,
    );
    await workspace
      .getByRole("button", { name: "Вибрати всі (48)", exact: true })
      .click();
    await expect(workspace.locator(".vp-actions")).toContainText("48 типів");
    await workspace.getByRole("button", { name: /Гальмівна система/ }).click();
    await expect(workspace.locator(".vp-row:not(.vp-table-head)")).toHaveCount(
      24,
    );
    await expect(workspace.locator(".vp-actions")).toContainText("48 типів");
    assert.equal(paid.length, 0);
    await workspace.getByRole("button", { name: /Усі категорії/ }).click();
    await workspace.getByRole("button", { name: /Показати ще 60/ }).click();
    await expect(workspace.locator(".vp-row:not(.vp-table-head)")).toHaveCount(
      96,
    );
    await workspace
      .getByRole("button", { name: "Зняти вибір", exact: true })
      .click();
    const first = workspace.locator(".vp-row:not(.vp-table-head)").first();
    await first.getByRole("button", { name: "Номери", exact: true }).click();
    const manager = workspace.getByRole("region", {
      name: "Артикули та OEM",
      exact: true,
    });
    await expect(manager.locator(".vp-offer")).toHaveCount(3);
    await expect(manager).toContainText("Synthetic Brand");
    await expect(
      manager.getByRole("button", {
        name: "Призначити OEM із API",
        exact: true,
      }),
    ).toBeDisabled();
    await p.evaluate(() => scrollTo({ left: 0, top: 0, behavior: "instant" }));
    await p.waitForTimeout(250);
    if (
      !(await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ))
    )
      console.log(
        "OVERFLOW",
        await p.evaluate(() => ({
          scrollX,
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth,
          body: document.body.scrollWidth,
          clipped: [...document.querySelectorAll("body *")]
            .filter(
              (e) =>
                e.scrollWidth > e.clientWidth + 2 &&
                getComputedStyle(e).overflowX === "visible",
            )
            .map((e) => ({
              cls: e.className,
              tag: e.tagName,
              cw: e.clientWidth,
              sw: e.scrollWidth,
              text: e.innerText?.slice(0, 40),
            }))
            .slice(-15),
          fixed: [...document.querySelectorAll("body *")]
            .filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
            .map((e) => ({
              cls: e.className,
              right: e.getBoundingClientRect().right,
              left: e.getBoundingClientRect().left,
            }))
            .slice(-10),
        })),
        await p.evaluate(() =>
          [...document.querySelectorAll("body *")]
            .filter(
              (e) =>
                e.getBoundingClientRect().right > innerWidth + 1 &&
                getComputedStyle(e).position !== "fixed",
            )
            .map((e) => ({
              cls: e.className,
              right: e.getBoundingClientRect().right,
              text: e.innerText?.slice(0, 30),
            }))
            .slice(-15),
        ),
      );
    assert(
      await p.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      "horizontal overflow " + width,
    );
    await p.screenshot({
      path: out + "/workspace-" + width + ".png",
      fullPage: false,
    });
    await workspace
      .locator(".vp-list h3")
      .evaluate((e) =>
        e.scrollIntoView({ block: "start", behavior: "instant" }),
      );
    await p.screenshot({ path: out + "/table-" + width + ".png" });
    await manager.scrollIntoViewIfNeeded();
    await p.screenshot({ path: out + "/manager-" + width + ".png" });
    await p.reload();
    await expect(workspace.locator(".vp-row:not(.vp-table-head)")).toHaveCount(
      60,
    );
    assert.equal(paid.length, 0);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    results.push({
      width,
      real_app: true,
      local_db: true,
      mock_provider: true,
      categories: true,
      selection_preserved: true,
      all96: true,
      saved_recovery: true,
      no_paid_lookup: true,
      no_js_errors: true,
      no_overflow: true,
    });
    await c.close();
    console.log("PASS", width);
  }
  fs.writeFileSync(out + "/results.json", JSON.stringify(results, null, 2));
} finally {
  await b.close();
}
