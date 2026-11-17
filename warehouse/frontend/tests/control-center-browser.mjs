// Actual staff-only React build + real local API + disposable PostgreSQL. No live data.
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
  throw Error("Only loopback fixture origin permitted");
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
const drivers =
  process.env.CONTROL_CENTER_BROWSER_ENGINE === "chromium"
    ? { chromium }
    : process.env.CONTROL_CENTER_BROWSER_ENGINE === "webkit"
      ? { webkit }
      : { chromium, webkit };
const report = [];
let index = 0;
async function nav(page, hash, heading) {
  await page.evaluate((h) => (location.hash = h), hash);
  if (heading)
    await page.getByRole("heading", { name: heading, exact: true }).waitFor();
}
async function noOverflow(page) {
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 1,
    ),
    false,
    "no document horizontal overflow",
  );
}
for (const [engine, driver] of Object.entries(drivers)) {
  const browser = await driver.launch(
    engine === "chromium" && process.env.WAREHOUSE_CHROMIUM_PATH
      ? {
          executablePath: process.env.WAREHOUSE_CHROMIUM_PATH,
          args: ["--no-sandbox"],
        }
      : {},
  );
  try {
    for (const width of [320, 390, 768, 1440])
      for (const theme of ["light", "forest", "gold", "onyx"]) {
        console.log(JSON.stringify({ checking: { engine, width, theme } }));
        const context = await browser.newContext({
            baseURL: origin,
            viewport: { width, height: 960 },
            reducedMotion: "reduce",
          }),
          page = await context.newPage(),
          errors = [];
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
        await page
          .getByLabel("Логін", { exact: true })
          .fill("browser-" + index++);
        await page.getByLabel("Пароль", { exact: true }).fill(fixture.password);
        await page.getByLabel("MFA-код", { exact: true }).fill(otp());
        await page.getByRole("button", { name: "Увійти", exact: true }).click();
        await page
          .getByRole("heading", { name: "Огляд клієнтів", exact: true })
          .waitFor();
        await page.getByText("25", { exact: true }).first().waitFor();
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
        await noOverflow(page);
        if (width === 320 && theme === "light") {
          const second = await context.newPage();
          await second.goto("/control/");
          await second
            .getByRole("heading", { name: "Огляд клієнтів", exact: true })
            .waitFor();
          assert.equal(
            await second.evaluate(() => sessionStorage.getItem("control.csrf")),
            null,
          );
          await nav(
            second,
            "#/company/" + fixture.companies[0].id + "/notes",
            "Тестова компанія Альфа",
          );
          await second
            .getByLabel("Нова нотатка", { exact: true })
            .fill("Перевірка CSRF нової вкладки " + engine);
          const saved = second.waitForResponse(
            (r) =>
              r.request().method() === "POST" &&
              r.url().endsWith("/notes") &&
              r.status() === 201,
          );
          await second
            .getByRole("button", { name: "Зберегти нотатку", exact: true })
            .click();
          await saved;
          await second.close();
          await page.evaluate(() =>
            sessionStorage.setItem("control.csrf", "stale-proof"),
          );
          await page.route("**/api/control/overview", async (route) => {
            const response = await route.fetch(),
              value = await response.json();
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
          await page
            .getByRole("button", { name: "Оновити", exact: true })
            .click();
          await page
            .locator(".cc-two-col > section")
            .first()
            .getByRole("status")
            .filter({ hasText: "Завантажуємо дані" })
            .waitFor();
          release();
          await page
            .locator(".cc-two-col > section")
            .first()
            .getByRole("status")
            .filter({ hasText: "Завантажуємо дані" })
            .waitFor({ state: "hidden" });
          await page.unroute("**/api/control/companies?*");
        }
        await nav(page, "#/clients", "Клієнти");
        await page
          .getByRole("link", { name: "Тестова компанія Альфа", exact: true })
          .waitFor();
        if (width === 320 && theme === "light") {
          await page
            .getByLabel("Пошук клієнта", { exact: true })
            .fill("no-such-company");
          await page
            .getByRole("button", { name: "Застосувати", exact: true })
            .click();
          await page
            .getByRole("heading", {
              name: "Клієнтів за цими умовами немає",
              exact: true,
            })
            .waitFor();
          await page
            .getByRole("link", { name: "Скинути", exact: true })
            .click();
          await page
            .getByRole("link", { name: "Тестова компанія Альфа", exact: true })
            .waitFor();
          await page
            .getByRole("link", { name: "Наступні →", exact: true })
            .click();
          await page.getByText("Кінець вибірки", { exact: true }).waitFor();
          assert(new URL(page.url()).hash.includes("cursor="));
          assert.equal(
            await page.locator(".cc-client-cards .cc-client-card").count(),
            5,
          );
          await page.reload();
          await page.getByText("Кінець вибірки", { exact: true }).waitFor();
          await page
            .getByRole("link", { name: "На початок", exact: true })
            .click();
          await page
            .getByRole("link", { name: "Тестова компанія Альфа", exact: true })
            .waitFor();
        }
        if (width <= 1100) {
          await page
            .getByRole("button", { name: "Відкрити меню", exact: true })
            .click();
          const sidebar = page.getByRole("dialog", {
            name: "Головне меню",
            exact: true,
          });
          await sidebar.waitFor();
          assert(
            await page.locator(".cc-layout-main").evaluate((e) => e.inert),
          );
          const first = sidebar.getByRole("button", {
            name: "Закрити меню",
            exact: true,
          });
          await first.focus();
          await page.keyboard.press("Shift+Tab");
          assert.equal(
            await sidebar
              .getByRole("button", { name: "Вийти", exact: true })
              .evaluate((e) => e === document.activeElement),
            true,
          );
          await page.keyboard.press("Escape");
          await page.waitForFunction(
            () =>
              document.querySelector(".cc-menu-button") ===
                document.activeElement &&
              document.querySelector(".cc-sidebar").inert,
          );
        }
        const launch = page.getByRole("link", {
          name: "Тестова компанія Альфа",
          exact: true,
        });
        await launch.focus();
        await page.keyboard.press("Enter");
        await page
          .getByRole("heading", { name: "Тестова компанія Альфа", exact: true })
          .waitFor();
        await page.getByText("34", { exact: false }).first().waitFor();
        assert.equal(
          await page.getByText("Оплачено", { exact: true }).count(),
          0,
        );
        await noOverflow(page);
        if (width === 1440 && theme === "forest")
          await page.screenshot({
            path: "/tmp/control-center-company.png",
            fullPage: true,
          });
        if (width === 390 && theme === "light")
          await page.screenshot({
            path: "/tmp/control-center-company-mobile.png",
            fullPage: true,
          });
        for (const [section, label] of [
          ["products", "Продукти"],
          ["people", "Працівники"],
          ["activity", "Активність"],
          ["history", "Історія"],
        ]) {
          await page
            .locator(".cc-profile-tabs")
            .getByRole("link", { name: label, exact: true })
            .click();
          await page.waitForURL((u) => u.hash.endsWith("/" + section));
          await noOverflow(page);
        }
        await page
          .locator(".cc-profile-tabs")
          .getByRole("link", { name: "Фінанси", exact: true })
          .click();
        await page
          .getByRole("button", {
            name: "Оновити фінансовий контекст",
            exact: true,
          })
          .click();
        await page
          .getByText("Немає перевіреного зв’язку з Billing", { exact: true })
          .waitFor();
        await page
          .locator(".cc-profile-tabs")
          .getByRole("link", { name: "Нотатки", exact: true })
          .click();
        const note =
          "Внутрішня нотатка " +
          engine +
          " " +
          width +
          " " +
          theme +
          " <img src=x onerror=alert(1)>";
        await page.getByLabel("Нова нотатка", { exact: true }).fill(note);
        assert.equal(
          await page.getByLabel("Нова нотатка", { exact: true }).inputValue(),
          note,
          "route focus must not interrupt immediate typing",
        );
        const noteSaved = page.waitForResponse(
          (r) =>
            r.request().method() === "POST" &&
            r.url().endsWith("/notes") &&
            r.status() !== 403,
        );
        await page
          .getByRole("button", { name: "Зберегти нотатку", exact: true })
          .click();
        const noteResponse = await noteSaved;
        assert.equal(noteResponse.status(), 201, await noteResponse.text());
        await page.getByText(note, { exact: true }).waitFor();
        assert.equal(await page.locator(".cc-note img").count(), 0);
        const taskAction =
          "Тестова наступна дія " + engine + " " + width + " " + theme;
        const taskButton = page.getByRole("button", {
          name: "Завдання",
          exact: true,
        });
        await taskButton.click();
        const dialog = page.getByRole("dialog", {
          name: "Нове завдання",
          exact: true,
        });
        await dialog
          .getByLabel("Наступна дія", { exact: true })
          .fill(taskAction);
        await dialog
          .getByRole("button", { name: "Додати до моєї черги", exact: true })
          .click();
        await dialog.waitFor({ state: "hidden" });
        await page
          .getByText("Завдання збережено", { exact: false })
          .first()
          .waitFor();
        assert.equal(
          await taskButton.evaluate((e) => e === document.activeElement),
          true,
          "task dialog restores focus",
        );
        await nav(page, "#/queue", "Робоча черга");
        const task = page
          .locator(
            width <= 850
              ? ".cc-task-cards .cc-client-card"
              : ".cc-task-table tr",
          )
          .filter({ hasText: taskAction });
        await task.waitFor();
        const selector = task.getByLabel("Статус завдання: " + taskAction, {
          exact: true,
        });
        await selector.selectOption("in_progress");
        await page
          .getByRole("status")
          .filter({ hasText: "Статус завдання збережено" })
          .waitFor();
        await page.waitForFunction(
          (action) =>
            [...document.querySelectorAll("label.cc-task-status")]
              .filter((l) => l.textContent.includes(action))
              .some((l) => l.querySelector("select")?.value === "in_progress"),
          taskAction,
        );
        await selector.waitFor();
        assert.equal(await selector.inputValue(), "in_progress");
        await noOverflow(page);
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
        if (width === 320 && theme === "light") {
          await page.evaluate(() => sessionStorage.removeItem("control.csrf"));
          await page
            .getByRole("button", { name: "Відкрити меню", exact: true })
            .click();
          await page
            .getByRole("button", { name: "Вийти", exact: true })
            .click();
          await page.getByLabel("Логін", { exact: true }).waitFor();
          assert.equal(
            (await context.request.get("/api/control/auth/me")).status(),
            401,
          );
        }
        if (width === 320 && theme === "forest") {
          await page.route("**/api/control/overview", (route) =>
            route.fulfill({ status: 401, json: { detail: "Session revoked" } }),
          );
          await page
            .getByRole("button", { name: "Оновити", exact: true })
            .click();
          await page.getByLabel("Логін", { exact: true }).waitFor();
          assert.equal(await page.locator(".cc-shell").count(), 0);
          assert.equal(
            await page.evaluate(() => sessionStorage.getItem("control.csrf")),
            null,
          );
        }
        assert.deepEqual(errors, []);
        report.push({ engine, width, theme, status: "passed" });
        await context.close();
      }
  } finally {
    await browser.close();
  }
}
fs.writeFileSync(
  process.env.CONTROL_CENTER_BROWSER_REPORT ||
    "/tmp/control-center-browser-results.json",
  JSON.stringify(report, null, 2),
);
console.log(
  JSON.stringify({
    passed: report.length,
    failed: 0,
    engines: Object.keys(drivers),
  }),
);
