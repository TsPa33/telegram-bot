// Controlled failures and out-of-order reads against local API fixtures only.
import { chromium, webkit } from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
import assert from "node:assert/strict";
if (process.env.CONTROL_CENTER_BROWSER_TEST !== "1")
  throw Error("Fixture opt-in required");
const origin =
  process.env.CONTROL_CENTER_BROWSER_ORIGIN || "http://127.0.0.1:5269";
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw Error("Loopback only");
const fixture = JSON.parse(
  fs.readFileSync(
    process.env.CONTROL_CENTER_BROWSER_FIXTURE_FILE ||
      "/tmp/control-browser-fixture.json",
    "utf8",
  ),
);
function otp() {
  const b = Buffer.alloc(8);
  b.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto
      .createHmac("sha1", Buffer.from("12345678901234567890"))
      .update(b)
      .digest(),
    o = h.at(-1) & 15;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1000000).padStart(6, "0");
}
const result = [];
let index = 32;
for (const [engine, driver] of Object.entries({ chromium, webkit })) {
  const b = await driver.launch();
  try {
    for (const width of [390, 1440]) {
      const c = await b.newContext({
          baseURL: origin,
          viewport: { width, height: 960 },
        }),
        p = await c.newPage(),
        errors = [];
      p.on("pageerror", (e) => errors.push(e.message));
      await p.goto("/control/");
      await p.getByLabel("Логін", { exact: true }).fill("browser-" + index++);
      await p.getByLabel("Пароль", { exact: true }).fill(fixture.password);
      await p.getByLabel("MFA-код", { exact: true }).fill(otp());
      await p.getByRole("button", { name: "Увійти", exact: true }).click();
      await p
        .getByRole("heading", { name: "Огляд клієнтів", exact: true })
        .waitFor();
      await p.route("**/api/control/overview", (r) =>
        r.fulfill({ status: 503, json: { detail: "Overview fault fixture" } }),
      );
      await p.getByRole("button", { name: "Оновити", exact: true }).click();
      await p
        .getByRole("alert")
        .filter({ hasText: "Overview fault fixture" })
        .waitFor();
      assert.deepEqual(
        await p.locator(".cc-metric strong").allTextContents(),
        Array(4).fill("Немає даних"),
      );
      await p.unroute("**/api/control/overview");
      await p.getByRole("button", { name: "Оновити", exact: true }).click();
      const alpha = fixture.companies[0],
        beta = fixture.companies[1];
      let release, started;
      const gate = new Promise((r) => (release = r)),
        entered = new Promise((r) => (started = r));
      await p.route("**/api/control/companies/" + alpha.id, async (r) => {
        started();
        await gate;
        await r.continue();
      });
      await p.evaluate(
        (id) => (location.hash = "#/company/" + id + "/overview"),
        alpha.id,
      );
      await entered;
      await p.evaluate(
        (id) => (location.hash = "#/company/" + id + "/overview"),
        beta.id,
      );
      await p.getByRole("heading", { name: beta.name, exact: true }).waitFor();
      assert(
        (await p.getByText("Недостатньо даних", { exact: true }).count()) > 0,
      );
      const old = p.waitForResponse((r) =>
        r.url().endsWith("/companies/" + alpha.id),
      );
      release();
      await old;
      await p.waitForTimeout(30);
      assert.equal(
        await p.getByRole("heading", { name: alpha.name, exact: true }).count(),
        0,
      );
      await p.unroute("**/api/control/companies/" + alpha.id);
      await p.route("**/api/control/companies/" + beta.id + "/notes", (r) =>
        r.request().method() === "GET"
          ? r.fulfill({ status: 503, json: { detail: "Notes fault fixture" } })
          : r.continue(),
      );
      await p
        .locator(".cc-profile-tabs")
        .getByRole("link", { name: "Нотатки", exact: true })
        .click();
      await p
        .getByRole("alert")
        .filter({ hasText: "Notes fault fixture" })
        .waitFor();
      assert.equal(
        await p.getByRole("heading", { name: beta.name, exact: true }).count(),
        1,
      );
      await p
        .locator(".cc-profile-tabs")
        .getByRole("link", { name: "Продукти", exact: true })
        .click();
      await p
        .getByRole("heading", { name: "Продукти клієнта", exact: true })
        .waitFor();
      await p.unroute("**/api/control/companies/" + beta.id + "/notes");
      const long = "Я".repeat(120);
      await p.route("**/api/control/companies/" + alpha.id, async (r) => {
        const res = await r.fetch(),
          data = await res.json();
        data.display_name = long;
        await r.fulfill({ response: res, json: data });
      });
      await p.evaluate(
        (id) => (location.hash = "#/company/" + id + "/overview"),
        alpha.id,
      );
      await p.getByRole("heading", { name: long, exact: true }).waitFor();
      assert.equal(
        await p.evaluate(
          () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
      );
      assert.deepEqual(errors, []);
      result.push({
        engine,
        width,
        unavailableNotZero: true,
        outOfOrderCompanyRead: true,
        independentSectionFailure: true,
        longNameLayout: true,
      });
      await c.close();
    }
  } finally {
    await b.close();
  }
}
console.log(JSON.stringify({ passed: result.length, result }));
