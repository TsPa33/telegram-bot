// Browser permission boundaries against the actual staff API, never mocked grants.
import { chromium, webkit } from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
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
for (const [engine, driver] of Object.entries({ chromium, webkit })) {
  const b = await driver.launch();
  try {
    for (const role of ["support", "manager", "admin"]) {
      const context = await b.newContext({
          baseURL: origin,
          viewport: { width: 390, height: 900 },
        }),
        p = await context.newPage(),
        requests = [];
      p.on("request", (r) => requests.push(new URL(r.url()).pathname));
      await p.goto("/control/");
      await p
        .getByLabel("Логін", { exact: true })
        .fill("browser-" + role + (engine === "webkit" ? "-webkit" : ""));
      await p.getByLabel("Пароль", { exact: true }).fill(fixture.password);
      await p.getByLabel("MFA-код", { exact: true }).fill(otp());
      await p.getByRole("button", { name: "Увійти", exact: true }).click();
      await p
        .getByRole("heading", { name: "Огляд клієнтів", exact: true })
        .waitFor();
      await p.evaluate(() => (location.hash = "#/clients"));
      await p
        .getByRole("link", { name: "Тестова компанія Альфа", exact: true })
        .waitFor();
      if (role !== "admin") {
        assert.equal(
          await p
            .getByRole("link", { name: "Тестова компанія Бета", exact: true })
            .count(),
          0,
        );
        assert(
          !requests.includes("/api/control/staff"),
          "delegated roles must not request the global staff registry",
        );
      }
      await p
        .getByRole("link", { name: "Тестова компанія Альфа", exact: true })
        .click();
      await p
        .getByRole("heading", { name: "Тестова компанія Альфа", exact: true })
        .waitFor();
      assert.equal(
        await p
          .locator(".cc-profile-head")
          .getByText("owner@example.test", { exact: false })
          .count(),
        0,
      );
      assert.equal(
        await p
          .locator(".cc-profile-tabs")
          .getByRole("link", { name: "Фінанси", exact: true })
          .count(),
        0,
      );
      await p.evaluate(
        (id) => (location.hash = "#/company/" + id + "/finance"),
        fixture.companies[0].id,
      );
      await p
        .getByRole("heading", {
          name: "Фінансовий контекст недоступний вашій ролі",
          exact: true,
        })
        .waitFor();
      assert.equal(requests.filter((u) => u.endsWith("/finance")).length, 0);
      if (role !== "admin") {
        await p.evaluate(
          (id) => (location.hash = "#/company/" + id + "/overview"),
          fixture.companies[1].id,
        );
        await p.getByRole("alert").waitFor();
        assert.equal(
          await p
            .getByRole("heading", {
              name: "Тестова компанія Бета",
              exact: true,
            })
            .count(),
          0,
        );
      }
      result.push({
        engine,
        role,
        serverScope: true,
        financeNotRequested: true,
        maskedContacts: true,
      });
      await context.close();
    }
  } finally {
    await b.close();
  }
}
console.log(JSON.stringify({ passed: result.length, result }));
