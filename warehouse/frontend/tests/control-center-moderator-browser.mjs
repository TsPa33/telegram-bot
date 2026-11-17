// Real owner provisioning and Moderator UI on disposable loopback API only.
import { chromium, webkit } from "@playwright/test";
import fs from "node:fs";
import assert from "node:assert/strict";
if (process.env.CONTROL_CENTER_BROWSER_TEST !== "1")
  throw Error("Explicit loopback fixture required");
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
const report = [];
let index = 20;
for (const [engine, driver] of Object.entries({ chromium, webkit })) {
  const browser = await driver.launch();
  try {
    for (const width of [320, 1440]) {
      const context = await browser.newContext({
          baseURL: origin,
          viewport: { width, height: 960 },
        }),
        page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const login = async (p, username, password) => {
        await p.goto("/control/");
        await p.getByLabel("Логін", { exact: true }).fill(username);
        await p.getByLabel("Пароль", { exact: true }).fill(password);
        await p.getByRole("button", { name: "Увійти", exact: true }).click();
      };
      await login(page, "browser-" + index, fixture.password);
      await page
        .getByRole("heading", { name: "Огляд клієнтів", exact: true })
        .waitFor();
      await page.evaluate(() => (location.hash = "#/security"));
      await page
        .getByRole("heading", { name: "Команда CRM", exact: true })
        .waitFor();
      const username = "moderator-" + engine + "-" + width + "-" + Date.now();
      const create = page.getByRole("form", { name: "Створити співробітника" });
      await create.getByLabel("Логін співробітника").fill(username);
      await create
        .getByLabel("Причина", { exact: true })
        .fill("Approved browser fixture");
      await create.getByLabel("Ваш поточний пароль").fill(fixture.password);
      await create
        .getByRole("button", { name: "Створити обліковий запис", exact: true })
        .click();
      const receipt = page.locator(".cc-activation-receipt");
      await receipt.waitFor();
      const temporary = await receipt.locator("code").innerText();
      assert(temporary.length >= 24);
      await receipt.getByRole("button", { name: "Приховати пароль" }).click();
      assert.equal(await receipt.count(), 0);
      const memberContext = await browser.newContext({
          baseURL: origin,
          viewport: { width, height: 960 },
        }),
        member = await memberContext.newPage();
      member.on("pageerror", (e) => errors.push(e.message));
      const requests = [];
      member.on("request", (r) => requests.push(new URL(r.url()).pathname));
      await login(member, username, temporary);
      await member
        .getByRole("heading", {
          name: "Активуйте особистий доступ",
          exact: true,
        })
        .waitFor();
      assert(!requests.includes("/api/control/companies"));
      await member
        .getByLabel("Поточний пароль", { exact: true })
        .fill(temporary);
      const personal = temporary + "-personal";
      await member
        .getByLabel("Новий пароль (від 12 символів)", { exact: true })
        .fill(personal);
      await member
        .getByRole("button", { name: "Змінити пароль", exact: true })
        .click();
      await member.getByLabel("Логін", { exact: true }).waitFor();
      await login(member, username, personal);
      await member
        .getByRole("heading", { name: "Огляд клієнтів", exact: true })
        .waitFor();
      await member.evaluate(() => (location.hash = "#/clients"));
      for (const name of ["Тестова компанія Альфа", "Тестова компанія Бета"])
        await member.getByRole("link", { name, exact: true }).waitFor();
      await member.evaluate(
        (id) => (location.hash = `#/company/${id}/notes`),
        fixture.companies[0].id,
      );
      await member
        .getByRole("heading", { name: "Тестова компанія Альфа", exact: true })
        .waitFor();
      await member
        .locator(".cc-profile-head")
        .getByText("owner@example.test", { exact: false })
        .waitFor();
      await member
        .getByLabel("Нова нотатка", { exact: true })
        .fill("Moderator private note " + username);
      await member
        .getByRole("button", { name: "Зберегти нотатку", exact: true })
        .click();
      await member
        .locator(".cc-note p")
        .filter({ hasText: "Moderator private note " + username })
        .waitFor();
      await member
        .getByText("Редагувати нотатку", { exact: true })
        .first()
        .click();
      await member
        .getByLabel("Текст нотатки")
        .first()
        .fill("Updated moderator note " + username);
      await member
        .getByRole("button", { name: "Зберегти зміни нотатки" })
        .first()
        .click();
      await member
        .locator(".cc-note p")
        .filter({ hasText: "Updated moderator note " + username })
        .waitFor();
      await member
        .getByRole("button", { name: "Завдання", exact: true })
        .click();
      await member
        .getByLabel("Наступна дія", { exact: true })
        .fill("Moderator follow-up " + username);
      await member
        .getByRole("button", { name: "Додати до моєї черги", exact: true })
        .click();
      await member.getByRole("dialog").waitFor({ state: "hidden" });
      await member.evaluate(() => (location.hash = "#/queue"));
      await member
        .getByText("Moderator follow-up " + username, { exact: true })
        .filter({ visible: true })
        .waitFor();
      await member.evaluate(
        (id) => (location.hash = `#/company/${id}/finance`),
        fixture.companies[0].id,
      );
      await member
        .getByRole("heading", {
          name: "Фінансовий контекст недоступний вашій ролі",
          exact: true,
        })
        .waitFor();
      await member.evaluate(() => (location.hash = "#/security"));
      await member
        .getByRole("button", { name: "Змінити пароль", exact: true })
        .waitFor();
      assert.equal(
        await member
          .getByRole("heading", { name: "Команда CRM", exact: true })
          .count(),
        0,
      );
      assert(!requests.includes("/api/control/staff"));
      assert(!requests.some((p) => p.endsWith("/finance")));
      await page
        .getByRole("button", { name: "Керувати " + username, exact: true })
        .click();
      let manage = page.getByRole("form", { name: "Керування співробітником" });
      await manage.getByLabel("Активний доступ").uncheck();
      await manage
        .getByLabel("Причина", { exact: true })
        .fill("Disable fixture");
      await manage.getByLabel("Ваш поточний пароль").fill(fixture.password);
      await manage
        .getByRole("button", { name: "Зберегти доступ", exact: true })
        .click();
      await manage.waitFor({ state: "hidden" });
      await member.reload();
      await member.getByLabel("Логін", { exact: true }).waitFor();
      await page
        .getByRole("button", { name: "Керувати " + username, exact: true })
        .click();
      manage = page.getByRole("form", { name: "Керування співробітником" });
      await manage.getByLabel("Активний доступ").check();
      await manage
        .getByLabel("Причина", { exact: true })
        .fill("Reactivate fixture");
      await manage.getByLabel("Ваш поточний пароль").fill(fixture.password);
      await manage
        .getByRole("button", { name: "Зберегти доступ", exact: true })
        .click();
      await manage.waitFor({ state: "hidden" });
      await page
        .getByRole("button", { name: "Керувати " + username, exact: true })
        .click();
      manage = page.getByRole("form", { name: "Керування співробітником" });
      await manage.getByLabel("Причина", { exact: true }).fill("Reset fixture");
      await manage.getByLabel("Ваш поточний пароль").fill(fixture.password);
      await manage
        .getByRole("button", { name: "Скинути доступ", exact: true })
        .click();
      await receipt.waitFor();
      assert.notEqual(await receipt.locator("code").innerText(), temporary);
      await receipt.getByRole("button", { name: "Приховати пароль" }).click();
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      );
      assert.deepEqual(errors, []);
      report.push({
        engine,
        width,
        ownerProvisioning: true,
        forcedRotation: true,
        allClients: true,
        contacts: true,
        notes: true,
        queue: true,
        financeHidden: true,
        deactivation: true,
        reactivation: true,
        reset: true,
      });
      await memberContext.close();
      await context.close();
      index++;
    }
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify({ passed: report.length, report }));
