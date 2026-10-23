import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local disposable database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[],unexpected=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))unexpected.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'UX511',email:`ux511-${Date.now()}@example.test`,password:'local-ux511-test-password'}});assert(auth.ok());const user=await auth.json(),headers={'X-CSRF-Token':user.csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const volvo=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),bmw=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2012});
 const part=await post('/parts',{name:'Капот UX511',vehicle_id:volvo.id,selling_price:'123.45',oem_number:'OEM511',description:'Опис деталі',location:'A1'});await post(`/parts/${part.id}/operations`,{type:'receipt',quantity:3,reason:'Local test receipt'});
 const auditBefore=(await(await context.request.get(origin+'/api/v1/audit')).json()).total;
 // Simulate an old UX5 preference: an implicit last donor must not count as explicit consent.
 await page.goto(origin+'/');await page.evaluate(({id,donor})=>localStorage.setItem('warehouse-inventory-view:'+id,JSON.stringify({mode:'general',donor})),{id:user.user.id,donor:volvo.id});
 await page.goto(origin+`/inventory?vehicle_id=${volvo.id}`);await page.getByRole('button',{name:'За автомобілями',exact:true}).click();
 const cards=page.getByRole('region',{name:'Автомобілі на складі'});await expect(cards.locator('article')).toHaveCount(2);await expect(page.locator('.donor-stock-tree')).toHaveCount(0);await expect(page.locator('.donor-potential')).toHaveCount(0);
 for(const name of ['Режим складу','Розділ складу']){const nav=page.getByRole('navigation',{name,exact:true});assert(await nav.evaluate(el=>{const a=el.children[0].getBoundingClientRect(),b=el.children[1].getBoundingClientRect();return Math.abs(a.top-b.top)<2&&el.getBoundingClientRect().height<55&&el.scrollWidth<=el.clientWidth;}),'Navigation must remain on one compact row');}
 await page.screenshot({path:`test-results/ux511-donors-${viewport.width}.png`,fullPage:true});
 await cards.getByRole('button',{name:/Відкрити склад Volvo XC90/}).click();await expect(page.getByRole('heading',{name:'Volvo XC90 · 2010 · №1',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Усі автомобілі',exact:true}).click();await expect(cards.locator('article')).toHaveCount(2);
 await page.reload();await expect(cards.locator('article')).toHaveCount(2);
 await cards.getByRole('button',{name:/Відкрити склад BMW X3/}).click();await page.goto(origin+'/inventory');await expect(cards.locator('article')).toHaveCount(2);
 await cards.getByRole('button',{name:/Відкрити склад Volvo XC90/}).click();await page.getByRole('checkbox',{name:'Запам’ятати цей автомобіль',exact:true}).check();await page.goto(origin+'/');await page.goto(origin+'/inventory');await expect(page.getByLabel('Автомобіль складу',{exact:true})).toHaveValue(volvo.id);
 await page.locator('.donor-stock-tree summary').filter({hasText:'Без категорії'}).click();await page.getByRole('searchbox',{name:'Пошук запчастин',exact:true}).fill('OEM511');await page.locator('.donor-stock-tree').getByRole('button',{name:'Капот UX511',exact:true}).click();const card=page.getByRole('dialog',{name:'Капот UX511',exact:true});
 assert(await card.evaluate(el=>{const r=el.getBoundingClientRect();return r.height<500&&r.top>=0&&r.bottom<=innerHeight&&el.scrollWidth<=el.clientWidth;}),'Part card must be compact and bounded');
 const metrics=card.locator('.stock-part-metrics');await expect(metrics).toContainText('У наявності: 3');await expect(metrics).toContainText('123,45');await expect(metrics).toContainText('A1');
 for(const name of ['Продати','Редагувати','Зарезервувати','Перемістити','Списати','Історія'])await expect(card.getByRole('button',{name,exact:true})).toBeVisible();
 await page.screenshot({path:`test-results/ux511-card-${viewport.width}.png`});await card.getByRole('button',{name:'Закрити',exact:true}).click();
 await page.getByRole('button',{name:'Історія операцій',exact:true}).click();const history=page.getByRole('region',{name:'Історія операцій',exact:true});await history.getByLabel('Тип історії',{exact:true}).selectOption('receipt');await expect(history.locator('.stock-history-event')).toHaveCount(1);
 await page.getByRole('button',{name:'Загальний склад',exact:true}).click();await expect(page.getByRole('button',{name:'Запчастини',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('heading',{name:'Запчастини та залишки',exact:true})).toBeVisible();await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await expect(page.getByLabel('Автомобіль складу',{exact:true})).toHaveValue(volvo.id);
 await page.getByRole('checkbox',{name:'Запам’ятати цей автомобіль',exact:true}).uncheck();await page.getByRole('button',{name:'Загальний склад',exact:true}).click();await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await expect(cards.locator('article')).toHaveCount(2);
 assert.equal((await(await context.request.get(origin+'/api/v1/audit')).json()).total,auditBefore,'Navigation must not create stock or audit mutations');assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
 await context.close();console.log(`PASS UX511 donor-list-first, explicit remember, return/reset, compact navigation/detail, scoped search/history, read-only switching ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
