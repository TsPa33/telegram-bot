import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const source=await readFile(new URL('../src/orderDraft.ts',import.meta.url),'utf8');const {linePayload,draftAmounts}=await import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
const line=(unit_price,quantity='1',currency='UAH')=>({part_id:'synthetic',name:'Synthetic',donor:'',oem:'',quantity,unit_price,currency});
test('decimal sums are exact and currencies never combined',()=>{assert.deepEqual(draftAmounts([line('0,10','3'),line('0.20'),line('3.50','2','USD')]),{UAH:'0.50',USD:'7.00'});});
test('large totals use integer cents without floating point loss',()=>{assert.deepEqual(draftAmounts([line('999999999999.99','1000000')]),{UAH:'999999999999990000.00'});});
test('zero price is explicit; missing price is not zero',()=>{assert.deepEqual(draftAmounts([line('0','1','USD'),line('')]),{USD:'0.00'});assert.throws(()=>linePayload([line('')]));});
test('payload contains only part quantity agreed price and currency',()=>{assert.deepEqual(linePayload([line('12,34','2')]),[{part_id:'synthetic',quantity:2,unit_price:'12.34',currency:'UAH'}]);});
test('invalid quantities and precision are rejected before command',()=>{for(const q of ['0','-1','1.5','1000001',''])assert.throws(()=>linePayload([line('1',q)]));for(const price of ['-1','1.234','NaN','1e3',''])assert.throws(()=>linePayload([line(price)]));});
