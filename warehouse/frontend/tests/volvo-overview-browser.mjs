// Synthetic local display QA. This never reads donor #30 or staging data.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local test harness only');
const out=process.env.WAREHOUSE_SCREENSHOTS||'/tmp/volvo-overview-qa';fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try {for(const width of [1440,390]) {
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5231',viewport:{width,height:1000}});
 const signup=await c.request.post('/api/v1/auth/register',{data:{name:'Synthetic Review QA',email:`review-${crypto.randomUUID()}@example.test`,password:'local-synthetic-test-password'}});
 assert.equal(signup.status(),201);const auth=await signup.json();
 const seed=await c.request.post('http://127.0.0.1:8031/__assembly_fixture?scenario=partial113',{headers:{'X-CSRF-Token':auth.csrf_token,Cookie:`warehouse_session=${(await c.cookies()).find(cookie=>cookie.name==='warehouse_session').value}`}});
 assert.equal(seed.status(),200,await seed.text());const fixture=await seed.json();
 const endpoint=`/api/v1/vehicles/${fixture.vehicle_id}/assemblies`;
 const state=await (await c.request.get(endpoint)).json();assert.equal(state.items.length,113);
 const mocked=structuredClone(state);
 mocked.items.forEach((r,i)=>{r.category=i%2?null:'Потребує уточнення';r.presence=i<2?'present':'unchecked';r.part_id=null;r.parent_id=null;r.quantity=0;});
 const page=await c.newPage(),errors=[],forbidden=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/v1/**',async route=>{
  const req=route.request();
  if(req.method()!=='GET') {forbidden.push(req.url());return route.abort();}
  if(new URL(req.url()).pathname===endpoint)return route.fulfill({json:mocked});
  if(/plan-parts|plan_parts/.test(req.url())){forbidden.push(req.url());return route.abort();}
  return route.continue();
 });
 await page.goto('/vehicles?donor='+fixture.vehicle_id);
 const work=page.getByRole('region',{name:'Фізичний склад вузлів',exact:true});
 const metrics=work.getByRole('region',{name:'Показники розбору'});
 for(const [label,count] of [['У плані',113],['Підтверджено',2],['На складі',0],['Потребує уваги',113]]) {
  await expect(metrics.locator('div').filter({has:page.locator('small',{hasText:label})}).last().locator('strong')).toHaveText(String(count));
 }
 await expect(work).toContainText('ці показники можуть перетинатися');
 const categories=work.getByRole('navigation',{name:'Категорії запчастин'});
 await categories.getByRole('button',{name:/Категорія не визначена/}).click();
 await expect.poll(()=>categories.locator('[aria-pressed=true]').evaluate(e=>getComputedStyle(e).backgroundColor)).toBe('rgb(7, 85, 68)');
 await expect(work.getByRole('button',{name:'Локальна деталь 5',exact:true})).toBeVisible();
 await work.getByLabel('Пошук у дереві').fill('Локальна деталь 112');
 await expect(work.getByRole('button',{name:'Локальна деталь 112',exact:true})).toBeVisible();
 await work.getByLabel('Пошук у дереві').fill('');
 await page.evaluate(()=>scrollTo(0,0));
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:`${out}/overview-${width}.png`,fullPage:false});
 await page.reload();await expect(metrics).toContainText('113');
 assert.deepEqual(errors,[]);assert.deepEqual(forbidden,[]);
 const after=await (await c.request.get(endpoint)).json();assert.deepEqual(after,state);
 console.log(`${width}: 113/2/0/113, null-category filter, search, reload, no overflow/JS errors/writes: PASS`);
 await c.close();
}} finally {await browser.close();}
