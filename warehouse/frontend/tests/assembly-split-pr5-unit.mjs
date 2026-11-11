import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source=file=>readFileSync(new URL('../src/'+file,import.meta.url),'utf8');
const ui=source('AssemblyTree.tsx'),css=source('assembly-tree.css');

test('one physical unit is required; references alone cannot create receipts',()=>{
 assert.match(ui,/selected\.part_id&&Number\(selected\.quantity\)===1/);
 assert.match(ui,/assemblyUnitFor\(selected\)/);
 assert.match(ui,/Вузол залишиться неповним/);
 assert.match(ui,/Відокремити та оприбуткувати/);
 assert.match(ui,/!splitConfirmed/);
 assert.match(ui,/!splitSelected\.length/);
});
test('physical split is a single atomic replay-protected backend command',()=>{
 assert.match(ui,/\/assemblies\/split/);
 assert.match(ui,/request_key:splitPending\.current\.key/);
 assert.match(ui,/confirm_physical:true/);
 assert.match(ui,/root_item_id:root\.id/);
 assert.match(ui,/unit_id:unit\.id/);
 assert.match(ui,/components,confirm_physical:true/);
 assert.match(ui,/const fingerprint=JSON\.stringify\(\[scope,'assembly:split'/);
 assert.match(ui,/if\(splitPending\.current\?\.fingerprint!==fingerprint\)/);
});
test('condition and selection are explicit physical confirmations',()=>{
 assert.match(ui,/splitSelected\.slice\(\)\.sort/);
 for(const c of ['used','damaged','new','refurbished'])assert.match(ui,new RegExp('value="'+c+'"'));
 assert.match(ui,/Підтверджую демонтаж/);
 assert.match(ui,/setSplitConfirmed\(false\)/);
});
test('stock and planned reference rows remain separated',()=>{
 assert.match(ui,/separated=planned\.filter\(n=>!!n\.part_id\)/);
 assert.match(ui,/waiting=planned\.filter\(n=>!n\.part_id\)/);
 assert.match(ui,/Відокремлені складські позиції/);
 assert.match(ui,/Окремі записи плану/);
 assert.match(ui,/Відокремлена позиція/);
 assert.doesNotMatch(ui,/addDoorComponentToPlan|\/assemblies\/door-plan-components/);
});
test('after split the original inspector refreshes and inventory navigation remains',()=>{
 assert.match(ui,/const fresh=await load\(ticket\)/);
 assert.match(ui,/setSelected\(updated\)/);
 assert.match(ui,/setPreview\(next\)/);
 assert.match(ui,/warehouse:inventory-changed/);
 assert.match(ui,/Відкрити склад і оформити продаж/);
 assert.match(ui,/send\('sale'/);
 assert.match(ui,/assembly_remainder:remainder/);
});
test('split UI stays accessible and does not auto-submit on checkbox choice',()=>{
 assert.match(ui,/<details className="assembly-physical-split">/);
 assert.match(ui,/type="checkbox" checked=\{checked\}/);
 assert.match(ui,/aria-label=\{'Стан: '\+entry\.label\}/);
 assert.match(ui,/onClick=\{\(\)=>void splitPhysicalUnit\(selected\)\}/);
 assert.match(css,/\.assembly-split-confirm/);
 assert.match(css,/@media\(max-width:650px\)/);
});
