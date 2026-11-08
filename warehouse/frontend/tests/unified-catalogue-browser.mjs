// Actual built UI + synthetic local PostgreSQL/API. Never staging or paid providers.
import {chromium,expect as baseExpect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
const origin='http://127.0.0.1:5227';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit local E2E guard required');
const out=process.env.WAREHOUSE_SCREENSHOTS||'/tmp/carpot-unified-catalogue-browser';fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']}),expect=baseExpect.configure({timeout:15000});
try{
 for(const width of [1440,390]){
  const context=await browser.newContext({baseURL:origin,viewport:{width,height:width===390?844:1000}});
  const r=await context.request.post('/api/v1/auth/register',{data:{name:'Синтетичний Volvo',email:`volvo-${crypto.randomUUID()}@example.test`,password:'synthetic-volvo-browser-only-password'}});
  assert.equal(r.status(),201);const auth=await r.json();
  const v=await context.request.post('/api/v1/vehicles',{headers:{'X-CSRF-Token':auth.csrf_token},data:{manufacturer:'Volvo',model:'XC90 II',year:2018,donor_id:'SYNTHETIC-'+width}});
  assert.equal(v.status(),201);const vehicle=await v.json();
  const page=await context.newPage(),errors=[],paid=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/plan-parts/')&&r.url().includes('/lookup'))paid.push(r.url());if(!r.url().startsWith(origin)&&!r.url().startsWith('data:'))external.push(r.url())});
  await page.goto('/vehicles?donor='+vehicle.id);
  const panel=page.getByRole('region',{name:'Розбір автомобіля',exact:true});
  await expect(panel).toBeVisible();

  await panel.getByLabel('Модифікація',{exact:true}).selectOption('catalogue:107555');
  await panel.getByRole('button',{name:'Продовжити',exact:true}).click();
  await panel.getByRole('button',{name:'Сформувати план розбору',exact:true}).click();
  await expect(panel).toContainText('Список збережено');
  await expect(page.locator('.wd-board')).toBeVisible();
  await page.reload();await expect(panel).toContainText('Список збережено');
  await expect(page.getByText('Лампа',{exact:true}).first()).toBeVisible();
  page.on('dialog',d=>d.accept());
  await page.getByRole('button',{name:'Додати 1 шт.',exact:true}).click();
  await expect(page.locator('.wd-chip.received').first()).toBeVisible();
  await page.getByRole('button',{name:'Налаштування запчастин',exact:true}).click();
  await page.locator('.wd-article').first().click();
  await expect(page.getByText('OEM-кроси: OEM-ONE, OEM-TWO',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Призначити та зберегти',exact:true}).click();
  await expect(page.locator('.wd-article').first()).toContainText('HELLA');
  await page.locator('.wd-article').first().click();
  await page.getByRole('button',{name:'Призначити OEM OEM-ONE',exact:true}).click();
  await expect(page.getByRole('button',{name:'OEM-ONE',exact:true})).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'horizontal overflow');
  await page.getByRole('button',{name:'Розбір і запчастини',exact:true}).click();
  await expect(panel.locator('.uf-status')).toHaveText('У процесі розбору');
  await expect(panel.locator('.wd-board')).toHaveCount(1);
  await expect(panel.locator('.uf-stage')).toHaveCount(0);
  await page.screenshot({path:`${out}/volvo-${width}.png`,fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);assert.deepEqual(external,[]);
  const inventory=await context.request.get('/api/v1/parts');assert.equal(inventory.status(),200);const actual=await inventory.json();const items=actual.items||actual;assert.equal(items.length,1);assert.equal(items[0].quantity,1);assert.equal(items[0].article_number,'EXAMPLE');assert.equal(items[0].oem_number,'OEM-ONE');
  await context.close();
 }
 console.log('PASS local synthetic Volvo save/reopen, 1440/390, no paid requests, no JS errors/overflow');
}finally{await browser.close()}
