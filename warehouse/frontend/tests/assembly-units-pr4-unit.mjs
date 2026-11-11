import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const read=file=>readFileSync(new URL('../src/'+file,import.meta.url),'utf8');
const transpiled=ts.transpileModule(read('assemblyUnitCatalog.ts'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
});
const exports={};
new Function('exports',transpiled.outputText)(exports);
const {allAssemblyUnits,assemblyUnitFor,assemblyReferenceLines}=exports;
const root=(id,name)=>({id,name,part_id:'a-real-existing-stock-id'});

test('24 independently resaleable unit families are recognized without duplicating catalogue types',()=>{
 const units=allAssemblyUnits();
 assert.equal(units.length,24);
 assert.equal(new Set(units.map(x=>x.id)).size,units.length);
 assert.ok(units.every(x=>x.parts.length>=5));
 assert.ok(units.every(x=>x.parts.every(label=>typeof label==='string'&&label.length>3)));
 const named=['Двері','Капот','Кришка багажника / двері багажного відділення','Бампер',
 'Зовнішнє дзеркало','Фара','Задній ліхтар','Двигун у зборі','Коробка передач',
 'Стартер','Генератор','Компресор кондиціонера','Гальмівний супорт','Кермова рейка',
 'Сидіння','Панель приладів','Радіатор охолодження','Турбокомпресор','Паливний бак',
 'Роздавальна коробка','Диференціал','Тяговий електродвигун','Кермова колонка','Підрамник'];
 assert.equal(named.length,24);
 for(const name of named)assert.ok(assemblyUnitFor(root(name,name)),name);
});
test('ordinary part types are not mistakenly treated as physical assemblies',()=>{
 for(const name of ['Замок дверей','Скло дверей','Підсилювач бампера','Джгут проводки дверей',
 'Головка блока циліндрів','Форсунка','Датчик двигуна','Гальмівна колодка','Склопідіймач',
 'Кронштейн генератора','Система безпеки','Обшивка сидіння']){
  assert.equal(assemblyUnitFor({name}),null,name);
 }
});
test('a whole door, engine or gearbox has reference components but remains one original stock part',()=>{
 for(const name of ['Двері','Двигун у зборі','Коробка передач']){
  const parent=root('original-unit',name);
  const entries=assemblyReferenceLines(parent,[parent],[]);
  assert.ok(entries.length>=5);
  assert.ok(entries.every(x=>x.kind==='reference'&&x.linkedId===undefined));
  assert.equal(parent.part_id,'a-real-existing-stock-id');
  assert.equal(entries.length,assemblyUnitFor(parent).parts.length);
 }
});
test('real physical children and separately saved plan items remain distinct and retain IDs',()=>{
 const parent=root('FL','Двері');
 const physicallyAttached={id:'part-original',name:'Скло дверей',part_id:'existing-part',parent_id:'FL'};
 const planned={id:'planned-original',name:'Замок дверей',part_id:null,plan_parent_id:'FL'};
 const unrelated={id:'other',name:'Обшивка дверей',part_id:'other-stock-id',plan_parent_id:'FR'};
 const entries=assemblyReferenceLines(parent,[parent,planned,unrelated],[physicallyAttached]);
 const glass=entries.find(x=>x.label==='Скло дверей');
 const lock=entries.find(x=>x.label==='Замок дверей');
 const trim=entries.find(x=>x.label==='Обшивка дверей');
 assert.deepEqual([glass.kind,glass.linkedId],['attached','part-original']);
 assert.deepEqual([lock.kind,lock.linkedId],['existing_plan','planned-original']);
 assert.equal(trim.kind,'reference');
 assert.ok(!entries.some(x=>x.linkedId==='other'));
});
test('templates cannot generate a stock or plan operation and UI has no add-each-component action',()=>{
 const source=read('assemblyUnitCatalog.ts'),ui=read('AssemblyTree.tsx');
 assert.doesNotMatch(source,/fetch\(|api\(|request_key|new Part|new DismantlingItem|AssemblyMembership\(/);
 assert.doesNotMatch(ui,/addDoorComponentToPlan|pendingTemplate|door-plan-components|Додати до плану/);
 assert.match(ui,/assemblyUnitFor/);
 assert.match(ui,/assemblyReferenceLines/);
 assert.match(ui,/Довідковий склад/);
 assert.match(ui,/Окремі записи плану/);
 assert.match(ui,/Підтвердити комплектність вузла/);
 assert.match(ui,/send\('attach'/);
 assert.match(ui,/send\('detach'/);
 assert.match(ui,/send\('sale'/);
 assert.match(ui,/role="status"/);
});
test('reference components never count as real donor or stock inventory',()=>{
 const ui=read('AssemblyTree.tsx');
 assert.match(ui,/const items:Row\[\]=data.items\|\|\[\]/);
 assert.match(ui,/stocked=items.filter\(n=>n.part_id/);
 assert.match(ui,/У плані',items.length/);
 assert.match(ui,/template.filter\(entry=>entry.kind!=='attached'\)/);
});
