import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const compile=async name=>'data:text/javascript;base64,'+Buffer.from(ts.transpileModule(await readFile(new URL('../src/'+name,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64');
const {isSmartReady,SMART_REVISION,SMART_FEATURES}=await import(await compile('smartSearch.ts'));
const valid={status:'ready',contract_version:8,required_revision:SMART_REVISION,database_revisions:[SMART_REVISION],features:[...SMART_FEATURES]};
test('only the exact v8 single head is ready; additive features allowed',()=>{assert(isSmartReady(valid));assert(isSmartReady({...valid,features:[...SMART_FEATURES,'future-addition']}));});
for(const [label,value] of Object.entries({null:null,empty:{},status:{...valid,status:'starting'},contract:{...valid,contract_version:7},stringVersion:{...valid,contract_version:'8'},minimum:{...valid,required_revision:'d86f21a90b34'},noHeads:{...valid,database_revisions:undefined},unknown:{...valid,database_revisions:['unknown']},emptyHeads:{...valid,database_revisions:[]},scalarHeads:{...valid,database_revisions:SMART_REVISION},mixed:{...valid,database_revisions:[SMART_REVISION,'unknown']},bothKnown:{...valid,database_revisions:[SMART_REVISION,'d86f21a90b34']},duplicate:{...valid,database_revisions:[SMART_REVISION,SMART_REVISION]},noFeatures:{...valid,features:null}}))test('rejects '+label,()=>assert.equal(isSmartReady(value),false));
for(const feature of SMART_FEATURES)test('requires '+feature,()=>assert.equal(isSmartReady({...valid,features:SMART_FEATURES.filter(f=>f!==feature)}),false));
const {api}=await import(await compile('api.ts'));
test('optional expected HTTP status is strict; legacy success semantics unchanged',async()=>{
 const saved={fetch:globalThis.fetch,document:globalThis.document,window:globalThis.window};
 try{
 globalThis.document={cookie:''};globalThis.window={dispatchEvent(){}};
 for(const status of [200,201,202]){
  globalThis.fetch=async()=>new Response(JSON.stringify(valid),{status,headers:{'Content-Type':'application/json'}});
  if(status===200)assert.deepEqual(await api('/smart-search/readiness','GET',undefined,200),valid);
  else await assert.rejects(()=>api('/smart-search/readiness','GET',undefined,200),e=>e.status===status);
  assert.deepEqual(await api('/legacy'),valid);
 }
 }finally{Object.assign(globalThis,saved);}
});
