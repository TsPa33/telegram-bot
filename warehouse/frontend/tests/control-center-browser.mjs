// Real local API + disposable PostgreSQL; synthetic staff/company fixtures only.
import { chromium, webkit } from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
import assert from "node:assert/strict";
if (process.env.CONTROL_CENTER_BROWSER_TEST !== "1")
  throw Error("Explicit local fixture opt-in required");
const fixture = JSON.parse(
  fs.readFileSync(
    process.env.CONTROL_CENTER_BROWSER_FIXTURE_FILE ||
      "/tmp/control-browser-fixture.json",
    "utf8",
  ),
);
const origin =
  process.env.CONTROL_CENTER_BROWSER_ORIGIN || "http://127.0.0.1:5269";
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin))
  throw Error("Only local fixture origin permitted");
function otp() {
  const step = Buffer.alloc(8);
  step.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const raw = crypto
      .createHmac("sha1", Buffer.from("12345678901234567890"))
      .update(step)
      .digest(),
    off = raw.at(-1) & 15;
  return String((raw.readUInt32BE(off) & 0x7fffffff) % 1000000).padStart(
    6,
    "0",
  );
}
const engines =
  process.env.CONTROL_CENTER_BROWSER_ENGINE === "chromium"
    ? { chromium }
    : process.env.CONTROL_CENTER_BROWSER_ENGINE === "webkit"
      ? { webkit }
      : { chromium, webkit };
