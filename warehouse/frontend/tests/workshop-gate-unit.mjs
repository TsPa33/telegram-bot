// Test the real gate loader without a server, credentials or database.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../src/WorkshopDialogs.tsx',import.meta.url),'utf8');
const gate=source.slice(source.indexOf('export function WorkshopGate('));
assert(gate.startsWith('export function WorkshopGate('));
const js=ts.transpileModule(gate.replace('export function','function'),{compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
const features=['actual_quick_sale_price','ledger_sales_projection','notes_compare_and_set','inspection_patch'];
const heads=['d86f21a90b34','a73e05b9c842','b94f62d18e07','b8716962f6b8','021e8f6f220c','41f9a2c87d10','5c7d9e1a320f','76af12de4b90','84d2c6fa190b','95c3e7b12a04'];
const ready=head=>({status:'ready',contract_version:7,required_revision:'d86f21a90b34',database_revisions:[head],features:[...features]});
async function validate(value,failure){
 let loader;
 const api=async path=>{assert.equal(path,'/workshop/readiness');if(failure)throw failure;return value;};
 const useLoad=callback=>{loader=callback;return {loading:true,reload(){}};};
 const React={createElement:()=>null};
 new Function('api','useLoad','React',js+';return WorkshopGate;')(api,useLoad,React)({children:null});
 return loader();
}
for(const head of heads){
 test(`accept known sole head ${head}`,()=>validate(ready(head)));
 test(`accept additive features ${head}`,()=>validate({...ready(head),features:[...features,'additive']}));
 for(const [label,patch] of Object.entries({status:{status:'starting'},version:{contract_version:8},stringVersion:{contract_version:'7'},minimum:{required_revision:'unknown'},futureMinimum:{required_revision:'b94f62d18e07'},emptyHeads:{database_revisions:[]},multipleHeads:{database_revisions:[head,'b94f62d18e07']},noFeatures:{features:null}}))
  test(`reject ${label} on ${head}`,()=>assert.rejects(()=>validate({...ready(head),...patch})));
 for(const feature of features)test(`require ${feature} on ${head}`,()=>assert.rejects(()=>validate({...ready(head),features:features.filter(f=>f!==feature)})));
}
for(const value of [null,{}, {...ready(heads[0]),database_revisions:['unknown']}, {...ready(heads[0]),database_revisions:'b94f62d18e07'}])
 test(`reject incomplete/unknown response ${JSON.stringify(value)}`,()=>assert.rejects(()=>validate(value)));
for(const field of ['status','contract_version','required_revision','database_revisions','features'])test(`require ${field}`,async()=>{const value=ready(heads[2]);delete value[field];await assert.rejects(()=>validate(value));});
for(const status of [401,404,503])test(`propagate HTTP ${status}`,async()=>{const error=Object.assign(new Error('HTTP error'),{status});await assert.rejects(()=>validate(null,error),e=>e===error);});
test('propagate network failure',async()=>{const error=new TypeError('Failed to fetch');await assert.rejects(()=>validate(null,error),e=>e===error);});
