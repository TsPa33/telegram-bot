import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const read=(file)=>readFile(new URL(file,import.meta.url),'utf8');
const charts=await read('../src/StatisticsCharts.tsx');
const css=await read('../src/statistics.css');
const page=await read('../src/pages/Dashboard.tsx');

test('no nested vertical scrollbars remain in statistics chart lists',()=>{
 assert.match(css,/\.chart-bars\{[^}]*overflow:visible/);
 assert.doesNotMatch(css,/\.chart-bars\{[^}]*overflow:auto/);
 assert.match(charts,/rows\.slice\(0,initial\)/);
 assert.match(charts,/aria-expanded=\{expanded\}/);
});
test('finance is shown only under dedicated analytics financial permission',()=>{
 assert.match(charts,/<Permit permission="analytics.financial">/);
 assert.match(page,/finance=can\('analytics.financial'\)/);
 assert.match(page,/<Permit permission="analytics.financial">/);
});
test('zero valuation is shown as unpriced only when price coverage is zero',()=>{
 assert.match(charts,/positive\(r\.priced_positions\)>0/);
 assert.match(charts,/Без оцінки/);
 assert.match(charts,/unpriced_positions/);
});
test('sales periods are not misrepresented as stock snapshot filters',()=>{
 assert.match(page,/showSales&&<SalesTrend\/>/);
 assert.doesNotMatch(page,/onClick.*setPeriod/);
});
test('stock dashboard uses API data and no static example numbers',()=>{
 assert.match(page,/api\('\/dashboard'\)/);
 assert.match(page,/count\(d\.positions\)/);
 assert.match(page,/count\(d\.available_units\)/);
});
