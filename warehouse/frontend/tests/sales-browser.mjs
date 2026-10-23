// Real local disposable API/PostgreSQL, production bundle, never provider calls.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local test database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,extraHTTPHeaders:{"X-Warehouse-Client":"5"}}),page=await context.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))paid.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Local seller test',email:`seller-${viewport.width}-${Date.now()}@example.test`,password:'offline-seller-long-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const volvo=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),bmw=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2012});
 async function stock(vehicle,name,quantity,extra={}){const p=await post('/parts',{vehicle_id:vehicle.id,name,...extra});if(quantity)await post(`/parts/${p.id}/operations`,{type:'receipt',quantity,reason:'Previous local stock'});return p;}
 const hood=await stock(volvo,'Капот',3,{selling_price:'123.45',oem_number:'OEM-123',article_number:'ART-123',location:'Полиця A'});
 await stock(volvo,'Кардан',1,{selling_price:'45.67',currency:'USD'});await stock(volvo,'Капот потенційний',0);await stock(bmw,'Капот BMW',1);
 await page.goto(origin+'/');await expect(page.getByRole('heading',{name:'Пошук запчастин',exact:true})).toBeVisible();
 await page.getByLabel('Марка пошуку',{exact:true}).selectOption('Volvo');await page.getByLabel('Модель пошуку',{exact:true}).selectOption('XC90');await page.getByLabel('Автомобіль пошуку',{exact:true}).selectOption(volvo.id);
 const search=page.getByRole('combobox',{name:'Пошук запчастин',exact:true});await search.fill('ка');
 await expect(page.getByRole('listbox',{name:'Підказки запчастин'})).toBeVisible();await expect(page.getByRole('option',{name:/Капот/})).toHaveCount(1);await expect(page.getByRole('option',{name:/Кардан/})).toHaveCount(1);
 const area=page.getByRole('region',{name:'Результати пошуку'}),row=name=>area.locator(viewport.width>800?'tbody tr':'.seller-card').filter({has:page.getByRole('button',{name,exact:true})});
 await expect(row('Капот')).toHaveCount(1);await expect(row('Капот BMW')).toHaveCount(0);await expect(row('Капот потенційний')).toHaveCount(0);
 await search.fill('КА');await expect(row('Кардан')).toBeVisible();await search.fill('OEM-123');await expect(row('Кардан')).toHaveCount(0);await expect(row('Капот')).toBeVisible();await search.fill('ART-123');await expect(row('Капот')).toBeVisible();
 await search.fill('Немає такого');await expect(area.getByRole('heading',{name:'Нічого не знайдено',exact:true})).toBeVisible();await search.fill('ка');await search.press('Escape');
 await row('Капот').getByRole('button',{name:'Ціна Капот',exact:true}).click();let modal=page.locator('dialog[open]').last();await modal.getByLabel('Сума',{exact:true}).fill('125.67');await modal.getByLabel('Валюта',{exact:true}).selectOption('USD');await modal.getByRole('button',{name:'Зберегти',exact:true}).click();
 await expect(row('Капот').getByRole('button',{name:'Ціна Капот',exact:true})).toContainText('125,67');await expect(row('Капот')).toContainText('USD');
 await page.reload();await expect(row('Капот')).toContainText('USD');await row('Капот').getByRole('button',{name:'Капот',exact:true}).click();
 modal=page.getByRole('dialog',{name:'Капот',exact:true});await modal.getByRole('button',{name:'Ціна Капот',exact:true}).click();let price=page.getByRole('dialog',{name:'Ціна запчастини',exact:true});await price.getByLabel('Сума',{exact:true}).fill('777.89');await price.getByLabel('Валюта',{exact:true}).selectOption('UAH');await price.getByRole('button',{name:'Зберегти',exact:true}).click();
 await expect(modal.getByRole('button',{name:'Ціна Капот',exact:true})).toContainText('777,89');await modal.getByRole('button',{name:'Закрити',exact:true}).click();await expect(row('Капот')).toContainText('777,89');await expect(row('Капот')).toContainText('UAH');
 // Simulate server commit followed by a lost response; retry after a reload.
 let intercepted=0;const keys=[];const pattern='**/api/v1/parts/'+hood.id+'/operations';
 await page.route(pattern,async route=>{keys.push(route.request().postDataJSON().request_key);intercepted++;await route.fetch();await route.abort('failed');});
 await row('Капот').getByRole('button',{name:'Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await expect(modal.getByLabel('Примітка (необов’язково)',{exact:true})).not.toHaveAttribute('required');await modal.getByRole('button',{name:'Підтвердити',exact:true}).evaluate(button=>{button.click();button.click();});await expect(modal.getByRole('alert')).toBeVisible();assert.equal(intercepted,1,'rapid repeated confirmation must send only one sale request');
 await page.unroute(pattern);await modal.getByRole('button',{name:'Закрити',exact:true}).click();await page.reload();await row('Капот').getByRole('button',{name:'Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await expect(modal.getByRole('alert')).toContainText('непідтверджений запит');
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/parts/'+hood.id+'/operations'))keys.push(r.postDataJSON().request_key);});
 await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();assert.equal(keys[0],keys[1]);
 let state=await (await context.request.get(origin+'/api/v1/parts/'+hood.id)).json();assert.equal(state.quantity,2);
 async function action(name){await row('Капот').getByText('⋯',{exact:true}).click();await row('Капот').getByRole('button',{name,exact:true}).click();return page.locator('dialog[open]').last();}
 modal=await action('Перемістити');await modal.getByLabel('Нове місце',{exact:true}).fill('Полиця B');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(row('Капот')).toContainText('Полиця B');
 modal=await action('Списати');await modal.getByLabel('Причина списання',{exact:true}).fill('Пошкоджено при огляді');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();
 state=await (await context.request.get(origin+'/api/v1/parts/'+hood.id)).json();assert.equal(state.quantity,1);assert.equal(state.location,'Полиця B');assert.equal(state.selling_price,'777.89');assert.equal(state.currency,'UAH');
 const audit=await (await context.request.get(origin+`/api/v1/audit?part_id=${hood.id}&limit=100`)).json();assert.equal(audit.items.filter(r=>r.type==='sale').length,1);assert.equal(audit.items.filter(r=>r.type==='write_off').length,1);assert.equal(audit.items.filter(r=>r.type==='transfer').length,1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`test-results/sales-${viewport.width}.png`,fullPage:true});
 // Lost response for the LAST unit: the row is gone, so resume via the pending banner.
 await page.route(pattern,async route=>{await route.fetch();await route.abort('failed');});
 await row('Капот').getByRole('button',{name:'Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal.getByRole('alert')).toBeVisible();await modal.getByRole('button',{name:'Закрити',exact:true}).click();await page.unroute(pattern);await page.reload();
 await expect(row('Капот')).toHaveCount(0);await page.getByRole('button',{name:'Перевірити: Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await expect(modal.getByRole('alert')).toContainText('непідтверджений запит');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();
 await expect(page.getByRole('button',{name:'Перевірити: Продати',exact:true})).toHaveCount(0);
 assert.equal((await (await context.request.get(origin+'/api/v1/parts/'+hood.id)).json()).quantity,0);
 const finalAudit=await (await context.request.get(origin+`/api/v1/audit?part_id=${hood.id}&type=sale`)).json();assert.equal(finalAudit.total,2);
 // Two deliberate identical receipts in the retained advanced card must get NEW keys.
 await page.goto(origin+`/inventory?vehicle_id=${volvo.id}`);await page.getByText('Додаткові фільтри',{exact:true}).click();await page.getByRole('checkbox',{name:'Показати також без залишку',exact:true}).check();await row('Капот').getByRole('button',{name:'Капот',exact:true}).click();
 const card=page.getByRole('dialog',{name:'Капот',exact:true});await card.getByText('Докладніше',{exact:true}).click();
 for(const quantity of [1,2]){await card.getByLabel('Кількість').fill('1');await card.getByLabel('Причина операції').fill('Нове надходження');await card.getByRole('button',{name:'Провести операцію',exact:true}).click();await expect(card.locator('.stock-summary>span').filter({hasText:'Залишок'})).toContainText(String(quantity));}
 assert.equal((await (await context.request.get(origin+'/api/v1/parts/'+hood.id)).json()).quantity,2);
 assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
 await context.close();console.log(`PASS seller search, Unicode/OEM/article, UAH/USD, card/list refresh, lost-response sale replay, writeoff/transfer/audit ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
