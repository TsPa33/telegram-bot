import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
const source = fs.readFileSync(
  new URL("../src/vehiclePartsWorkspace.ts", import.meta.url),
  "utf8",
);
const {
  workspaceSections,
  sectionOf,
  filterWorkspace,
  changeWorkspaceSelection,
  priceQuote,
} = await import(
  "data:text/javascript;base64," +
    Buffer.from(
      ts.transpileModule(source, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ESNext,
        },
      }).outputText,
    ).toString("base64")
);
const a = {
    pt_id: 1,
    name: "Starter",
    name_uk: "Стартер",
    classification: { section: workspaceSections[0] },
  },
  b = {
    pt_id: 2,
    name: "Brake",
    classification: { section: workspaceSections[4] },
  },
  unknown = { pt_id: 3, name: "Unknown", classification: { section: null } };
const parts = new Map([
    [
      1,
      { article_number: "ART-1", article_brand: "Brand", oem_number: "OEM-1" },
    ],
  ]),
  receipts = new Map([
    [1, { stored: true }],
    [2, { status: "uncertain", received_at: null }],
  ]);
const filter = (options) =>
  filterWorkspace([a, b, unknown], options, parts, receipts, {});
test("backend classification only; ambiguous stays review", () =>
  assert.equal(sectionOf(unknown), "Потребують уточнення"));
test("category filters main list without supplier lookups", () =>
  assert.deepEqual(filter({ section: workspaceSections[0] }), [a]));
test("selection persists across category/page changes and deduplicates", () => {
  let ids = changeWorkspaceSelection(
    [],
    Array.from({ length: 180 }, (_, i) => i),
    true,
  );
  ids = changeWorkspaceSelection(ids, [179, 180], true);
  assert.equal(ids.length, 181);
  assert.deepEqual(changeWorkspaceSelection(ids, [180], false).length, 180);
});
for (const q of ["Стартер", "ART-1", "Brand", "OEM-1"])
  test("search " + q, () => assert.deepEqual(filter({ q }), [a]));
test("combined filters use actual saved snapshots and stock", () => {
  assert.deepEqual(filter({ stock: "stored", data: "saved", oem: "yes" }), [a]);
  assert.deepEqual(filter({ data: "uncertain" }), [b]);
});
test("all source variants can be searched after free recovery", () =>
  assert.deepEqual(
    filterWorkspace([b], { q: "SECOND" }, parts, receipts, {
      2: [{ article_nr: "SECOND" }],
    }),
    [b],
  ));
test("cost must be confirmed integer; no invented default", () => {
  assert.deepEqual(priceQuote(2, 20), { known: true, max: 40 });
  for (const v of [undefined, null, "2", -1, 1.2, Infinity])
    assert.equal(priceQuote(v, 1).known, false);
});
