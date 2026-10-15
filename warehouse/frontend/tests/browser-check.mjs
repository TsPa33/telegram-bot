// Direct browser runner for environments where Playwright's test loader is unavailable.
// Uses the same dedicated test database precondition as the Playwright suite.
import { chromium } from "playwright";
import { workflow } from "./workflow.mjs";
import fs from "node:fs/promises";
if (process.env.WAREHOUSE_E2E !== "1")
  throw new Error(
    "Use a dedicated warehouse*_test database and set WAREHOUSE_E2E=1",
  );
const browser = await chromium.launch({
  executablePath: process.env.WAREHOUSE_CHROMIUM_PATH || undefined,
  headless: true,
  args: ["--no-sandbox"],
});
try {
  await fs.mkdir("test-results", { recursive: true });
  for (const viewport of [
    { name: "desktop", width: 1440, height: 1000 },
    { name: "iphone", width: 390, height: 844 },
  ]) {
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:5173",
    });
    const page = await context.newPage();
    await workflow(page, viewport);
    console.log(`PASS: standalone inventory workflow · ${viewport.name}`);
    await context.close();
  }
} finally {
  await browser.close();
}
