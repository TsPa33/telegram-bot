// Authenticated real UI/API/PG. Local fixtures are test records, never live staging evidence.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const live=process.env.ISSUE502_TARGET==='staging',phase=process.env.ISSUE502_PHASE||'after';
const base=live?'https://confident-sparkle-warehouse-staging.up.railway.app':'http://127.0.0.1:5251';
if(!live&&process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit local test guard required');
if(live&&(!process.env.ISSUE502_STORAGE_STATE||!process.env.ISSUE502_VEHICLE_ID))throw Error('Authorized browser storage file and exact owned donor ID required; no login/stock writes performed');
const dir=process.env.ISSUE502_OUTPUT||`/tmp/issue502-${phase}`;fs.mkdirSync(dir,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
const errors=[],network=[],mutations=[],consoleErrors=[];
if(live&&process.env.ISSUE502_CONFIRM_LOCAL_SPLIT)throw Error('Live stock mutations forbidden');
try{
 const c=await browser.newContext({baseURL:base,viewport:{width:1440,height:1000},...(live?{storageState:process.env.ISSUE502_STORAGE_STATE}:{})});
 if(live)await c.route('**/*',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())&&new URL(route.request().url()).origin===new URL(base).origin?route.continue():route.abort('blockedbyclient'));
 let id,fixture;
 if(live){id=process.env.ISSUE502_VEHICLE_ID;if(!/^[0-9a-f-]{36}$/i.test(id))throw Error('Exact UUID donor ID required');}
 else{
  const signup=await c.request.post('/api/v1/auth/register',{data:{name:'Issue500 Local QA',email:`issue502-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(signup.status(),201);
  const auth=await signup.json();const seed=await c.request.post('http://127.0.0.1:8050/__issue502_fixture',{headers:{'X-CSRF-Token':auth.csrf_token,Cookie:(await c.cookies()).map(v=>`${v.name}=${v.value}`).join('; ')}});assert.equal(seed.status(),200);fixture=await seed.json();id=fixture.vehicle_id;
 }
 const me=await c.request.get('/api/v1/auth/me',{maxRedirects:0});assert.equal(me.status(),200,'Authorized session required');const actor=await me.json();
 const get=async path=>{const r=await c.request.get(path,{maxRedirects:0});assert.equal(r.status(),200,path);return r.json()};
 const initial=await get(`/api/v1/vehicles/${id}/assemblies`),readiness=await get(`/api/v1/vehicles/${id}/assemblies/readiness`);
 const before=await get(`/api/v1/parts?vehicle_id=${id}&limit=200`);
 const page=await c.newPage();page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(20000);page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push({text:m.text(),location:m.location()})});
 page.on('response',r=>{const u=new URL(r.url());if(u.origin===new URL(base).origin)network.push({method:r.request().method(),path:u.pathname,status:r.status(),cacheControl:r.headers()['cache-control']||null,etag:r.headers().etag||null})});
 page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname})});
 await page.goto('/vehicles?donor='+encodeURIComponent(id));await page.screenshot({animations:'disabled',path:`${dir}/initial.png`});
 const cases=live?initial.items.filter(n=>n.part_id&&/бампер/iu.test(n.name)&&[1,6].includes(n.quantity)):fixture.rows;
 assert.ok(cases.some(n=>n.quantity===1)&&cases.some(n=>n.quantity===6),'Both 1 and 6 stock cases required; do not synthesize missing staging records');
 const outcomes=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  for(const n of cases){
   const wait=page.waitForResponse(r=>r.url().endsWith(`/assemblies/${n.id}/preview`));
   await page.locator(`[id="assembly-node-${n.id}"]`).click();await wait;
   const panel=page.getByRole('region',{name:'Картка запчастини',exact:true});
   await expect(panel.locator('.assembly-stock-label')).toBeVisible();
   const action=panel.locator('.assembly-physical-split'),missing=phase==='before'&&/Бампер \(/u.test(n.name);
   if(missing)assert.equal(await action.count(),0,'Baseline decorated-name defect must reproduce');
   else{
    await expect(action.locator('summary')).toBeVisible();await action.locator('summary').click();
    if(n.quantity===6){await expect(action).toContainText('один фізичний вузол');assert.equal(await action.locator('input[type=checkbox]').count(),0);}
    else if(readiness.enabled&&['dismantling.manage','inventory.edit','inventory.adjust_quantity','inventory.create'].every(p=>actor.permissions?.includes(p))){
     await expect(action.locator('input[type=checkbox]').first()).toBeVisible();
     // Choosing a suggestion and a condition is NOT a mutation/receipt.
     await action.locator('input[type=checkbox]').first().check();await action.getByRole('combobox').first().selectOption('damaged');
     await expect(action.getByRole('button',{name:/Відокремити та оприбуткувати/})).toBeDisabled();
    }else await expect(action.locator('[role=status]').first()).toBeVisible();
   }
   await panel.scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal page overflow');
   const name=n.name.includes('передній')?'front-6':n.name.includes('задній')?'rear-1':/двигун/iu.test(n.name)?'engine-1':'door-1';
   await page.screenshot({animations:'disabled',path:`${dir}/${name}-${width}.png`,fullPage:false});
   outcomes.push({width,name:n.name,quantity:n.quantity,actionPresent:await action.count()===1,phase});
   await panel.getByRole('button',{name:'Закрити картку',exact:true}).click();
  }
 }
 if(!live){
  await page.setViewportSize({width:1440,height:1000});const root=fixture.rows.find(n=>n.name==='Бампер (задній)');
  await page.locator(`[id="assembly-node-${root.id}"]`).click();
  const reference=page.locator('.assembly-door-component-preview').first();await reference.locator('summary').click();
  const choice=reference.locator('button.assembly-template-label').first(),label=await choice.innerText();await choice.click();
  const inspector=page.getByRole('region',{name:'Картка запчастини',exact:true});await expect(inspector.getByRole('region',{name:'Довідкова складова'})).toContainText(label);
  await expect(inspector.locator('.assembly-physical-split')).toHaveAttribute('open','');
  assert.equal(await inspector.locator('.assembly-split-row input:checked').count(),0,'Reference selection is not physical confirmation');
  await inspector.getByRole('button',{name:'Закрити картку',exact:true}).click();
 }
 const after=await get(`/api/v1/parts?vehicle_id=${id}&limit=200`);assert.deepEqual(after,before,'Read-only diagnostic must not alter existing stock');
 assert.deepEqual(await get(`/api/v1/vehicles/${id}/assemblies`),initial,'No plan/membership mutations');
 fs.writeFileSync(`${dir}/diagnostic-network.json`,JSON.stringify({network,consoleErrors},null,2));
 assert.deepEqual(errors,[]);assert.deepEqual(mutations,[]);assert.deepEqual(consoleErrors.filter(e=>!e.location.url.endsWith('/favicon.ico')),[],'No unexpected application console errors');
 let previewFailureVisible=null;
 if(!live&&phase==='after'){
  const root=fixture.rows.find(n=>n.name==='Бампер (задній)');const pattern=`**/assemblies/${root.id}/preview`;
  await page.route(pattern,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Injected local preview outage'})}));
  await page.locator(`[id="assembly-node-${root.id}"]`).click();const panel=page.getByRole('region',{name:'Картка запчастини',exact:true});
  await expect(panel).toContainText('Не вдалося перевірити склад');const action=panel.locator('.assembly-physical-split');await expect(action.locator('summary')).toBeVisible();await action.locator('summary').click();await expect(action).toContainText('Оновіть перегляд вузла');assert.equal(await action.locator('input').count(),0);previewFailureVisible=true;
  await page.unroute(pattern);await panel.getByRole('button',{name:'Закрити картку',exact:true}).click();
 }
 let functionalLocalSplit=null;
 if(!live&&phase==='after'&&process.env.ISSUE502_CONFIRM_LOCAL_SPLIT==='1'){
  const root=fixture.rows.find(n=>n.name==='Бампер (задній)');
  const pending=page.waitForResponse(r=>r.url().endsWith(`/assemblies/${root.id}/preview`));await page.locator(`[id="assembly-node-${root.id}"]`).click();await pending;
  const action=page.getByRole('region',{name:'Картка запчастини',exact:true}).locator('.assembly-physical-split');await action.locator('summary').click();
  const choices=action.locator('.assembly-split-row input[type=checkbox]');await choices.nth(0).check();await choices.nth(1).check();await action.getByRole('combobox').nth(1).selectOption('damaged');
  assert.equal((await get(`/api/v1/parts?vehicle_id=${id}&limit=200`)).total,before.total,'No receipt before explicit confirmation');
  await action.getByLabel(/Підтверджую демонтаж 2 деталей/).check();
  const response=page.waitForResponse(r=>r.url().endsWith('/assemblies/split')&&r.request().method()==='POST');await action.getByRole('button',{name:'Відокремити та оприбуткувати 2',exact:true}).click();const posted=await response;assert.equal(posted.status(),200);const result=await posted.json();assert.equal(result.count,2);
  const stock=await get(`/api/v1/parts?vehicle_id=${id}&limit=200`);assert.equal(stock.total,before.total+2);assert.equal(stock.items.find(n=>n.id===root.part_id).quantity,1);
  for(const row of fixture.rows)assert.equal(stock.items.find(p=>p.id===row.part_id).quantity,row.quantity,'All original Part IDs and quantities preserved');
  const tree=await get(`/api/v1/vehicles/${id}/assemblies`);assert.equal(tree.items.find(n=>n.id===root.id).completeness,'incomplete');
  assert.equal(new Set(result.split.map(n=>n.part_id)).size,2);assert.ok(result.split.every(n=>stock.items.find(p=>p.id===n.part_id).quantity===1));
  functionalLocalSplit={count:result.count,rootQuantity:1,frontLotQuantity:6,originalPartIdsPreserved:true};
  await page.screenshot({animations:'disabled',path:`${dir}/local-confirmed-split.png`,fullPage:false});
 }
 const assets=await page.locator('script[src]').evaluateAll(nodes=>nodes.map(n=>n.src));
 const report={target:live?'STAGING':'LOCAL_REAL_AUTH_POSTGRES_TEST_RECORDS',phase,readiness,role:actor.role||'actor',permissions:actor.permissions,outcomes,network,errors,consoleErrors,mutations,diagnosticStockUnchanged:true,functionalLocalSplit,previewFailureVisible,assets,canonicalOrigin:new URL(base).origin,documentPath:'/vehicles?donor=<owned-id>'};
 fs.writeFileSync(`${dir}/report.json`,JSON.stringify(report,null,2));
 console.log(`${report.target} ${phase}: authenticated exact donor route, 1/6 stock, 1440/390, readonly diagnostics + optional explicit local confirmation: PASS (favicon warnings retained in report)`);
 await c.close();
}finally{await browser.close()}
