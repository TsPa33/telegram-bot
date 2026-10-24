// Real local API/PostgreSQL + production assets. No Railway or Plan.Parts calls.
import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated warehouse*_test DB required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try {
 await fs.mkdir('test-results',{recursive:true});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  const context=await browser.newContext({viewport}),page=await context.newPage();const errors=[],paid=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url())||r.method()==='POST'&&/plan-parts-checklist/.test(r.url()))paid.push(r.url());});
  const registered=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Local simple test',email:`simple-${viewport.width}-${Date.now()}@example.test`,password:'offline-e2e-long-password'}});
  assert(registered.ok());const session=await registered.json(),headers={'X-CSRF-Token':session.csrf_token};
  const created=await context.request.post(origin+'/api/v1/vehicles',{headers,data:{manufacturer:'Volvo',model:'XC90',year:2010,status:'planned'}});assert(created.ok());const vehicle=await created.json();
  const base=origin+`/api/v1/vehicles/${vehicle.id}/dismantling`;
  const parts=async()=>(await (await context.request.get(origin+`/api/v1/parts?vehicle_id=${vehicle.id}`)).json());
  const view=async()=>(await (await context.request.get(base+'/workspace')).json());
  await page.goto(origin+`/vehicles?donor=${vehicle.id}`);
  const add=()=>page.getByRole('button',{name:/^Додати на склад/});
  await expect(add()).toHaveText('Додати на склад (33)');assert.equal((await parts()).total,0);
  await expect(page.getByRole('button',{name:/Почати розбір|Продовжити розбір/})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Каталог запчастин автомобіля'}).getByRole('combobox')).toHaveCount(0);
  await page.locator('.simple-category>summary').filter({hasText:'Освітлення'}).click();await page.locator('.simple-subcategory>summary').filter({hasText:'Переднє освітлення'}).click();
  await expect(page.getByRole('checkbox',{name:'Вибрати Фара · Ліва',exact:true})).toBeChecked();
  assert.equal((await view()).counts.included,33);
  const bodyText=await page.locator('body').innerText();assert(!bodyText.includes(vehicle.id));assert(!bodyText.includes(vehicle.donor_id));
  const body=page.getByRole('checkbox',{name:'Вибрати категорію Кузов',exact:true});await body.uncheck();
  await expect(add()).toHaveText('Додати на склад (23)');assert.equal((await parts()).total,0);
  await page.locator('.simple-category>summary').filter({hasText:'Кузов'}).click();
  const doors=page.getByRole('checkbox',{name:'Вибрати підкатегорію Двері',exact:true});await doors.check();
  await expect(add()).toHaveText('Додати на склад (27)');await body.check();await expect(add()).toHaveText('Додати на склад (33)');
  const left=()=>page.getByRole('checkbox',{name:'Вибрати Фара · Ліва',exact:true});await left().uncheck();await expect(add()).toHaveText('Додати на склад (32)');
  await page.reload();await expect(add()).toHaveText('Додати на склад (32)');await page.locator('.simple-category>summary').filter({hasText:'Освітлення'}).click();await page.locator('.simple-subcategory>summary').filter({hasText:'Переднє освітлення'}).click();await expect(left()).not.toBeChecked();await expect(add()).toHaveText('Додати на склад (32)');
  // Search never silently changes the scope of the main receipt button.
  await page.getByRole('searchbox',{name:'Пошук деталей',exact:true}).fill('дзеркало');await expect(add()).toHaveText('Додати на склад (32)');
  const confirmation=await view();await add().click();let dialog=page.locator('dialog[open]').last();
  await expect(dialog).toContainText('Нових позицій: 32');await expect(dialog).toContainText('кількість кожної — 1');await expect(dialog).toContainText('Volvo XC90 · 2010');
  await dialog.getByRole('button',{name:'Скасувати',exact:true}).click();assert.equal((await parts()).total,0);
  await add().click();dialog=page.locator('dialog[open]').last();await dialog.getByRole('button',{name:'Підтвердити',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Додано 32 запчастин на склад'})).toBeVisible();assert.equal((await parts()).total,32);
  assert((await parts()).items.every(p=>p.quantity===1));
  const retry=await context.request.post(base+'/add-stock',{headers,data:{expected_count:confirmation.add_count,selection_token:confirmation.add_token,quantity:1}});assert.equal((await retry.json()).updated,0);
  await page.reload();await expect(add()).toBeDisabled();const receivedCategory=page.locator('.simple-category').first();await receivedCategory.locator(':scope>summary').click();await receivedCategory.locator('.simple-subcategory>summary').first().click();await expect(page.getByText('Додано на склад · залишок 1',{exact:true}).first()).toBeVisible();
  const audit=(await (await context.request.get(origin+`/api/v1/audit?vehicle_id=${vehicle.id}&limit=200`)).json()).items;assert.equal(audit.filter(a=>a.type==='receipt').length,32);
  // Import 1001 synthetic own types, automatically extend same donor, paginate.
  const upload={source:'browser.owned',provenance:'Independent synthetic browser test; not fitment',license_reference:'Own test data, reusable',types:Array.from({length:1001},(_,i)=>({catalog_key:`browser-${i}`,category_key:'browser',category_name:'Browser tests',subcategory_key:'types',subcategory_name:'Owned types',name:`Owned test type ${String(i).padStart(4,'0')}`,position:''}))};
  await page.goto(origin+'/settings');
  await page.getByText('Розширити власний каталог',{exact:true}).click();
  await page.getByLabel('JSON власного каталогу',{exact:true}).setInputFiles({name:'owned.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(upload))});
  await page.getByRole('checkbox',{name:/Маю права на збереження/}).check();await page.getByRole('button',{name:'Перевірити каталог',exact:true}).click();
  await expect(page.getByText('Нових: 1001. Оновлено: 0. Усього в джерелі: 1001.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Імпортувати до власного довідника',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Імпортовано: нових 1001'})).toBeVisible();
  await page.goto(origin+`/vehicles?donor=${vehicle.id}`);
  await expect(add()).toHaveText('Додати на склад (1001)');assert.equal((await view()).counts.total,1034);assert.equal((await parts()).total,32);
  await page.getByRole('searchbox',{name:'Пошук деталей',exact:true}).fill('Owned test type');
  await expect(page.getByText('Owned test type 0000',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Наступні',exact:true}).click();
  await expect(page.getByText('Owned test type 0100',{exact:true})).toBeVisible();
  assert(await page.locator('.simple-part').count()<=100);
  await page.getByLabel('Категорія',{exact:true}).selectOption({label:'Browser tests'});
  await expect(page.getByText('Owned test type 0000',{exact:true})).toBeVisible();
  const own=page.getByRole('checkbox',{name:'Вибрати категорію Browser tests',exact:true});await own.uncheck();await expect(add()).toBeDisabled();assert.equal((await parts()).total,32);
  await page.reload();await expect(own).not.toBeChecked();await own.check();await expect(add()).toHaveText('Додати на склад (1001)');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.equal(await page.locator('.simple-part').first().evaluate(e=>getComputedStyle(e).flexDirection),'row');await page.screenshot({path:`test-results/simple-warehouse-${viewport.width}.png`,fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
  await page.getByRole('searchbox',{name:'Пошук деталей',exact:true}).fill('');
  // Open ordinary stock from the post-receipt result (result is session-local).
  await page.goto(origin+`/inventory?vehicle_id=${vehicle.id}`);await expect(page.getByRole('heading',{name:'Запчастини та залишки',exact:true})).toBeVisible();
  await context.close();console.log(`PASS UX3 auto catalogue, hierarchical selection, direct receipt, replay, reload, 1001-type import/pagination ${viewport.width}x${viewport.height}`);
 }
}finally{await browser.close();}
