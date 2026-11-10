// Offline decoder fixtures with real local PostgreSQL persistence; never live VIN evidence.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local test only');
fs.mkdirSync('/tmp/vin-create-qa',{recursive:true});
const vins=['YV4L12RK6N1970668','YV4A22PK2G1092943'];
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5231',viewport:{width:1440,height:1000}});
 const signup=await c.request.post('/api/v1/auth/register',{data:{name:'VIN Offline QA',email:`vin-${crypto.randomUUID()}@example.test`,password:'local-synthetic-test-password'}});assert.equal(signup.status(),201,await signup.text());
 const page=await c.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/v1/vehicles/vin/decode?**',route=>{
  const vin=new URL(route.request().url()).searchParams.get('vin');assert.ok(vins.includes(vin));
  const vehicle=vin===vins[0]?{manufacturer:'Volvo',model:'OFFLINE TEST A',year:2020,drive_type:'Повний (AWD)',engine:'Fixture engine',engine_code:'TEST-ENGINE',engine_displacement_l:'2',transmission:'Автоматична',body_class:'Fixture SUV',engine_power_kw:'123',doors:'5',generation:'TEST GENERATION',transmission_code:'TEST-AT'}:{manufacturer:'Volvo',model:'OFFLINE TEST B',year:2020};
  return route.fulfill({json:{vin,source:'OFFLINE TEST FIXTURE',vehicle,available_fields:Object.keys(vehicle),requires_review:true,observed_at:'2026-11-11T00:00:00Z',message:'Синтетичні дані, не live VIN.'}});
 });
 for(const [i,vin] of vins.entries()){
  await page.goto('/vehicles');await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  const form=page.getByRole('region',{name:'Додавання автомобіля за VIN'});
  await form.getByLabel('VIN',{exact:true}).fill(vin);await form.getByRole('button',{name:'Визначити автомобіль',exact:true}).click();
  await expect(form.getByLabel('Модель',{exact:true})).toHaveValue(`OFFLINE TEST ${i===0?'A':'B'}`);
  if(i===1){await form.getByLabel('Код двигуна',{exact:true}).fill('MANUAL-CODE');await form.getByLabel('Тип кузова',{exact:true}).fill('Manual body');}
  await form.getByLabel('Характеристики перевірено, підтверджую додавання').check();
  const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/v1/vehicles');
  await form.getByRole('button',{name:'Додати автомобіль',exact:true}).click();const saved=await response;assert.equal(saved.status(),201,await saved.text());const row=await saved.json();
  await expect(form).toHaveCount(0);await page.reload();
  const persisted=await (await c.request.get('/api/v1/vehicles/'+row.id)).json();assert.equal(persisted.vin,vin);assert.equal(persisted.vin_details.source,'OFFLINE TEST FIXTURE');
  if(i===0){assert.equal(persisted.drive_type,'AWD');assert.equal(persisted.vin_details.characteristics.engine_power_kw,'123');assert.equal(persisted.vin_details.characteristics.transmission_code,'TEST-AT');}
  else {assert.equal(persisted.engine_code,'MANUAL-CODE');assert.equal(persisted.vin_details.characteristics.body_class,'Manual body');}
  await page.screenshot({path:`/tmp/vin-create-qa/created-${i}.png`,fullPage:false});
 }
 await page.goto('/vehicles');await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();const form=page.getByRole('region',{name:'Додавання автомобіля за VIN'});
 await form.getByLabel('VIN',{exact:true}).fill('INVALID');await expect(form.getByRole('button',{name:'Визначити автомобіль'})).toBeDisabled();
 await form.getByRole('button',{name:'Додати вручну'}).click();await expect(form.getByLabel('Марка')).toBeVisible();
 await form.getByLabel('VIN',{exact:true}).fill(vins[0]);await form.getByRole('button',{name:'Визначити автомобіль'}).click();await expect(form.getByLabel('Модель',{exact:true})).toHaveValue('OFFLINE TEST A');
 await form.getByLabel('Характеристики перевірено, підтверджую додавання').check();await form.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
 await expect(form.getByRole('alert')).toContainText('уже існує');await expect(form.getByRole('button',{name:'Відкрити наявний автомобіль'})).toBeVisible();
 assert.equal((await (await c.request.get('/api/v1/vehicles')).json()).total,2);assert.deepEqual(errors,[]);
 console.log('Both requested VINs: fixture decode, review, PostgreSQL save/reload, all attributes, duplicate and invalid/manual fallback: PASS');await c.close();
}finally{await browser.close();}
