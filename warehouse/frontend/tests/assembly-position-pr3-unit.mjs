// PR3 position/group acceptance with executable checks of the actual TS helper.
// No DB or paid provider operations; this runs before every Railway Web build.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

const read=name=>readFileSync(new URL('../src/'+name,import.meta.url),'utf8');
const transformed=ts.transpileModule(read('assemblyPresentation.ts'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
});
const exports={};
new Function('exports',transformed.outputText)(exports);
const {assemblyLabel,doorKey,doorOrder,installationAxes,isGenericDoor,
 isKnownDoorComponent,sameDoorInstallation,manuallyReviewableDoorComponent}=exports;
const node=(id,position,side)=>({
 id,name:'Двері',position:position==='front'?'':position==='rear'?'':'',
 installation_position:{position,side}
});

test('four separate door placements have stable identities and Ukrainian names',()=>{
 const cars=[
  node('FL','front','left'),node('FR','front','right'),
  node('RL','rear','left'),node('RR','rear','right'),
 ];
 assert.deepEqual(cars.map(assemblyLabel),[
  'Передні двері ліві','Передні двері праві',
  'Задні двері ліві','Задні двері праві'
 ]);
 assert.deepEqual(cars.map(doorKey),['front:left','front:right','rear:left','rear:right']);
 assert.deepEqual(cars.map(doorOrder),[0,1,2,3]);
 assert.equal(new Set(cars.map(r=>r.id)).size,4);
});

test('saved Cyrillic positions are useful without inventing VIN fitment',()=>{
 assert.deepEqual(installationAxes({name:'Двері',position:'передня ліва'}),{side:'left',position:'front'});
 assert.equal(assemblyLabel({name:'Двері',position:'задня права'}),'Задні двері праві');
 assert.equal(assemblyLabel({name:'Двері'}),'Двері · уточнити розташування');
 assert.equal(doorKey({name:'Двері'}),null);
 assert.equal(assemblyLabel({name:'Двері',position:'передня права',completeness:'complete'}),'Передні двері праві в зборі');
 assert.equal(assemblyLabel({name:'Двері',position:'передня права',completeness:'incomplete'}),'Передні двері праві');
});

test('conflicting source location is not guessed',()=>{
 const n={name:'Двері',position:'передня права',installation_position:{position:'front',side:'left'}};
 assert.equal(installationAxes(n).side,null);
 assert.equal(doorKey(n),null);
 assert.match(assemblyLabel(n),/уточнити розташування/);
});

test('door grouping excludes boot hatch and individual components',()=>{
 assert.equal(isGenericDoor({name:'Двері'}),true);
 assert.equal(isGenericDoor({name:'Двері багажника'}),false);
 assert.equal(isGenericDoor({name:'Замок дверей'}),false);
 assert.equal(isGenericDoor({name:'Скло дверей'}),false);
});

test('source-position candidates are not guessed or auto-attached',()=>{
 const parent=node('FL','front','left');
 const match={id:'glass',name:'Скло дверей',installation_position:{side:'left',position:'front'}};
 const wrong={id:'wrong',name:'Скло дверей',installation_position:{side:'right',position:'front'}};
 const unsure={id:'unknown',name:'Склопідіймач'};
 assert.ok(isKnownDoorComponent(match));
 assert.ok(isKnownDoorComponent(wrong));
 assert.ok(isKnownDoorComponent(unsure));
 assert.equal(sameDoorInstallation(parent,match),true);
 assert.equal(sameDoorInstallation(parent,wrong),false);
 assert.equal(sameDoorInstallation(parent,unsure),false);
 assert.equal(manuallyReviewableDoorComponent(parent,wrong),false);
 assert.equal(manuallyReviewableDoorComponent(parent,unsure),true);
 assert.equal(isKnownDoorComponent({id:'engine',name:'Стартер'}),false);
});

test('UI grouping remains display-only; stock uses existing physical operations',()=>{
 const board=read('AssemblyTree.tsx');
 const backend=readFileSync(new URL('../../backend/app/services/assemblies.py',import.meta.url),'utf8');
 assert.match(board,/assembly-virtual-group/);
 assert.match(board,/doorRoots\.map\(render\)/);
 assert.match(board,/componentCandidates\.map/);
 assert.match(board,/send\('attach'/);
 assert.match(board,/send\('detach'/);
 assert.match(board,/send\('sale'/);
 assert.match(backend,/AssemblyMembership/);
 assert.match(backend,/no_reserves\(db/);
 assert.match(backend,/stock_guard\(/);
 const flow=read('GlobalCatalogueFlow.tsx');
 assert.match(flow,/<details className="uf-catalogue-disclosure">/);
 assert.match(flow,/Точна модифікація не підтверджена/);
 assert.match(flow,/UniversalPlanGenerator/);
});

test('package #3 never modifies stock quantities or adds unknown parts by display grouping',()=>{
 const helper=read('assemblyPresentation.ts');
 assert.doesNotMatch(helper,/fetch\(|api\(|request_key|Part\(|stock\(/);
 assert.match(helper,/display group never creates a Part/);
});
