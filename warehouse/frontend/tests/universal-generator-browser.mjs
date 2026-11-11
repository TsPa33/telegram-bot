// Real local generator on synthetic donor records, never staging/fitment proof.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local test only');
fs.mkdirSync('/tmp/generator-qa',{recursive:true});
const b=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 const c=await b.newContext({baseURL:'http://127.0.0.1:5234',viewport:{width:1440,height:1000}});
 const signup=await c.request.post('/api/v1/auth/register',{data:{name:'Generator Local QA',email:`generator-${crypto.randomUUID()}@example.test`,password:'local-synthetic-test-password'}});assert.equal(signup.status(),201);
 const auth=await signup.json(),cookie=(await c.cookies()).find(r=>r.name==='warehouse_session').value;
 const v=await c.request.post('/api/v1/vehicles',{headers:{'X-CSRF-Token':auth.csrf_token,Cookie:`warehouse_session=${cookie}`},data:{manufacturer:'Volvo',model:'XC60 (local synthetic)',year:2022}});assert.equal(v.status(),201);const row=await v.json();
 const page=await c.newPage(),errors=[],forbidden=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/\/plan-parts\/|\/vin\/decode|aleto.*(?:refresh|import)/.test(r.url()))forbidden.push(r.url())});
 await page.goto('/vehicles?donor='+row.id);
 const generator=page.getByRole('region',{name:'Універсальний каталог запчастин'});
 await generator.getByRole('button',{name:'Розібрати на запчастини',exact:true}).click();
 await expect(generator).toContainText('Доступних типів:');await expect(generator).toContainText('Довідник CarPot');await expect(generator).toContainText('Потребує уточнення');
 await page.screenshot({path:'/tmp/generator-qa/preview-1440.png',fullPage:false});
 await generator.getByRole('button',{name:'Зберегти перелік',exact:true}).click();
 await expect(generator.getByRole('button',{name:'Оновити каталог',exact:true})).toBeVisible();
 const state=await (await c.request.get(`/api/v1/vehicles/${row.id}/dismantling-v3`)).json();assert.ok(state.total>100);assert.equal((await (await c.request.get('/api/v1/parts')).json()).total,0);
 const tree=page.getByRole('region',{name:'Фізичний склад вузлів'});await expect(tree.getByRole('region',{name:'Показники розбору'})).toContainText(String(state.total));
 await page.reload();await expect(generator.getByRole('button',{name:'Оновити каталог',exact:true})).toBeVisible();
 await generator.getByRole('button',{name:'Оновити каталог',exact:true}).click();await expect(generator).toContainText('Нових позицій: 0');await generator.getByRole('button',{name:'Скасувати',exact:true}).click();
 await page.setViewportSize({width:390,height:844});await generator.scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:'/tmp/generator-qa/saved-390.png',fullPage:false});
 assert.deepEqual(errors,[]);assert.deepEqual(forbidden,[]);console.log(`Generator UI 1440/390: ${state.total} saved planned positions, no stock, reload/regeneration without duplicates, no paid/source calls/JS errors: PASS`);
 await c.close();
}finally{await b.close()}
