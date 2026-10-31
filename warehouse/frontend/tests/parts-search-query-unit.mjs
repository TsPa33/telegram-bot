import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const {partsSearchQuery}=await import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(await readFile(new URL('../src/partsSearchQuery.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
const base={smart:false,q:'',vehicle:'',brand:'',model:'',condition:'',stock:true,page:0};
test('empty search retains bounded server pagination and stock default',()=>assert.deepEqual(Object.fromEntries(partsSearchQuery(base)),{q:'',in_stock:'true',limit:'50',offset:'0'}));
test('OEM/article punctuation and Unicode survive query encoding',()=>{for(const q of ['OEM-123-A','UI3-ARTICLE-0','Фара ліва & скло'])assert.equal(new URLSearchParams(partsSearchQuery({...base,q}).toString()).get('q'),q);});
test('donor filters and physical condition are server-side in ordinary search',()=>assert.deepEqual(Object.fromEntries(partsSearchQuery({...base,vehicle:'donor',brand:'Volvo',model:'XC40',condition:'used',page:2,stock:false})),{q:'',in_stock:'false',limit:'50',offset:'100',vehicle_id:'donor',manufacturer:'Volvo',model:'XC40',condition:'used'}));
test('mode switch preserves query and donor scope but never sends unsupported smart filters',()=>{const input={...base,q:'фара',vehicle:'donor',brand:'Volvo',model:'XC40',condition:'used'},standard=partsSearchQuery(input),smart=partsSearchQuery({...input,smart:true});assert.equal(standard.get('condition'),'used');assert(!smart.has('condition'));for(const key of ['q','vehicle_id','manufacturer','model','in_stock'])assert.equal(smart.get(key),standard.get(key));assert(!smart.has('selling_price'));assert(!smart.has('sort'));});

test('quick category filters ordinary search server-side without filtering only the current page',()=>{
 const query=partsSearchQuery({...base,category:'lighting-root',q:'фара',page:2});
 assert.equal(query.get('category_id'),'lighting-root');assert.equal(query.get('offset'),'100');
 assert.equal(query.get('q'),'фара');
});
test('smart search never receives category_id even if standard category was selected',()=>{
 const query=partsSearchQuery({...base,smart:true,category:'lighting-root',q:'фара'});
 assert.equal(query.get('category_id'),null);
 assert.equal(query.get('q'),'фара');
});
