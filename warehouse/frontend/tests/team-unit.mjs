import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
async function load(name){return import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(await readFile(new URL('../src/'+name,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));}
const {isTeamReady,TEAM_REVISION,TEAM_FEATURES}=await load('teamReadiness.ts');
const valid={status:'ready',contract_version:9,required_revision:TEAM_REVISION,database_revisions:[TEAM_REVISION],features:TEAM_FEATURES,employee_creation_enabled:false};
for(const enabled of [false,true])test('ready schema with creation '+enabled,()=>assert(isTeamReady({...valid,employee_creation_enabled:enabled})));
for(const [name,patch] of Object.entries({status:{status:'starting'},version:{contract_version:8},stringVersion:{contract_version:'9'},revision:{required_revision:'a73e05b9c842'},emptyHeads:{database_revisions:[]},unknownHead:{database_revisions:['unknown']},multipleHeads:{database_revisions:[TEAM_REVISION,'a73e05b9c842']},duplicate:{database_revisions:[TEAM_REVISION,TEAM_REVISION]},stringHeads:{database_revisions:TEAM_REVISION},stringFeatures:{features:TEAM_FEATURES.join(',')},missingFlag:{employee_creation_enabled:undefined},stringFlag:{employee_creation_enabled:'false'}}))test('reject team '+name,()=>assert.equal(isTeamReady({...valid,...patch}),false));
for(const feature of TEAM_FEATURES)test('requires team feature '+feature,()=>assert.equal(isTeamReady({...valid,features:TEAM_FEATURES.filter(f=>f!==feature)}),false));
for(const value of [null,{},'ready',undefined])test('reject incomplete '+JSON.stringify(value),()=>assert.equal(isTeamReady(value),false));
const {allowed,identityKey,roleLabel}=await load('access.ts');
for(const role of [undefined,'UNKNOWN','director'])test('unknown role fails closed '+role,()=>{assert.equal(allowed({role,permissions:['inventory.view']},'inventory.view'),false);assert.equal(roleLabel(role),'Невідома роль');});
for(const role of ['MANAGER','ADMIN'])test(role+' only sees explicitly granted permissions',()=>{assert(allowed({role,permissions:['inventory.view']},'inventory.view'));assert.equal(allowed({role,permissions:['inventory.view']},'parts.view_cost'),false);assert.equal(allowed({role,permissions:'inventory.view'},'inventory.view'),false);});
test('explicit director, never anonymous, has full UI access',()=>{assert(allowed({role:'DIRECTOR',permissions:[]},'inventory.view'));assert.equal(allowed(null,'inventory.view'),false);});
const user={id:'worker-a',workspace_account_id:'owner-a',role:'MANAGER',permissions:['inventory.view','parts.view_cost'],must_change_password:false};
test('identity key ignores permission order and duplicates',()=>assert.equal(identityKey(user),identityKey({...user,permissions:['parts.view_cost','inventory.view','inventory.view']})));
for(const [field,value] of [['id','worker-b'],['workspace_account_id','owner-b'],['role','ADMIN'],['permissions',['inventory.view']],['must_change_password',true]])test('identity key invalidates cached screens on '+field,()=>assert.notEqual(identityKey(user),identityKey({...user,[field]:value})));
const {api}=await load('api.ts');
test('403 refreshes protected identity but never recursively refreshes auth endpoints',async()=>{
 const saved={fetch:globalThis.fetch,document:globalThis.document,window:globalThis.window};
 const events=[];
 try{
  globalThis.document={cookie:''};globalThis.window={dispatchEvent:e=>events.push(e.type)};
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Forbidden'}),{status:403,headers:{'Content-Type':'application/json'}});
  await assert.rejects(()=>api('/auth/me'));assert.deepEqual(events,[]);
  await assert.rejects(()=>api('/parts'));assert.deepEqual(events,['warehouse:permissions-changed']);
 }finally{Object.assign(globalThis,saved);}
});

test('a superseded session response cannot leak data, log out the new user or discard uncertain mutations',async()=>{
 const saved={fetch:globalThis.fetch,document:globalThis.document,window:globalThis.window};
 try{
  const events=[];globalThis.document={cookie:'warehouse_csrf=old-session'};
  globalThis.window={dispatchEvent:e=>events.push(e.type)};
  globalThis.fetch=async()=>{globalThis.document.cookie='warehouse_csrf=new-session';return new Response(JSON.stringify({unit_cost:'private-old-account'}),{status:200});};
  await assert.rejects(()=>api('/parts'),e=>e.message.includes('Сесію змінено')&&!('status' in e));
  assert.deepEqual(events,['warehouse:permissions-changed']);
 }finally{Object.assign(globalThis,saved);}
});

for(const head of ['b8716962f6b8','021e8f6f220c','41f9a2c87d10','5c7d9e1a320f','76af12de4b90','84d2c6fa190b']){
 test('accept verified additive catalogue head '+head,()=>assert(isTeamReady({...valid,database_revisions:[head]})));
 for(const patch of [{contract_version:8},{required_revision:head},{features:[]},{database_revisions:[head,TEAM_REVISION]}])test('keep team contract checks '+head+JSON.stringify(patch),()=>assert.equal(isTeamReady({...valid,database_revisions:[head],...patch}),false));
}
test('platform capability change invalidates protected caches',()=>assert.notEqual(identityKey(user),identityKey({...user,catalogue_platform_admin:true})));

test('virtual inventory head preserves team capabilities',()=>assert(isTeamReady({...valid,database_revisions:['95c3e7b12a04']})));
test('seller pricing head preserves team capabilities',()=>assert(isTeamReady({...valid,database_revisions:['a6d94c72e310']})));
