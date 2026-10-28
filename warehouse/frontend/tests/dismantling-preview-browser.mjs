// Local real auth/API and mobile/desktop verification; no catalogue apply.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const origin=process.env.WAREHOUSE_PREVIEW_ORIGIN||'http://127.0.0.1:5181';
if(process.env.WAREHOUSE_E2E!=='1'||new URL(origin).hostname!=='127.0.0.1')throw Error('Dedicated loopback test environment required');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 for(const width of [1440,390]){
  const context=await browser.newContext({baseURL:origin,viewport:{width,height:900}});
  const auth=await context.request.post('/api/v1/auth/register',{data:{name:'Stage 2A browser',email:`preview-${width}-${Date.now()}@example.test`,password:'local-stage2a-test-password'}});assert.equal(auth.status(),201);
  const user=await auth.json(),headers={'X-CSRF-Token':user.csrf_token};
  const response=await context.request.post('/api/v1/vehicles',{headers,data:{manufacturer:'Volvo',model:'XC90',year:2020,donor_id:'STAGE2A-'+width,acquisition_date:'2026-01-01',acquisition_cost:'10'}});assert.equal(response.status(),201);const vehicle=await response.json();
  const page=await context.newPage(),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET'&&r.url().includes('/api/v1/'))writes.push(new URL(r.url()).pathname);});
  await page.goto(`/vehicles?donor=${vehicle.id}&info=1`);
  await page.getByRole('button',{name:'Переглянути read-only preview',exact:true}).click();
  const section=page.getByRole('region',{name:'Попередній план розбору v3'});await expect(section).toBeVisible();
  await section.getByText('Уточнити параметри лише для preview',{exact:true}).click();
  await section.getByLabel('Силова установка',{exact:true}).selectOption('BEV');await section.getByLabel('Привід',{exact:true}).selectOption('AWD');await section.getByLabel('Точний код двигуна',{exact:true}).fill('TEST-ENGINE');
  await section.getByRole('button',{name:'Сформувати попередній план',exact:true}).evaluate(b=>{b.click();b.click();});
  await expect(section.getByText(/Унікальних позицій: 33/)).toBeVisible();await expect(section.getByText(/Підтверджено: 0/)).toBeVisible();
  await section.getByText(/Унікальних позицій:/).scrollIntoViewIfNeeded();
  await page.screenshot({path:`/workspace/scratch/stage2a-ready-${width}.png`});
  const saved=await context.request.get(`/api/v1/vehicles/${vehicle.id}`);assert.equal((await saved.json()).engine,'');
  assert(writes.every(p=>p===`/api/v1/vehicles/${vehicle.id}/dismantling-preview`));assert.equal(writes.length,1);
  await context.route('**/dismantling-preview',r=>r.fulfill({status:503,json:{detail:'Тестова точна помилка preview'}}));
  await section.getByRole('button',{name:'Сформувати попередній план',exact:true}).click();await expect(section.getByRole('alert')).toHaveText('Тестова точна помилка preview');await expect(section.getByLabel('Точний код двигуна',{exact:true})).toHaveValue('TEST-ENGINE');await expect(section.getByText(/Унікальних позицій:/)).toHaveCount(0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);
  await page.screenshot({path:`/workspace/scratch/stage2a-browser-${width}.png`,fullPage:true});
  await page.reload();await page.getByRole('button',{name:'Переглянути read-only preview',exact:true}).click();await expect(section).toBeVisible();await expect(section.getByText(/Унікальних позицій:/)).toHaveCount(0);assert.equal(writes.filter(p=>p.endsWith('/dismantling-preview')).length,2);
  await context.close();console.log(`PASS ${width}px real auth, preview, no writes, errors, reload, no overflow`);
 }
}finally{await browser.close();}
