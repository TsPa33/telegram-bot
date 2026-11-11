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
 isKnownDoorComponent,sameDoorInstallation,manuallyReviewableDoorComponent,suggestedDoorComponents,doorTemplateEntries}=exports;
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
 assert.match(board,/assembly-virtual-group/);
 assert.match(board,/doorRoots\.map\(render\)/);
 assert.match(board,/componentCandidates\.map/);
 assert.match(board,/send\('attach'/);
 assert.match(board,/send\('detach'/);
 assert.match(board,/send\('sale'/);
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

test('nested candidate preview reuses existing IDs and only evidence-matched placements',()=>{
 const root=node('door-front-left','front','left');
 const matched={id:'original-glass-part',name:'Скло дверей',position:'передня ліва',part_id:'stock-part-original'};
 const unknown={id:'unknown-glass',name:'Скло дверей',position:''};
 const wrong={id:'wrong-glass',name:'Скло дверей',position:'передня права'};
 const joined={id:'joined-glass',name:'Скло дверей',position:'передня ліва',parent_id:'another-door'};
 const sold={id:'sold-glass',name:'Скло дверей',position:'передня ліва',consumed_operation_id:'sale-op'};
 const irrelevant={id:'engine',name:'Блок циліндрів',position:'передня ліва'};
 const found=suggestedDoorComponents(root,[matched,unknown,wrong,joined,sold,irrelevant,root]);
 assert.deepEqual(found.map(x=>x.id),['original-glass-part']);
 assert.equal(found[0],matched,'same object and physical ID, not a new stock record');
 assert.deepEqual(suggestedDoorComponents({name:'Двері'},[matched]),[]);
});
test('reference-aligned details visually separate attached children and unlinked candidates',()=>{
 const tree=read('AssemblyTree.tsx');
 assert.match(tree,/assembly-children/);
 assert.match(tree,/Фізично приєднані/);
 assert.match(tree,/Компоненти дверей/);
 assert.match(tree,/Типовий склад · \{template.length\} позицій/);
 assert.match(tree,/suggestedDoorComponents/);
 assert.match(tree,/Кандидат|Не включено/);
 assert.match(tree,/preview\.memberships\?\.length/);
 assert.match(tree,/assembly-manage-shortcut/);
 const css=read('assembly-tree.css');
 assert.match(css,/\.assembly-presence\{display:grid;grid-template-columns:repeat\(3/);
 assert.match(css,/\.assembly-door-candidate/);
 assert.match(css,/\.assembly-inspector-close/);
});

test('door can expand with no physical children, arrow uses expandable not kids.length',()=>{
 const tree=read('AssemblyTree.tsx');
 assert.match(tree,/const expandable=kids\.length>0\|\|isGenericDoor\(node\)/);
 assert.match(tree,/\{expandable\?\(expanded\?<ChevronDown size=\{16\}\/>:<ChevronRight size=\{16\}\/>\):<span\/>\}/);
 assert.match(tree,/if\(isGenericDoor\(node\)\)setOpen\(previous=>new Set\(\[\.\.\.previous,node\.id\]\)\)/);
 assert.match(tree,/template\.filter\(entry=>entry\.kind!=='physically_attached'\)/);
});
test('reference door template renders nine explicit unconfirmed components even without source fitment',()=>{
 const root=node('FL','front','left');
 const rows=doorTemplateEntries(root,[root],[]);
 assert.deepEqual(rows.map(x=>x.label),[
  'Каркас дверей','Скло дверей','Склопідіймач','Замок дверей',
  'Зовнішня ручка дверей','Внутрішня ручка дверей','Обшивка дверей',
  'Проводка дверей','Ущільнювач дверей'
 ]);
 assert.equal(rows.length,9);
 assert.ok(rows.every(row=>row.kind==='template_only'));
 assert.ok(rows.every(row=>row.linkedId===undefined));
 assert.deepEqual(doorTemplateEntries({name:'Двері'},[],[]),[]);
});
test('existing physical and exact source components retain their original IDs, no fabricated Parts',()=>{
 const root=node('FL','front','left');
 const attached={id:'real-child-part',name:'Замок дверей',parent_id:'FL'};
 const confirmed={id:'known-glass-plan',name:'Скло дверей',installation_position:{position:'front',side:'left'}};
 const wrong={id:'right-door-glass',name:'Скло дверей',installation_position:{position:'front',side:'right'}};
 const items=doorTemplateEntries(root,[confirmed,wrong], [attached]);
 const lock=items.find(x=>x.key==='lock'),glass=items.find(x=>x.key==='glass');
 assert.equal(lock.kind,'physically_attached');
 assert.equal(lock.linkedId,attached.id);
 assert.equal(glass.kind,'source_candidate');
 assert.equal(glass.linkedId,confirmed.id);
 assert.ok(items.filter(x=>x.kind==='template_only').every(x=>x.linkedId===undefined));
 assert.equal(items.some(x=>x.linkedId===wrong.id),false);
});

test('level two is its own collapse control, and every type can become a managed plan item',()=>{
 const tree=read('AssemblyTree.tsx');
 assert.match(tree,/<details className="assembly-door-component-preview">/);
 assert.match(tree,/<summary className="assembly-component-preview-heading">/);
 assert.match(tree,/assembly-template-control/);
 assert.match(tree,/Додати до плану/);
 assert.match(tree,/addDoorComponentToPlan/);
 assert.match(tree,/\/assemblies\/door-plan-components/);
 assert.match(tree,/request_key:pendingTemplate\.current\.key/);
 assert.match(tree,/setOpen\(old=>new Set\(\[\.\.\.old,parent\.id\]\)\)/);
 assert.match(tree,/plan_parent_id/);
 assert.match(tree,/Відкрити керовану позицію плану/);
});
