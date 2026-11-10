// Local reconstruction of the persisted partial113 shape, not real Volvo coverage proof.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Guarded local test harness only');
const out=process.env.WAREHOUSE_SCREENSHOTS||'/tmp/carpot-workspace-qa';fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const width of [1440,390]){
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5231',viewport:{width,height:1000}});
 const signup=await c.request.post('/api/v1/auth/register',{data:{name:'Local Catalogue QA',email:`partial-${crypto.randomUUID()}@example.test`,password:'local-synthetic-test-password'}});assert.equal(signup.status(),201);
 const auth=await signup.json(),headers={'X-CSRF-Token':auth.csrf_token,Cookie:`warehouse_session=${(await c.cookies()).find(cookie=>cookie.name==='warehouse_session').value}`};
 const seed=await c.request.post('http://127.0.0.1:8031/__assembly_fixture?scenario=partial113',{headers});assert.equal(seed.status(),200,await seed.text());const fixture=await seed.json();
 const base=`/api/v1/vehicles/${fixture.vehicle_id}`;
 const ready=await (await c.request.get(base+'/assemblies/readiness')).json();assert.equal(ready.enabled,false);assert.equal(ready.workspace_enabled,true);
 const state=await (await c.request.get(base+'/global-dismantling')).json();assert.equal(state.saved.payload.coverage,'partial');assert.equal(state.saved.payload.categories.length,113);
 const page=await c.newPage(),errors=[],forbidden=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/plan-parts|plan_parts|\/unified-catalogue\/articles/.test(r.url()))forbidden.push(r.url())});
 await page.goto('/vehicles?donor='+fixture.vehicle_id);
 const work=page.getByRole('region',{name:'Фізичний склад вузлів',exact:true});
 await expect(work).toContainText('План розбору сформовано');await expect(work.getByRole('region',{name:'Показники розбору'})).toContainText('113');
 assert.equal(await page.getByRole('columnheader',{name:'Артикули',exact:true}).count(),0);await expect(work).not.toContainText('Потребує уточнення');
 await work.getByLabel('Пошук у дереві').fill('Локальна деталь 5');
 await work.getByRole('button',{name:'Локальна деталь 5',exact:true}).click();
 await work.getByRole('button',{name:'Підтвердити наявність',exact:true}).click();
 await expect(work.getByRole('region',{name:'Картка запчастини'})).toContainText('Ще не на складі');
 const afterInspect=await (await c.request.get(base+'/assemblies')).json();assert.equal(afterInspect.items.filter(i=>i.part_id).length,0);
 await work.getByRole('button',{name:'Закрити картку',exact:true}).click();
 await work.getByRole('button',{name:'Додати підтверджені на склад',exact:true}).click();
 const report=work.getByRole('region',{name:'Попередній підсумок надходження'});await expect(report).toContainText('Буде додано: 1 позицій');
 await report.getByLabel('Підтверджую фактичне надходження наведених позицій').check();await report.getByRole('button',{name:'Підтвердити надходження',exact:true}).click();
 await expect(work.getByText('Додано на склад: 1 позицій. Пропущено: 112. Залишки збережено.',{exact:true})).toContainText('Додано на склад: 1 позицій');
 await page.reload();await expect(work).toContainText('План розбору сформовано');
 const after=await (await c.request.get(base+'/assemblies')).json();assert.equal(after.items.length,113);assert.equal(after.items.filter(i=>i.part_id).length,1);
 await work.getByLabel('Пошук у дереві').fill('Локальна деталь 5');await work.getByRole('button',{name:'Локальна деталь 5',exact:true}).click();
 await expect(work.getByRole('region',{name:'Картка запчастини'})).toContainText('На складі');
 await work.getByLabel('Пошук у дереві').fill('');
 for(const theme of ['day','night']){
  if(theme==='night')await page.getByRole('button',{name:'Ніч',exact:true}).click();
  if(width===1440)await page.evaluate(()=>scrollTo(0,0));else await work.getByRole('region',{name:'Картка запчастини'}).scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:`${out}/partial113-${width}-${theme}.png`,fullPage:false});
  if(width===390){await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${out}/partial113-overview-${width}-${theme}.png`,fullPage:false});}
 }
 const update=work.locator('.assembly-plan-review');await update.locator('summary').click();
 await update.getByRole('button',{name:'Переглянути зміни плану',exact:true}).click();
 await expect(update).toContainText('Нових позицій:');await expect(update).toContainText('Потрібні рішення:');
 const untouched=await (await c.request.get(base+'/assemblies')).json();assert.equal(untouched.items.length,113);assert.equal(untouched.items.filter(i=>i.part_id).length,1);
 await update.scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 for(const theme of ['day','night']){await page.getByRole('button',{name:theme==='day'?'День':'Ніч',exact:true}).click();await update.scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:`${out}/universal-review-${width}-${theme}.png`,fullPage:false});}
 await page.route('**/api/v1/vehicles/*/assemblies',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Локальна перевірка недоступності списку'})}));
 await page.reload();await expect(page.getByRole('alert')).toContainText('Локальна перевірка недоступності списку');assert.equal(await page.getByRole('columnheader',{name:'Артикули',exact:true}).count(),0);
 assert.deepEqual(errors,[]);assert.deepEqual(forbidden,[]);
 console.log(`${width}: partial113 flag-OFF workspace, inspect without stock, bulk receipt, reload, Day/Night, no JS errors/overflow: PASS`);
 await c.close();
}}finally{await browser.close()}
