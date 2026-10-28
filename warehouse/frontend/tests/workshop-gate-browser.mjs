// Compatibility contract tests use real local stock; only readiness is simulated.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local test DB required');
const origin='http://127.0.0.1:5173',endpoint='**/api/v1/workshop/readiness';
const features=['actual_quick_sale_price','ledger_sales_projection','notes_compare_and_set','inspection_patch'];
const response=head=>({status:'ready',contract_version:7,required_revision:'d86f21a90b34',database_revisions:[head],features});
const cases=[];
for(const head of ['d86f21a90b34','a73e05b9c842','b94f62d18e07','b8716962f6b8','021e8f6f220c','41f9a2c87d10']){
 cases.push([`ready ${head}`,{body:response(head)},true]);
 cases.push([`wrong contract ${head}`,{body:{...response(head),contract_version:8}},false]);
 cases.push([`wrong minimum ${head}`,{body:{...response(head),required_revision:head==='d86f21a90b34'?'unknown':head}},false]);
 cases.push([`not ready ${head}`,{body:{...response(head),status:'starting'}},false]);
 for(const feature of features)cases.push([`missing ${feature} ${head}`,{body:{...response(head),features:features.filter(f=>f!==feature)}},false]);
}
for(const [name,revisions] of [['unknown',['unknown']],['mixed-known-unknown',['d86f21a90b34','unknown']],['both heads',['d86f21a90b34','a73e05b9c842']],['duplicate head',['a73e05b9c842','a73e05b9c842']],['empty',[]],['scalar','d86f21a90b34'],['null',null]])cases.push([name,{body:{...response('d86f21a90b34'),database_revisions:revisions}},false]);
for(const field of ['status','contract_version','required_revision','database_revisions','features']){const body={...response('d86f21a90b34')};delete body[field];cases.push([`missing ${field}`,{body},false]);}
cases.push(['wrong minimum schema',{body:{...response('a73e05b9c842'),required_revision:'a73e05b9c842'}},false]);
cases.push(['null body',{body:null},false],['empty body',{body:{}},false],['HTML',{html:true},false]);
for(const status of [401,404,503])cases.push([`HTTP ${status}`,{status,body:response('d86f21a90b34')},false]);
cases.push(['network',{network:true},false]);
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],smart=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/smart-search/'))smart.push(r.url());if(r.method()!=='GET'&&r.url().includes('/api/v1/parts/'))writes.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Compatibility test',email:`gate-${viewport.width}-${Date.now()}@example.test`,password:'local-workshop-gate-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 const created=await context.request.post(origin+'/api/v1/parts',{headers,data:{name:'Compatibility test part',selling_price:'15.25'}});assert(created.ok());const p=await created.json();assert((await context.request.post(origin+`/api/v1/parts/${p.id}/operations`,{headers,data:{type:'receipt',quantity:1,reason:'Local gate test'}})).ok());
 const blocked=page.getByRole('region',{name:'Оновлення майстерні'}),sale=page.getByRole('button',{name:'Продати',exact:true});
 for(const [name,scenario,allowed] of cases){
  await page.unroute(endpoint);await page.route(endpoint,route=>scenario.network?route.abort('failed'):route.fulfill({status:scenario.status||200,...(scenario.html?{contentType:'text/html',body:'<html>not readiness</html>'}:{json:scenario.body})}));
  await page.goto(origin+'/inventory');
  if(scenario.status===401){await expect(page.getByRole('button',{name:'Увійти',exact:true})).toBeVisible();await expect(sale).toHaveCount(0);}
  else if(allowed){await expect(blocked).toHaveCount(0);await expect(sale.filter({visible:true})).toHaveCount(1);await expect(sale.filter({visible:true})).toBeEnabled();}
  else{await expect(blocked.getByRole('button',{name:'Перевірити готовність'})).toBeEnabled();await expect(sale).toHaveCount(0);}
  assert.equal(writes.length,0,`No mutations in ${name}`);
 }
 // A response pending on the network must not expose actions before validation.
 await page.unroute(endpoint);let release;const gate=new Promise(resolve=>release=resolve);await page.route(endpoint,async route=>{await gate;await route.fulfill({json:response('a73e05b9c842')});});await page.goto(origin+'/inventory');await expect(blocked.getByRole('button',{name:'Перевірити готовність'})).toBeDisabled();await expect(sale).toHaveCount(0);release();await expect(sale.filter({visible:true})).toBeEnabled();
 // Failure -> explicit retry -> allowed future head, with the same v7 minimum.
 await page.unroute(endpoint);await page.route(endpoint,route=>route.fulfill({status:503,json:{detail:'Unavailable'}}));await page.reload();await expect(blocked.getByRole('button',{name:'Перевірити готовність'})).toBeEnabled();await page.unroute(endpoint);await page.route(endpoint,route=>route.fulfill({json:response('a73e05b9c842')}));await blocked.getByRole('button',{name:'Перевірити готовність'}).click();await expect(sale.filter({visible:true})).toBeEnabled();
 assert.deepEqual(smart,[]);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await context.close();console.log(`PASS ${cases.length} readiness cases + pending/retry ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
