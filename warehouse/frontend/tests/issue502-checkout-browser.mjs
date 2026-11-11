// Real authentication, inventory, checkout and PostgreSQL; synthetic local account only.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local test flag required');
const dir=process.env.ISSUE502_OUTPUT||'/tmp/issue502-checkout';fs.mkdirSync(dir,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 for(const count of [1,2]){
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5251',viewport:{width:1440,height:1000}});
 const reg=await c.request.post('/api/v1/auth/register',{data:{name:'Checkout QA',email:`checkout502-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(reg.status(),201);const auth=await reg.json();
 const post=async(path,data)=>{const r=await c.request.post('/api/v1'+path,{data,headers:{'X-CSRF-Token':auth.csrf_token}});assert.ok(r.ok(),await r.text());return r.json()};
 const v=await post('/vehicles',{manufacturer:'Renault',model:'ZOE — local checkout test',year:2020});
 const p=await post('/parts',{name:'Checkout502 detail',vehicle_id:v.id,selling_price:'100.00',currency:'UAH'});
 await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:2,reason:'Isolated local QA'});
 let second;if(count===2){second=await post('/parts',{name:'Second502 detail',vehicle_id:v.id,selling_price:'12.00',currency:'USD'});await post(`/parts/${second.id}/operations`,{type:'receipt',quantity:1,reason:'Isolated local QA'});}
 const b=await post('/buyers',{name:'Synthetic buyer',phone:'0501112233'});
 const page=await c.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/inventory');
 await page.getByRole('button',{name:'Дії Checkout502 detail',exact:true}).click();
 await page.getByRole('menuitem',{name:'Оформити замовлення',exact:true}).click();
 const dialog=page.getByRole('dialog').last();await expect(dialog.getByRole('heading',{name:'Оформити замовлення',exact:true})).toBeVisible();
 await expect(dialog.getByRole('searchbox',{name:'Пошук позицій замовлення'})).not.toBeVisible();
 await dialog.getByRole('button',{name:'+ Додати товар',exact:true}).click();await expect(dialog.getByRole('searchbox',{name:'Пошук позицій замовлення'})).toBeVisible();
 if(second){await dialog.getByRole('button',{name:/Second502 detail/}).click();await dialog.getByLabel('Погоджена ціна Second502 detail',{exact:true}).fill('15.25');}
 await dialog.getByRole('button',{name:'+ Додати товар',exact:true}).click();
 await expect(dialog.locator('.order-line-editor').first()).toContainText('Renault ZOE');
 await dialog.getByLabel('Телефон покупця',{exact:true}).fill('0501112233');await dialog.getByRole('button',{name:/Synthetic buyer/}).click();
 await dialog.getByLabel('Дія з замовленням',{exact:true}).selectOption('sell');await dialog.getByLabel('Підтверджую продаж і списання всіх позицій',{exact:true}).check();
 for(const width of [1440,390]){await page.setViewportSize({width,height:1000});const approval=dialog.getByLabel('Підтверджую продаж і списання всіх позицій',{exact:true});await approval.uncheck();await approval.check();assert.ok((await approval.boundingBox()).width<=22,'Compact usable confirmation checkbox');await expect(dialog.getByRole('button',{name:'Підтвердити продаж',exact:true})).toBeEnabled();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({animations:'disabled',path:`${dir}/checkout-${count}-${width}.png`});}
 const response=page.waitForResponse(r=>r.url().endsWith('/orders/checkout')&&r.request().method()==='POST');await dialog.getByRole('button',{name:'Підтвердити продаж',exact:true}).click();const result=await response;assert.equal(result.status(),201,await result.text());const order=await result.json();assert.ok(order.sold_at);
 await expect(page.getByRole('heading',{name:`Замовлення №${order.number}`})).toBeVisible();await page.reload();await expect(page.getByRole('heading',{name:`Замовлення №${order.number}`})).toBeVisible();
 await page.goto('/sales?tab=orders');await page.getByRole('button',{name:'Переглянути',exact:true}).first().click();await expect(page.getByRole('complementary',{name:'Картка операції'})).toContainText('Synthetic buyer');
 for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Sales overflow ${theme}/${width}`);await page.screenshot({animations:'disabled',path:`${dir}/sales-${count}-${theme==='День'?'light':'dark'}-${width}.png`});}
 const stock=await c.request.get(`/api/v1/parts/${p.id}`,{headers:{'X-Warehouse-Client':'5'}});assert.equal((await stock.json()).quantity,1);assert.deepEqual(errors,[]);
 fs.writeFileSync(`${dir}/report-${count}.json`,JSON.stringify({target:'LOCAL_AUTHENTICATED_POSTGRES_TEST_RECORDS',checkout:true,onDemandSearch:true,sale:true,quantityAfterReload:1,errors},null,2));console.log(`Local real-auth checkout ${count} lines, 1440/390, price edit, sale, reload and ledger: PASS`);await c.close();}
}finally{await browser.close()}
