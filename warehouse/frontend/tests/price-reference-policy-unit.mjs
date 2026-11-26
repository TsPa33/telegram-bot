import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const src=fs.readFileSync(new URL('../src/priceReferencePolicy.ts',import.meta.url),'utf8');
const code=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {adjusted,chooseReference,defaultRule,summary,rowsForApply}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const ctx={currency:'UAH',condition:'used',eligible:true};
const group={currency:'UAH',condition:'used',match:'exact',offer_count:3,minimum:'1000.00',maximum:'2000.00',average:'1500.00'};
const lookup=(references,context=ctx,rule=defaultRule)=>chooseReference({references},context,rule);
test('mean/min/max, markup and discount use integer cents',()=>{
 assert.equal(lookup([group]).value,'1500.00');
 assert.equal(lookup([group],ctx,{...defaultRule,mode:'minimum'}).value,'1000.00');
 assert.equal(lookup([group],ctx,{...defaultRule,mode:'maximum',percent:'10'}).value,'2200.00');
 assert.equal(adjusted('1500.01','-10'),'1350.01');
 assert.equal(adjusted('0.01','-99'),null);
 assert.equal(adjusted('1000','101'),null);
 assert.equal(adjusted('NaN','0'),null);
});
test('no currency/condition mixing, ambiguous cohorts or unsupported references',()=>{
 assert.equal(lookup([group,{...group,condition:'new'}]).value,'1500.00');
 assert.equal(lookup([group,{...group,currency:'USD'}]).value,'1500.00');
 assert.equal(lookup([group,{...group}]),null);
 assert.equal(lookup([{...group,offer_count:2}]),null);
 assert.equal(lookup([group],{...ctx,eligible:false}),null);
 assert.equal(lookup([group],{...ctx,condition:'unknown'}),null);
 assert.equal(chooseReference({references:[group],truncated:true},ctx,defaultRule),null);
 assert.equal(lookup([{...group,match:'similar'}]),null);
 assert.equal(lookup([{...group,match:'similar'}],ctx,{...defaultRule,similar:true}).value,'1500.00');
 assert.equal(lookup([group,{...group,match:'similar'}],ctx,{...defaultRule,similar:true}).group.match,'exact');
});
test('individual resume cannot mutate other ready rows and progress is actual',()=>{
 const rows=[{id:'a',state:'uncertain'},{id:'b',state:'ready'},{id:'c',state:'applied'},{id:'d',state:'attention'},{id:'e',state:'skipped'},{id:'f',state:'pending'}];
 assert.deepEqual(rowsForApply(rows,'a').map(r=>r.id),['a']);
 assert.deepEqual(rowsForApply(rows).map(r=>r.id),['a','b']);
 assert.deepEqual(summary(rows),{total:6,checked:4,ready:1,applied:1,attention:1,skipped:1,pending:1,uncertain:1});
});
