// Static design-contract checks for PR2, executed by the Railway frontend build.
// Runtime browser acceptance remains a separate requirement.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = name => readFileSync(new URL('../src/'+name, import.meta.url),'utf8');
const board=read('AssemblyTree.tsx');
const source=read('GlobalCatalogueFlow.tsx');
const generator=read('UniversalPlanGenerator.tsx');
const boardCss=read('assembly-tree.css');
const sourceCss=read('unified-dismantling.css');

test('source identity remains visible but does not occupy a large separate panel',()=>{
 assert.match(source,/uf-source-strip/);
 assert.match(source,/Точну каталожну модифікацію не вибрано/);
 assert.match(source,/GlobalVehicleForm/);
 assert.match(sourceCss,/\.uf-source-strip/);
});
test('the full source list and technical provenance are collapsed, not repeated above workbench',()=>{
 assert.match(generator,/catalogue_platform_admin===true/);
 assert.match(generator,/dv2-sources/);
 assert.doesNotMatch(generator,/ug-type-review/);
 assert.match(generator,/Оновити каталог/);
 assert.match(generator,/не підтверджена фізична наявність/);
});
test('approved workbench keeps three predictable columns and selection-side inspector',()=>{
 assert.match(board,/className="assembly-workspace has-inspector"/);
 assert.match(board,/assembly-inspector-empty/);
 assert.match(board,/<nav className="assembly-categories"/);
 assert.match(boardCss,/grid-template-columns:minmax\(175px,210px\) minmax\(0,1fr\) minmax\(250px,300px\)/);
 assert.match(boardCss,/@media\(max-width:650px\)/);
});
test('quantity buttons edit a local draft without an HTTP request per click',()=>{
 assert.match(board,/const \[quantityDraft,setQuantityDraft\]=useState/);
 const row=board.match(/<div className="assembly-counter"[\s\S]*?<\/div>/)?.[0];
 assert.ok(row,'counter markup missing');
 assert.match(row,/setQuantityDraft/);
 assert.match(row,/assembly-counter-save/);
 assert.doesNotMatch(row,/onClick=\{\(\)=>void inspect/);
 assert.match(board,/async function saveQuantity/);
});
test('an inspect refresh preserves selected card without calling select again',()=>{
 assert.match(board,/if\(action==='inspect'\)[\s\S]*?setSelected\(node\)/);
 assert.doesNotMatch(board,/if\(action==='inspect'\)[\s\S]{0,130}await select\(node\)/);
 assert.match(board,/selectedId\.current===node\.id/);
});
test('existing stock receipt, sale protections and confirm workflow remain wired',()=>{
 assert.match(board,/GuidedReceipt/);
 assert.match(board,/bulk\.start/);
 assert.match(board,/setCheckout\(/);
 assert.match(board,/send\('return'/);
 assert.match(board,/preview\.conflicts\.length/);
});
