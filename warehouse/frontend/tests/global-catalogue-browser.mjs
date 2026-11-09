// Synthetic presentation checks only. Never proof of actual MySQL coverage.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local harness only');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try {for(const width of [1440,390]){
 const context=await browser.newContext({baseURL:'http://127.0.0.1:5227',viewport:{width,height:900}});
 const signup=await context.request.post('/api/v1/auth/register',{data:{name:'Synthetic Global QA',email:`global-${crypto.randomUUID()}@example.test`,password:'synthetic-local-password-only'}});
 assert.equal(signup.status(),201);const auth=await signup.json();
 const created=await context.request.post('/api/v1/vehicles',{headers:{'X-CSRF-Token':auth.csrf_token},data:{manufacturer:'Volvo',model:'XC90 II',year:2018}});
 assert.equal(created.status(),201);const vehicle=await created.json();vehicle.dismantling_v3={global_selection:{car_id:107555}};
 const page=await context.newPage(),errors=[],forbidden=[];let saved=false;
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/plan-parts|unified-catalogue\/base/.test(r.url()))forbidden.push(r.url())});
 const categories=Array.from({length:113},(_,i)=>({product_id:i+1,name_source:`Synthetic part ${i+1}`,name_uk:`Тестова деталь ${i+1}`,category_path:['Двигун','Фільтри','Тест'],article_count:2,kind:'review'}));
 await page.route('**/api/v1/vehicles/catalogue-directory/available?*',r=>r.fulfill({json:{items:[{manufacturer:'Volvo',model:'XC90 II',model_id:13084,generation:null,source_modification_id:107555,modification:{description:'T6 AWD (fixture)'},type_count:113,article_count:226,oem_links:1,coverage:'partial'}],next_after:null}}));
 await page.route('**/api/v1/vehicles/catalogue-directory/vehicles',r=>r.fulfill({status:201,json:vehicle}));
 await page.route(`**/api/v1/vehicles/${vehicle.id}`,r=>r.fulfill({json:vehicle}));
 await page.route(`**/api/v1/vehicles/${vehicle.id}/global-dismantling`,r=>{if(r.request().method()==='POST'){saved=true;return r.fulfill({json:{saved:true,created:113}})}return r.fulfill({json:{selection:{car_id:107555},saved:saved?{payload:{coverage:'partial',categories}}:null,keys:Object.fromEntries(categories.map(p=>[p.product_id,'catalogue:'+p.product_id]))}})});
 await page.route(`**/api/v1/vehicles/${vehicle.id}/unified-catalogue/articles?*`,r=>r.fulfill({json:{articles:[{art_id:1,article_nr:'FIXTURE-ARTICLE',brand:'Fixture maker',oem_numbers:['FIXTURE-OEM']}]}}));
 await page.goto('/vehicles');await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
 const form=page.getByRole('dialog');await form.getByLabel('Марка',{exact:true}).selectOption('Volvo');await form.getByLabel('Модель',{exact:true}).selectOption('13084');await form.getByLabel('Покоління',{exact:true}).selectOption('unknown');await form.getByLabel('Модифікація',{exact:true}).selectOption('107555');await form.getByLabel('Рік конкретного автомобіля').fill('2018');await form.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
 const flow=page.getByRole('region',{name:'Розбір автомобіля',exact:true});await flow.getByRole('button',{name:'Розібрати автомобіль',exact:true}).click();await expect(flow).toContainText('113 типів');await flow.getByRole('button',{name:'Переглянути',exact:true}).first().click();await expect(flow).toContainText('FIXTURE-OEM');
 await page.reload();await expect(page.getByRole('region',{name:'Розбір автомобіля',exact:true})).toContainText('113 типів');
 assert.deepEqual(forbidden,[]);assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 fs.mkdirSync('/tmp/carpot-global-stage1',{recursive:true});await page.screenshot({path:`/tmp/carpot-global-stage1/${width}.png`,fullPage:true});console.log(`${width}: PASS`);await context.close();
}}finally{await browser.close()}
