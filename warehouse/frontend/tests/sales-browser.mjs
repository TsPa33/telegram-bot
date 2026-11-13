// Real local disposable API/PostgreSQL. Current order checkout replaces legacy quick-sale UI.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local test database required');
const origin=process.env.WAREHOUSE_SALES_ORIGIN||'http://127.0.0.1:5173';
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Local only');
const browser=await chromium.launch({...(process.env.WAREHOUSE_CHROMIUM_PATH?{executablePath:process.env.WAREHOUSE_CHROMIUM_PATH}:{}),args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,extraHTTPHeaders:{'X-Warehouse-Client':'5'}}),page=await context.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))paid.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Local seller test',email:`seller-${crypto.randomUUID()}@example.test`,password:'offline-seller-long-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 async function get(path){const r=await context.request.get(origin+'/api/v1'+path);assert(r.ok(),await r.text());return r.json();}
 const volvo=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),bmw=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2012});
 async function stock(vehicle,name,quantity,extra={}){const p=await post('/parts',{vehicle_id:vehicle.id,name,...extra});if(quantity)await post(`/parts/${p.id}/operations`,{type:'receipt',quantity,reason:'Previous local stock'});return p;}
 const hood=await stock(volvo,'Капот',3,{selling_price:'123.45',oem_number:'OEM-123',article_number:'ART-123',location:'Полиця A'});
 await stock(volvo,'Кардан',1,{selling_price:'45.67',currency:'USD'});await stock(volvo,'Капот потенційний',0);await stock(bmw,'Капот BMW',1);
 const buyer=await post('/buyers',{name:'Seller Buyer QA',phone:'0509876543'});
 const row=name=>page.locator('.ui11-result-wrap,.mobile-search-result,.stock-row-wrap').filter({has:page.getByRole('button',{name,exact:true})});
 const search=page.getByRole('combobox',{name:'Пошук запчастин',exact:true});
 async function searchPage(){await page.goto(origin+'/search');await search.fill('ка');await search.press('Escape');await expect(row('Капот')).toBeVisible();}
 async function action(label,stock=false,scope=row('Капот')){await scope.getByRole('button',{name:'Дії Капот',exact:true}).click();if(stock)await page.getByRole('menuitem',{name:'Складські операції',exact:true}).click();await page.getByRole('menuitem',{name:label,exact:true}).click();return page.getByRole('dialog').last();}
 await page.goto(origin+'/search');await expect(page.getByRole('heading',{name:'Пошук запчастин',exact:true})).toBeVisible();
 await page.getByLabel('Марка пошуку',{exact:true}).selectOption('Volvo');await page.getByLabel('Модель пошуку',{exact:true}).selectOption('XC90');await page.getByLabel('Автомобіль пошуку',{exact:true}).selectOption(volvo.id);
 await search.fill('ка');await expect(page.getByRole('listbox',{name:'Підказки запчастин'})).toBeVisible();await expect(page.getByRole('option',{name:/Капот/})).toHaveCount(1);await expect(page.getByRole('option',{name:/Кардан/})).toHaveCount(1);
 await expect(row('Капот')).toHaveCount(1);await expect(row('Капот BMW')).toHaveCount(0);await expect(row('Капот потенційний')).toHaveCount(0);
 await search.fill('КА');await expect(row('Кардан')).toBeVisible();await search.fill('OEM-123');await expect(row('Кардан')).toHaveCount(0);await expect(row('Капот')).toBeVisible();await search.fill('ART-123');await expect(row('Капот')).toBeVisible();
 await search.fill('Немає такого');await expect(page.getByRole('region',{name:'Результати пошуку'}).getByRole('heading',{name:'Нічого не знайдено',exact:true})).toBeVisible();await search.fill('ка');await search.press('Escape');
 let modal=await action('Змінити ціну');await expect(modal.getByText(/^Поточна ціна:/)).toBeVisible();await modal.getByLabel('Моя ціна',{exact:true}).fill('125.67');await modal.getByLabel('Валюта моєї ціни',{exact:true}).selectOption('USD');await modal.getByRole('button',{name:'Зберегти мою ціну',exact:true}).click();await expect(modal).not.toBeVisible();await expect(row('Капот')).toContainText(/125[.,]67/);await expect(row('Капот')).toContainText('USD');
 await page.reload();await expect(row('Капот')).toContainText('USD');modal=await action('Відкрити картку');await expect(modal).toHaveAccessibleName('Капот');
 const price=await action('Змінити ціну',false,modal);await expect(price.getByText(/^Поточна ціна:/)).toBeVisible();await price.getByLabel('Моя ціна',{exact:true}).fill('777.89');await price.getByLabel('Валюта моєї ціни',{exact:true}).selectOption('UAH');await price.getByRole('button',{name:'Зберегти мою ціну',exact:true}).click();await expect(price).not.toBeVisible();await expect(row('Капот')).toContainText(/777[.,]89/);await expect(row('Капот')).toContainText('UAH');
 // Commit followed by lost response; reload and replay the exact checkout key,
 // including when the last unit disappears from search. No automatic retry.
 const saleKeys=[];
 for(const quantity of [2,0]){
  await searchPage();modal=await action('Оформити замовлення');await modal.getByRole('textbox',{name:'Телефон покупця',exact:true}).fill(buyer.phone);await modal.getByRole('button',{name:/Seller Buyer QA/}).click();await modal.getByRole('combobox',{name:'Дія з замовленням'}).selectOption('sell');await modal.getByRole('checkbox',{name:'Підтверджую продаж і списання всіх позицій',exact:true}).check();
  const pattern='**/api/v1/orders/checkout';let resolveLost,committed,requests=0;const lost=new Promise(resolve=>{resolveLost=resolve;});
  await page.route(pattern,async route=>{requests++;saleKeys.push(route.request().postDataJSON().request_key);const response=await route.fetch();assert.equal(response.status(),201,await response.text());committed=await response.json();await route.abort('failed');resolveLost();});
  await expect(modal.getByRole('button',{name:'Підтвердити продаж',exact:true})).toBeEnabled();
  await modal.getByRole('button',{name:'Підтвердити продаж',exact:true}).evaluate(button=>{button.click();button.click();});await lost;await expect(modal.getByRole('alert')).toBeVisible();assert.equal(requests,1,'Rapid confirmation sends one checkout');await page.unroute(pattern);
  assert.equal((await get('/parts/'+hood.id)).quantity,quantity);
  await page.reload();await page.goto(origin+'/orders');const replay=page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith('/orders/checkout'));await page.getByRole('button',{name:'Перевірити результат запиту',exact:true}).click();const request=await replay;assert.equal(request.postDataJSON().request_key,saleKeys.at(-1));await expect(page.getByRole('heading',{name:'Замовлення №'+committed.number,exact:true})).toBeVisible();assert.equal((await get('/parts/'+hood.id)).quantity,quantity);
  if(quantity===2){
   await searchPage();modal=await action('Перемістити',true);await modal.getByLabel('Нове місце',{exact:true}).fill('Полиця B');await expect(modal.getByLabel('Примітка (необов’язково)',{exact:true})).not.toHaveAttribute('required');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();
   modal=await action('Списати',true);await modal.getByLabel('Причина списання',{exact:true}).fill('Пошкоджено при огляді');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();const state=await get('/parts/'+hood.id);assert.equal(state.quantity,1);assert.equal(state.location,'Полиця B');assert.equal(state.selling_price,'777.89');assert.equal(state.currency,'UAH');
   const audit=await get(`/audit?part_id=${hood.id}&limit=100`);for(const type of ['sale','write_off','transfer'])assert.equal(audit.items.filter(r=>r.type===type).length,1);
  }
 }
 assert.equal((await get(`/audit?part_id=${hood.id}&type=sale`)).total,2);assert.equal(new Set(saleKeys).size,2);
 await page.goto(origin+'/search');await expect(row('Капот')).toHaveCount(0);
 // Two identical, deliberate receipts must have different request keys.
 await page.goto(origin+`/inventory?vehicle_id=${volvo.id}`);await page.getByRole('checkbox',{name:'Тільки в наявності',exact:true}).uncheck();
 const receiptKeys=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/parts/'+hood.id+'/operations'))receiptKeys.push(r.postDataJSON().request_key);});
 for(const quantity of [1,2]){modal=await action('Додати кількість',true);await modal.getByLabel('Кількість',{exact:true}).fill('1');await modal.getByLabel('Примітка (необов’язково)',{exact:true}).fill('Нове надходження');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();assert.equal((await get('/parts/'+hood.id)).quantity,quantity);}
 assert.equal(new Set(receiptKeys).size,2);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:`test-results/sales-${viewport.width}.png`,fullPage:true});assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);await context.close();console.log(`PASS seller Unicode/OEM/article, prices, card/list, lost-response checkout and last-unit replay, writeoff/transfer/audit, fresh receipt keys ${viewport.width}`);
}}finally{await browser.close();}
