// Isolated authenticated UI regression. No staging or production traffic.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit local test guard required');
const output=process.env.UX_V2_OUTPUT||'/tmp/corporate-ux-v2';fs.mkdirSync(output,{recursive:true});
const browser=await chromium.launch({args:['--no-sandbox']});
try{
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5251',viewport:{width:1440,height:1000}});
 const reg=await c.request.post('/api/v1/auth/register',{data:{name:'Corporate UX QA',email:`ux-v2-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(reg.status(),201,await reg.text());const auth=await reg.json();
 const post=async(path,data)=>{const r=await c.request.post('/api/v1'+path,{data,headers:{'X-CSRF-Token':auth.csrf_token}});assert.ok(r.ok(),await r.text());return r.json()};
 const v=await post('/vehicles',{manufacturer:'Renault',model:'ZOE',year:2020});
 const partRows=[];
 for(const name of ['UX QA starter','UX QA filter']){const p=await post('/parts',{name,vehicle_id:v.id,selling_price:'100.00',currency:'UAH'});partRows.push(p);await post('/parts/'+p.id+'/operations',{type:'receipt',quantity:2,reason:'Isolated UX QA'});}
 const page=await c.newPage();page.setDefaultTimeout(20000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/inventory');await expect(page.getByRole('navigation',{name:'Категорії складу'})).toBeVisible();
 await expect(page.locator('.stock-v2-main')).toBeVisible();
 const menu=page.locator('#warehouse-sidebar'),main=page.locator('.main');
 const aligned=async()=>{const a=await menu.boundingBox(),b=await main.boundingBox();assert.ok(Math.abs(a.x+a.width-b.x)<2,'No sidebar overlay');};
 await page.getByRole('button',{name:'Увімкнути автоматичне меню',exact:true}).click();
 await page.mouse.move(1100,600);await expect.poll(async()=>Math.round((await menu.boundingBox()).width)).toBe(78);await aligned();
 await menu.hover({position:{x:25,y:100}});await expect.poll(async()=>Math.round((await menu.boundingBox()).width)).toBe(240);await aligned();
 await page.mouse.move(1100,600);await expect.poll(async()=>Math.round((await menu.boundingBox()).width)).toBe(78);await aligned();
 await page.getByRole('button',{name:'Закріпити бічне меню',exact:true}).click();
 await page.mouse.move(1100,600);await aligned();
 await page.getByRole('button',{name:'Дії UX QA starter',exact:true}).click();await page.getByRole('menuitem',{name:'Оформити замовлення',exact:true}).click();
 const dialog=page.getByRole('dialog').last();await expect(dialog.getByRole('heading',{name:'Оформити замовлення',exact:true})).toBeVisible();
 const add=dialog.getByRole('button',{name:'+ Додати товар',exact:true});await add.click();const picker=dialog.locator('.r4-picker');await expect(picker).toBeVisible();assert.equal(await add.evaluate(el=>el.nextElementSibling?.classList.contains('r4-picker')),true);
 await picker.getByRole('button',{name:/UX QA filter/}).click();await expect(picker).toHaveCount(0);await expect(dialog.locator('.order-line-editor')).toHaveCount(2);
 await page.screenshot({path:output+'/checkout.png',animations:'disabled'});await page.keyboard.press('Escape');
 await page.goto('/settings?section=general');await expect(page.getByRole('region',{name:'Оформлення'})).toBeVisible();
 for(const style of ['emerald','onyx','gold']){await page.locator('.theme-switch select').selectOption(style);await expect(page.locator('html')).toHaveAttribute('data-night-style',style);await page.reload();await expect(page.locator('html')).toHaveAttribute('data-night-style',style);await expect(page.locator('html')).toHaveAttribute('data-theme','dark');}
 await page.goto('/settings?section=payments');await expect(page.getByRole('region',{name:'Оплати'})).toContainText('недоступне');
 for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.goto('/inventory');await expect(page.locator('.stock-v2-main')).toBeVisible();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Inventory overflow '+width);await page.screenshot({path:output+'/inventory-'+width+'.png',animations:'disabled'});}

 // Actual orders/buyer identity on the disposable PostgreSQL fixture.
 const buyer1=await post('/buyers',{name:'QA Покупець Один',phone:'0501112233'});
 const buyer2=await post('/buyers',{name:'QA Покупець Два',phone:'0674445566'});
 const order1=await post('/orders',{request_key:crypto.randomUUID(),buyer_id:buyer1.id,lines:[{part_id:partRows[0].id,quantity:1,unit_price:'100.00',currency:'UAH'}]});
 const order2=await post('/orders',{request_key:crypto.randomUUID(),buyer_id:buyer2.id,contact_phone:buyer1.phone,lines:[{part_id:partRows[1].id,quantity:1,unit_price:'100.00',currency:'UAH'}]});
 await post('/orders/'+order2.id+'/reserve',{request_key:crypto.randomUUID()});
 await page.setViewportSize({width:1440,height:1000});await page.goto('/sales?tab=orders');
 const kpi=(label)=>page.locator('.sc-kpi').filter({hasText:label}).locator('strong');
 await expect(kpi('Нові замовлення')).toHaveText('1');await expect(kpi('Зарезервовано')).toHaveText('1');await expect(kpi('Продажі сьогодні')).toHaveText('0');
 await page.locator('.sc-journal tbody tr').filter({hasText:'Замовлення · №'+order1.number}).getByRole('button',{name:'Переглянути',exact:true}).click();
 const inspector=page.getByRole('complementary',{name:'Картка операції'});
 await expect(inspector.getByRole('heading',{name:'Замовлення №'+order1.number,exact:true})).toBeVisible();
 await expect(inspector).toContainText('UX QA starter');
 const confirm=async(button,title)=>{await inspector.getByRole('button',{name:button,exact:true}).click();await page.getByRole('dialog',{name:title,exact:true}).getByRole('button',{name:'Підтвердити',exact:true}).click();};
 await confirm('Зарезервувати','Зарезервувати запчастини?');
 await expect(kpi('Зарезервовано')).toHaveText('2');
 await confirm('Підтвердити продаж','Підтвердити продаж?');
 await expect(inspector.getByText('Продаж проведено',{exact:true})).toBeVisible();
 await expect(kpi('Продажі сьогодні')).toHaveText('1');
 const stock=async()=>{const response=await c.request.get('/api/v1/parts/'+partRows[0].id,{headers:{'X-Warehouse-Client':'5'}});assert.ok(response.ok(),await response.text());return response.json();};
 const afterSale=await stock();assert.equal(afterSale.quantity,1);assert.equal(afterSale.reserved_quantity,0);
 await confirm('Підтвердити передачу покупцеві','Покупець отримав замовлення?');
 await expect(inspector.getByText('Завершено',{exact:true})).toBeVisible();
 const afterReceipt=await stock();assert.equal(afterReceipt.quantity,afterSale.quantity);assert.equal(afterReceipt.reserved_quantity,afterSale.reserved_quantity);
 await page.screenshot({path:output+'/sales-order-inspector.png',animations:'disabled'});
 await page.getByRole('button',{name:'Покупці',exact:true}).click();
 await page.getByRole('textbox',{name:'Пошук покупця за телефоном'}).fill('0501112233');
 await page.getByRole('button',{name:/QA Покупець Один/}).click();
 const customer=page.getByRole('complementary',{name:'Картка покупця'});
 await expect(customer.getByRole('link',{name:new RegExp('Замовлення №'+order1.number+'(?: |$)')})).toBeVisible();
 await expect(customer.locator('.sc-buyer-order')).toHaveCount(1);
 await expect(customer).not.toContainText('Замовлення №'+order2.number);
 await page.screenshot({path:output+'/sales-buyers.png',animations:'disabled'});
 for(const width of [1440,1920,390]){
  await page.setViewportSize({width,height:1000});await page.goto('/sales?tab=orders');
  await expect(kpi('Продажі сьогодні')).toHaveText('1');await expect(page.locator('.sc-journal tbody tr').first()).toBeVisible();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Sales overflow '+width);
  await page.screenshot({path:output+'/sales-'+width+'.png',animations:'disabled'});
  await page.getByRole('button',{name:'Покупці',exact:true}).click();
  await expect(page.getByRole('button',{name:/QA Покупець Один/})).toBeVisible();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Buyers overflow '+width);
 }

 for(const width of [1440,1920,390]){
  await page.setViewportSize({width,height:1000});await page.goto('/statistics');
  await expect(page.getByRole('heading',{name:'Статистика складу',exact:true})).toBeVisible();
  await expect(page.locator('.stats-finance')).toContainText('Не визначено');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Statistics overflow '+width);
  await page.screenshot({path:output+'/statistics-'+width+'.png',animations:'disabled'});
 }
 await page.goto('/settings?section=general');
 const settings=page.getByRole('navigation',{name:'Розділ налаштувань'});
 await expect(settings.getByRole('link',{name:'Загальні'})).toHaveAttribute('aria-current','page');
 await settings.getByRole('link',{name:'Оплати'}).click();
 await expect(settings.getByRole('link',{name:'Оплати'})).toHaveAttribute('aria-current','page');
 await expect(page.getByRole('region',{name:'Оплати'})).toContainText('недоступне');
 assert.deepEqual(errors,[]);console.log('Corporate UX: real-auth stock, aligned sidebar, inline picker, persisted palettes, responsive widths, sales lifecycle and exact buyer history PASS');
 await c.close();
}finally{await browser.close();}
