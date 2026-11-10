import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const code=ts.transpileModule(await readFile(new URL('../src/assemblyOverview.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {categoryKey,assemblyOverview}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('113/2/0/113 are overlapping item counts, not independent totals',()=>{
 const items=Array.from({length:113},(_,i)=>({id:String(i),category:i%2?null:'Потребує уточнення',presence:i<2?'present':'unchecked',planned_quantity:1}));
 const before=structuredClone(items);assert.deepEqual(assemblyOverview(items),{checked:2,stocked:0,attention:113,uncategorized:113});assert.deepEqual(items,before);
});
test('missing and whitespace categories remain visible through the same category key',()=>{
 const items=[{category:null},{},{category:' '},{category:'Потребує уточнення'},{category:'Кузов'}];
 assert.equal(items.filter(n=>categoryKey(n)==='Потребує уточнення').length,4);
 assert.equal(new Set(items.map(categoryKey)).size,2);
});
test('attention is union, stock excludes contained, sold and archived items',()=>{
 const items=[{category:'Кузов',presence:'damaged',completeness:'incomplete'},
 {category:'Кузов',presence:'present',part_id:'1',quantity:1},
 {part_id:'2',parent_id:'1',quantity:1},{part_id:'3',quantity:0,consumed_operation_id:'sale'},
 {part_id:'4',quantity:1,archived:true}];
 assert.deepEqual(assemblyOverview(items),{checked:2,stocked:1,attention:4,uncategorized:3});
});
