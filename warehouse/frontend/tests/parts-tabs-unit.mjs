import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/vehicleModificationLabel.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {vehicleModificationLabel:label}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('make/model/year and free text do not substitute for selected modification',()=>{assert.deepEqual(label({manufacturer:'Volvo',model:'XC40',year:2018,engine:'2.0'}),{label:'Модифікацію не вибрано',details:'',selected:false});});
test('selected ID uses its own saved description and confirmed units only',()=>{assert.deepEqual(label({ktype:2,engine:'Old'},[{ktype:1,modification:'Other',power_kw:99},{ktype:2,modification:'1.9 JTD',displacement_cc:1910,power_ps:110}]),{label:'1.9 JTD',details:'1910 см³ · 110 к.с.',selected:true});});
test('selected older ID without saved description is not presented as missing',()=>{for(const engine of ['', 'Потребує уточнення','Не вказано'])assert.equal(label({ktype:3,engine}).label,'Модифікацію вибрано');assert.equal(label({ktype:3,engine:'1.9 JTD'}).label,'1.9 JTD');});
