// MFA enrollment remains mandatory before newly provisioned staff can read CRM.
import { chromium, webkit } from "@playwright/test";
import fs from "node:fs";
import crypto from "node:crypto";
import assert from "node:assert/strict";
if (process.env.CONTROL_CENTER_BROWSER_TEST !== "1")
  throw Error("Disposable fixture opt-in required");
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
function otp(seed, offset = 0) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of seed.replace(/=+$/, ""))
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((x) => parseInt(x, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offset));
  const hash = crypto.createHmac("sha1", key).update(counter).digest(),
    position = hash.at(-1) & 15;
  return String((hash.readUInt32BE(position) & 0x7fffffff) % 1000000).padStart(
    6,
    "0",
  );
}
const report = [];
let index = 34;
for (const [engine, driver] of Object.entries({ chromium, webkit })) {
  const browser = await driver.launch();
  try {
    for (const width of [320, 1440]) {
      const owner = await browser.newContext({ baseURL: origin });
      const response = await owner.request.post("/api/control/auth/login", {
        headers: { Origin: origin },
        data: {
          username: "browser-" + index++,
          password: fixture.password,
          code: otp(fixture.seed),
        },
      });
      assert.equal(response.status(), 200);
      const auth = await response.json();
      const username = "mfa-" + engine + "-" + width + "-" + Date.now();
      const created = await owner.request.post("/api/control/staff", {
        headers: { Origin: origin, "X-Control-CSRF": auth.csrf },
        data: {
          username,
          reason: "MFA browser fixture",
          mfa_code: otp(fixture.seed, 1),
        },
      });
      assert.equal(created.status(), 201);
      const account = await created.json();
      await owner.close();
      const context = await browser.newContext({
          baseURL: origin,
          viewport: { width, height: 960 },
        }),
        page = await context.newPage(),
        errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto("/control/");
      await page.getByLabel("Логін", { exact: true }).fill(username);
      await page
        .getByLabel("Пароль", { exact: true })
        .fill(account.temporary_password);
      await page.getByRole("button", { name: "Увійти", exact: true }).click();
      await page
        .getByRole("heading", {
          name: "Активуйте особистий доступ",
          exact: true,
        })
        .waitFor();
      const status = await page.evaluate(
        async () => (await fetch("/api/control/companies")).status,
      );
      assert.equal(status, 403);
      await page
        .getByRole("button", {
          name: "Підключити власний Authenticator",
          exact: true,
        })
        .click();
      const form = page.getByRole("form", {
        name: "Активація персонального доступу",
      });
      await form.waitFor();
      const seed = await form.locator("code").innerText();
      await form
        .getByLabel("Тимчасовий пароль", { exact: true })
        .fill(account.temporary_password);
      const password = account.temporary_password + "-personal";
      await form
        .getByLabel("Новий пароль (від 12 символів)", { exact: true })
        .fill(password);
      await form
        .getByLabel("Код із нового Authenticator", { exact: true })
        .fill(otp(seed));
      await form
        .getByRole("button", { name: "Активувати й увійти знову", exact: true })
        .click();
      await page.getByLabel("Логін", { exact: true }).waitFor();
      await page.getByLabel("Логін", { exact: true }).fill(username);
      await page.getByLabel("Пароль", { exact: true }).fill(password);
      await page.getByLabel("MFA-код", { exact: true }).fill(otp(seed, 1));
      await page.getByRole("button", { name: "Увійти", exact: true }).click();
      await page
        .getByRole("heading", { name: "Огляд клієнтів", exact: true })
        .waitFor();
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      );
      assert.deepEqual(errors, []);
      report.push({
        engine,
        width,
        restrictedSession: true,
        enrollment: true,
        personalPassword: true,
        mfaLogin: true,
      });
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify({ passed: report.length, report }));
