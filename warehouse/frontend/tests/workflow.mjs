import { expect } from "@playwright/test";
export async function workflow(page, viewport) {
  await page.setViewportSize(viewport);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  async function nav(label) {
    if (viewport.width < 800)
      await page
        .getByRole("button", { name: "Відкрити меню", exact: true })
        .click();
    await page
      .getByRole("navigation")
      .getByRole("link", { name: label, exact: true })
      .click();
  }
  await page.goto("/");
  await page
    .getByRole("button", { name: "Зареєструватися", exact: true })
    .click();
  await page.getByLabel("Ваше ім’я").fill("E2E test owner");
  await page
    .getByLabel("Електронна пошта")
    .fill(`e2e-${viewport.name}-${Date.now()}@example.test`);
  await page.getByLabel("Пароль").fill("e2e-only-long-password");
  await page
    .getByRole("button", { name: "Створити обліковий запис", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Огляд складу", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Історія почнеться з першої дії")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/${viewport.name}-dashboard.png`,
    fullPage: true,
  });
  await nav("Донорські авто");
  await page
    .getByRole("button", { name: "Додати автомобіль", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Виробник").fill("E2E manufacturer");
  await dialog.getByLabel("Модель", { exact: false }).fill("E2E model");
  await dialog.getByLabel("Рік").fill("2020");
  await dialog.getByLabel("Внутрішній ID донора").fill("E2E-DONOR");
  await dialog.getByLabel("Дата придбання").fill("2026-01-01");
  await dialog.getByRole("button", { name: "Зберегти", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "E2E manufacturer E2E model",
      exact: true,
    }),
  ).toBeVisible();
  await nav("Каталог запчастин");
  await page
    .getByRole("button", { name: "Імпорт категорій", exact: true })
    .click();
  await page.getByLabel("JSON-файл категорій").setInputFiles({
    name: "e2e-only-catalog.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        source: "e2e-only",
        nodes: [
          { key: "group", name: "E2E group", kind: "category" },
          {
            key: "part",
            parent_key: "group",
            name: "E2E checklist part",
            kind: "part",
          },
        ],
      }),
    ),
  });
  await page.getByRole("button", { name: "Перевірити файл" }).click();
  await expect(
    page.getByText("Перевірено: 2. Нових: 2. Існує: 0."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Підтвердити імпорт" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await nav("Донорські авто");
  await page
    .getByRole("button", { name: "E2E manufacturer E2E model", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Сформувати список запчастин" })
    .click();
  await expect(page.locator(".toast")).toContainText("Додано позицій: 1");
  await page.getByRole("button", { name: "Закрити", exact: true }).click();
  await nav("Складські залишки");
  await page
    .getByRole("button", { name: "E2E checklist part", exact: true })
    .click();
  await page.getByLabel("Кількість").fill("3");
  await page.getByLabel("Причина операції").fill("E2E test receipt");
  await page.getByRole("button", { name: "Провести операцію" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await nav("Операції зі складом");
  const value = await page
    .getByLabel("Запчастина для операції")
    .locator("option")
    .nth(1)
    .getAttribute("value");
  await page.getByLabel("Запчастина для операції").selectOption(value);
  await page.getByLabel("Тип операції").selectOption("reserve");
  await page.getByLabel("Кількість").fill("1");
  await page.getByLabel("Причина операції").fill("E2E test reservation");
  await page.getByRole("button", { name: "Провести операцію" }).click();
  await expect(page.locator(".toast")).toContainText("Операцію проведено");
  await nav("Аналітика та аудит");
  await page
    .getByLabel("Тип операції", { exact: true })
    .selectOption("reserve");
  await expect(
    page.getByText("E2E test reservation", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `test-results/${viewport.name}-audit.png`,
    fullPage: true,
  });
  await nav("Архів");
  await expect(
    page.getByRole("heading", { name: "Архів порожній" }),
  ).toBeVisible();
  await nav("Налаштування");
  await expect(
    page.getByRole("heading", { name: "Обліковий запис", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Вийти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "З поверненням" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
}
