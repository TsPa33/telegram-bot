import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import ts from 'typescript';import {spawnSync} from 'node:child_process';
const aliases=JSON.parse(fs.readFileSync(new URL('../src/corporateCategoryAliases.json',import.meta.url)));
const raw=fs.readFileSync(new URL('../src/catalogueLabels.ts',import.meta.url),'utf8').replace(/import corporateAliases[^\n]+\n/,`const corporateAliases=${JSON.stringify(aliases)};\n`);
const code=ts.transpileModule(raw,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {corporateCategoryGroups,categoryOptionLabel}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('frontend category aliases exactly mirror the backend authoritative classifier',()=>{
 const script="import ast,json; t=ast.parse(open('../backend/app/services/plan_parts_classification.py').read()); print(json.dumps(ast.literal_eval(next(n.value for n in t.body if isinstance(n,ast.Assign) and any(getattr(x,'id','')=='CATEGORY_ALIASES' for x in n.targets)))))";
 const r=spawnSync('python',['-c',script],{encoding:'utf8'});assert.equal(r.status,0,r.stderr);assert.deepEqual(aliases,JSON.parse(r.stdout));assert.equal(Object.keys(aliases).length,12);
});
test('corporate root groups aggregate aliases without exposing part/subcategory roots',()=>{
 const rows=[{id:'a',kind:'category',name:'Електрика'},{id:'b',kind:'category',name:'Електрика та електроніка'},{id:'sub',kind:'subcategory',parent_id:'a',name:'Запобіжники'},{id:'p',kind:'part',name:'Стартер'},{id:'legacy-part-root',kind:'category',name:'Стартер'}];
 const groups=corporateCategoryGroups(rows);assert.equal(groups.length,1);assert.equal(groups[0].label,'Електрика та електроніка');assert.deepEqual(groups[0].members.map(x=>x.id),['a','b']);assert.deepEqual(rows[2].parent_id,'a');
});
test('duplicate selector labels omit source keys and internal identifiers',()=>{
 const rows=[{id:'internal-a',name:'Оптика',kind:'subcategory',source:'carpot.v3'},{id:'internal-b',name:'Оптика',kind:'subcategory',source:'vendor.secret'}];
 for(const r of rows){const label=categoryOptionLabel(r,rows);assert(!/carpot|vendor|internal|#/.test(label));assert.match(label,/варіант [12]/);}
});