const report = [];
let index = 0;
for (const [engine, driver] of Object.entries(engines)) {
  const browser = await driver.launch(
    engine === "chromium" && process.env.WAREHOUSE_CHROMIUM_PATH
      ? {
          executablePath: process.env.WAREHOUSE_CHROMIUM_PATH,
          args: ["--no-sandbox"],
        }
      : {},
  );
  try {
    for (const width of [320, 390, 430, 1440])
      for (const theme of ["light", "forest", "gold", "onyx"]) {
        const context = await browser.newContext({
            baseURL: origin,
            viewport: { width, height: 960 },
            reducedMotion: "reduce",
          }),
          page = await context.newPage();
        const errors = [];
        page.on("pageerror", (e) => errors.push(e.message));
        await page.addInitScript((theme) => {
          localStorage.setItem(
            "warehouse.theme",
            theme === "light" ? "light" : "dark",
          );
          localStorage.setItem(
            "warehouse.nightStyle",
            theme === "light" ? "forest" : theme,
          );
        }, theme);
        await page.goto("/control/");
        await page.getByLabel("Логін").fill("browser-" + index++);
        await page.getByLabel("Пароль", { exact: true }).fill(fixture.password);
        await page.getByLabel("MFA-код").fill(otp());
        await page.getByRole("button", { name: "Увійти", exact: true }).click();
        await page.getByRole("heading", { name: "Огляд Warehouse" }).waitFor();
        if (width === 1440 && theme === "forest") {
          await page.getByText("Стан підписок").waitFor();
          await page.screenshot({ path: "/tmp/control-center-overview.png", fullPage: true });
        }
        assert.equal(
          await page.evaluate(() => document.documentElement.dataset.theme),
          theme === "light" ? "light" : "dark",
        );
        if (theme !== "light")
          assert.equal(
            await page.evaluate(
              () => document.documentElement.dataset.nightStyle,
            ),
            theme,
          );
        if (width === 320 && theme === "light") {
          // Deliberate UI fault injection; actual source role/failure behavior has
          // separate PostgreSQL/API coverage. No production endpoints involved.
          await page.route("**/api/control/overview", async (route) => {
            const response = await route.fetch();
            const value = await response.json();
            value.source.state = "stale";
            await route.fulfill({ response, json: value });
          });
          await page
            .getByRole("button", { name: "Оновити", exact: true })
            .click();
          await page
            .getByRole("status")
            .filter({ hasText: "Дані застаріли" })
            .waitFor();
          await page.unroute("**/api/control/overview");
          await page.route("**/api/control/companies?*", (route) =>
            route.fulfill({
              status: 503,
              json: { detail: "Тестова недоступність джерела" },
            }),
          );
          await page
            .getByRole("button", { name: "Оновити", exact: true })
            .click();
          await page
            .getByRole("alert")
            .filter({ hasText: "Тестова недоступність джерела" })
            .waitFor();
          await page.unroute("**/api/control/companies?*");
          let release;
          const gate = new Promise((resolve) => {
            release = resolve;
          });
          await page.route("**/api/control/companies?*", async (route) => {
            await gate;
            await route.continue();
          });
          const recovered = page.waitForResponse((res) =>
            new URL(res.url()).pathname === "/api/control/companies" && res.status() === 200);
          await page
            .getByRole("button", { name: "Оновити", exact: true })
            .click();
          await page
            .getByRole("status")
            .filter({ hasText: "Завантаження даних" })
            .waitFor();
          release();
          await recovered;
          await page
            .getByRole("status")
            .filter({ hasText: "Завантаження даних" })
            .waitFor({ state: "hidden" });
          await page.unroute("**/api/control/companies?*");
        }
        await page
          .getByRole("button", { name: "Клієнти", exact: true })
          .click();
        const launch = page.getByRole("button", {
          name: /Тестова компанія Альфа/,
        });
        await launch.waitFor();
        if (width === 320 && theme === "light") {
          await page
            .getByLabel("Пошук", { exact: true })
            .fill("no-such-company");
          await page
            .getByRole("button", { name: "Застосувати", exact: true })
            .click();
          await page
            .getByText(
              "Компаній за цими умовами немає.",
            )
            .waitFor();
          await page.getByLabel("Пошук", { exact: true }).fill("");
          await page
            .getByRole("button", { name: "Застосувати", exact: true })
            .click();
          await launch.waitFor();
        }
        if (width === 1440 && theme === "forest")
          await page.screenshot({ path: "/tmp/control-center-clients.png", fullPage: true });
        await launch.focus();
        await page.keyboard.press("Enter");
        const modal = page.getByRole("dialog");
        await modal.waitFor();
        await modal.getByText("o***@example.test", { exact: true }).waitFor();
        if (width === 1440 && theme === "forest")
          await page.screenshot({ path: "/tmp/control-center-company.png" });
        if (width === 390 && theme === "light")
          await page.screenshot({ path: "/tmp/control-center-company-mobile.png" });
        assert.equal(
          await modal.evaluate(
            (element) => getComputedStyle(element).animationName,
          ),
          "none",
          "reduced motion",
        );
        assert.equal(
          await modal.getByText("o***@example.test", { exact: true }).count(),
          1,
        );
        await modal
          .getByLabel("Нова нотатка")
          .fill(
            "Внутрішня browser-нотатка " + engine + " " + width + " " + theme,
          );
        await modal.getByRole("button", { name: "Зберегти нотатку" }).click();
        await modal
          .getByRole("status")
          .filter({ hasText: "Збережено лише" })
          .waitFor();
        await modal
          .getByRole("button", { name: "Оновити фінансовий контекст" })
          .click();
        await modal.getByText(/Немає перевіреного зв’язку з Billing/).waitFor();
        await modal
          .getByLabel("Дія", { exact: true })
          .fill("Тестова наступна дія");
        await modal
          .getByRole("button", { name: "Додати до моєї черги" })
          .click();
        await page.keyboard.press("Escape");
        await modal.waitFor({ state: "hidden" });
        assert.equal(
          await launch.evaluate((e) => e === document.activeElement),
          true,
          "focus restored",
        );
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          true,
          "no page horizontal overflow",
        );
        await page
          .getByRole("button", { name: "Робоча черга", exact: true })
          .click();
        await page
          .getByText("Тестова наступна дія", { exact: true })
          .first()
          .waitFor();
        if (width === 1440 && theme === "forest")
          await page.screenshot({
            path: "/tmp/control-center-desktop.png",
            fullPage: true,
          });
        if (width === 390 && theme === "light")
          await page.screenshot({
            path: "/tmp/control-center-mobile.png",
            fullPage: true,
          });
        assert.deepEqual(errors, []);
        report.push({ engine, width, theme, status: "passed" });
        await context.close();
      }
  } finally {
    await browser.close();
  }
}
const output =
  process.env.CONTROL_CENTER_BROWSER_REPORT ||
  "/tmp/control-center-browser-results.json";
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log(
  JSON.stringify({
    passed: report.length,
    failed: 0,
    engines: Object.keys(engines),
  }),
);
