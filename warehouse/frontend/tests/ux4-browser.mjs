// UX4 against a real disposable local API/DB. No staging/provider requests.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local test database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{
 await fs.mkdir('test-results',{recursive:true});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[],paid=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url())||r.method()==='POST'&&/plan-parts-checklist/.test(r.url()))paid.push(r.url());});
  const registered=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'UX4 local test',email:`ux4-${viewport.width}-${Date.now()}@example.test`,password:'offline-ux4-long-password'}});
  assert(registered.ok());const session=await registered.json(),headers={'X-CSRF-Token':session.csrf_token};
  async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
  const volvo=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010,vin:'YV1CZ123456789012',notes:'Existing owner data'});
  const bmw=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2012,engine:'Existing actual engine',transmission:'Existing actual transmission'});
  const old=await post('/parts',{name:'Previous stock part',vehicle_id:volvo.id,oem_number:'OWN-123',selling_price:'900.00',description:'Preserve original description',location:'Old-A'});
  await post(`/parts/${old.id}/operations`,{type:'receipt',quantity:4,reason:'Earlier stock'});
  await post(`/parts/${old.id}/operations`,{type:'sale',quantity:1,reason:'Earlier sale'});
  const oldSnapshot=await (await context.request.get(origin+`/api/v1/parts/${old.id}`)).json();
  await page.goto(origin+'/vehicles');
  await expect(page.locator('.sidebar nav a')).toHaveCount(4);
  assert.deepEqual(await page.locator('.sidebar nav a').allTextContents(),['Пошук запчастин','Автомобілі','Склад','Статистика']);
  assert.equal(await page.locator('.sidebar nav a[href="/archive"]').count(),0);
  const card=page.locator('.vehicle-summary-card').filter({has:page.getByRole('button',{name:'Volvo XC90',exact:true})});
  await expect(card).toContainText('2010 · №1');await expect(card.locator('.vehicle-stock-count')).toContainText('1');
  await expect(card.getByRole('button',{name:'Двигун Volvo XC90',exact:true})).toContainText('Вибрати двигун');
  await card.getByRole('button',{name:'Двигун Volvo XC90',exact:true}).click();
  let dialog=page.locator('dialog[open]').last();await dialog.getByLabel('Двигун',{exact:true}).fill('2.4 D5 — значення власника');await dialog.getByRole('button',{name:'Зберегти',exact:true}).click();
  await expect(card.getByRole('button',{name:'Двигун Volvo XC90',exact:true})).toContainText('2.4 D5 — значення власника');
  await card.getByRole('button',{name:'КПП Volvo XC90',exact:true}).click();dialog=page.locator('dialog[open]').last();await dialog.getByLabel('КПП',{exact:true}).fill('Власна автоматична КПП');await dialog.getByRole('button',{name:'Зберегти',exact:true}).click();
  await expect(card.getByRole('button',{name:'КПП Volvo XC90',exact:true})).toContainText('Власна автоматична КПП');
  await page.reload();await expect(card.getByRole('button',{name:'КПП Volvo XC90',exact:true})).toContainText('Власна автоматична КПП');
  await page.screenshot({path:`test-results/ux4-vehicles-${viewport.width}.png`,fullPage:true});
  await card.getByRole('button',{name:'Запчастини Volvo XC90',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Volvo XC90 · 2010 · №1',exact:true})).toBeVisible();
  const add=page.getByRole('button',{name:'Додати на склад (33)',exact:true});await expect(add).toBeEnabled();
  await expect(page.getByText('У довіднику: 33 · На складі: 1',{exact:true})).toBeVisible();
  await expect(page.locator('dialog[open] .vehicle-secondary')).not.toHaveAttribute('open');
  await expect(page.getByText('Розширити власний каталог',{exact:true})).toHaveCount(0);
  const visible=await page.locator('dialog[open]').innerText();for(const noise of [volvo.id,volvo.donor_id,'K-Type','API','carpot.base'])assert(!visible.includes(noise));
  const category=page.locator('.simple-category').first(),sub=category.locator('.simple-subcategory').first(),part=sub.locator('.simple-part').first();
  const boxes=await Promise.all([category.locator('summary input').boundingBox(),sub.locator('.simple-subcategory-title input').boundingBox(),part.locator('input').boundingBox()]);
  assert(boxes[1].x>boxes[0].x&&boxes[2].x>boxes[1].x,'Visually nested category / subcategory / part');
  assert((await category.boundingBox()).width>(await page.getByRole('region',{name:'Каталог запчастин автомобіля'}).boundingBox()).width*.9,'Category uses the available screen width');
  const check=part.locator('input');await check.uncheck();await expect(page.getByRole('button',{name:'Додати на склад (32)',exact:true})).toBeEnabled();
  await page.reload();await expect(check).not.toBeChecked();await check.check();await expect(add).toBeEnabled();
  await page.screenshot({path:`test-results/ux4-donor-${viewport.width}.png`,fullPage:true});
  await add.click();dialog=page.locator('dialog[open]').last();await dialog.getByRole('button',{name:'Підтвердити',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Додано 33 запчастин на склад'})).toBeVisible();
  await expect(page.getByText('У довіднику: 33 · На складі: 34',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Закрити',exact:true}).click();await expect(card.locator('.vehicle-stock-count')).toContainText('34');
  await card.getByRole('button',{name:'Запчастини Volvo XC90',exact:true}).click();await expect(page.getByRole('button',{name:'Додати на склад',exact:true})).toBeDisabled();
  await page.locator('dialog[open]').getByRole('button',{name:'Двигун Volvo XC90',exact:true}).click();dialog=page.locator('dialog[open]').last();await dialog.getByLabel('Двигун',{exact:true}).fill('Уточнений двигун власника');await dialog.getByRole('button',{name:'Зберегти',exact:true}).click();
  await expect(page.locator('dialog[open]').getByRole('button',{name:'Двигун Volvo XC90',exact:true})).toContainText('Уточнений двигун власника');
  await page.getByRole('button',{name:'Закрити',exact:true}).click();await expect(card.getByRole('button',{name:'Двигун Volvo XC90',exact:true})).toContainText('Уточнений двигун власника');
  assert.deepEqual(await (await context.request.get(origin+`/api/v1/parts/${old.id}`)).json(),oldSnapshot);
  const vehicles=await (await context.request.get(origin+'/api/v1/vehicles')).json();assert.equal(vehicles.total,2);
  assert.equal(vehicles.items.find(v=>v.id===bmw.id).engine,bmw.engine);
  const audit=await (await context.request.get(origin+`/api/v1/audit?vehicle_id=${volvo.id}&limit=200`)).json();assert(audit.items.some(r=>r.type==='sale'&&r.reason==='Earlier sale'));
  async function navigate(label){if(viewport.width<800)await page.getByRole('button',{name:'Відкрити меню',exact:true}).click();await page.locator('.sidebar').getByRole('link',{name:label,exact:true}).click();}
  await navigate('Пошук запчастин');await expect(page.getByRole('heading',{name:'Пошук запчастин',exact:true})).toBeVisible();assert(new URL(page.url()).pathname==='/');
  await navigate('Налаштування');await expect(page.getByRole('navigation',{name:'Додаткові розділи'}).getByRole('link',{name:'Архів',exact:true})).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
  await context.close();console.log(`PASS UX4 navigation, donor stock counts, engine/KPP edit, nested tree, receipt and old stock/sale preservation ${viewport.width}x${viewport.height}`);
 }
}finally{await browser.close();}
