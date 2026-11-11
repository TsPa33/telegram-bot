// Local real-auth/API/PostgreSQL only. No provider mocks or external VIN calls.
import {chromium,expect} from '@playwright/test';import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit local guard required');
const dir=process.env.ISSUE502_OUTPUT||'/tmp/issue502-shared';fs.mkdirSync(dir,{recursive:true});const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5251',viewport:{width:1440,height:1000}});
 const reg=await c.request.post('/api/v1/auth/register',{data:{name:'Shared UX QA',email:`shared502-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(reg.status(),201);const auth=await reg.json();
 const post=async(path,data)=>{const r=await c.request.post('/api/v1'+path,{data,headers:{'X-CSRF-Token':auth.csrf_token}});assert.ok(r.ok(),await r.text());return r.json()};
 const get=async(path)=>{const r=await c.request.get('/api/v1'+path,{headers:{'X-Warehouse-Client':'5'}});assert.ok(r.ok());return r.json()};
 const page=await c.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));const results=[];
 // Only provider response is a labelled fixture; all persistence and authentication are real.
 await page.route('**/api/v1/vehicles/vin/decode?*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({vin:'VF3AAAAA0N0000001',source:'offline_fixture',vehicle:{manufacturer:'PEUGEOT',model:'5008',year:2022,fuel_type:'Бензин'},available_fields:['manufacturer','model','year','fuel_type'],field_sources:{manufacturer:'offline_fixture',model:'offline_fixture',year:'offline_fixture'},message:'Локальний контроль форми; не live-декодування',additional:{}})}));
 await page.goto('/vehicles');await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();await page.getByLabel('VIN',{exact:true}).fill('VF3AAAAA0N0000001');await page.getByRole('button',{name:'Визначити автомобіль',exact:true}).click();await expect(page.getByLabel('Марка',{exact:true})).toHaveValue('PEUGEOT');await page.getByLabel('Рік',{exact:true}).fill('2021');await page.getByLabel('Характеристики перевірено, підтверджую додавання',{exact:true}).check();
 await page.screenshot({animations:'disabled',path:`${dir}/vin-form-fixture.png`});const created=page.waitForResponse(r=>r.url().endsWith('/api/v1/vehicles')&&r.request().method()==='POST');await page.locator('.vin-intake').getByRole('button',{name:'Додати автомобіль',exact:true}).click();const stored=await (await created).json();assert.equal(stored.year,2021);assert.equal(stored.vin_details.decoded.year,2022);assert.equal(stored.vin_details.characteristics.year,'2021');await page.unroute('**/api/v1/vehicles/vin/decode?*');
 for(const [manufacturer,model,year] of [['PEUGEOT','5008',1987],['Renault','ZOE',2020],['Volkswagen','Golf',2019]]){
  const v=await post('/vehicles',{manufacturer,model,year});await page.goto('/vehicles?donor='+v.id);
  const generator=page.getByRole('region',{name:'Універсальний каталог запчастин'}); // section is explicitly labelled
  const action=page.getByRole('button',{name:'Розібрати на запчастини',exact:true});await expect(action).toBeVisible();
  await page.screenshot({animations:'disabled',path:`${dir}/${manufacturer}-empty.png`});await action.click();await expect(page.getByRole('button',{name:'Зберегти перелік',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Зберегти перелік',exact:true}).click();await expect(page.getByRole('button',{name:'Оновити каталог',exact:true})).toBeVisible();
  const saved=await get(`/vehicles/${v.id}/dismantling-v3`);assert.equal(saved.total,227);assert.equal((await get(`/parts?vehicle_id=${v.id}`)).total,0);
  await page.reload();await expect(page.getByRole('button',{name:'Оновити каталог',exact:true})).toBeVisible();assert.equal((await get(`/vehicles/${v.id}/dismantling-v3`)).total,227);
  results.push({manufacturer,positions:saved.total,stock:0,reload:true});
 }
 for(const theme of ['light','dark'])for(const width of [1440,1920,390]){
  await page.setViewportSize({width,height:1000});await page.goto('/settings');await page.getByRole('button',{name:theme==='dark'?'Ніч':'День',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Загальні',exact:true})).toBeVisible();await page.getByRole('tab',{name:'Загальні',exact:true}).focus();await page.keyboard.press('ArrowRight');await expect(page.getByRole('tab',{name:'Оплати',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.getByRole('tabpanel',{name:'Оплати',exact:true})).toContainText('недоступне');assert.equal(await page.getByRole('button',{name:/LiqPay/}).count(),0);
  if(width>1100){await page.getByRole('button',{name:'Згорнути бічне меню',exact:true}).click();await page.getByRole('tab',{name:'Оплати',exact:true}).focus();await page.mouse.move(width-10,500);await expect(page.locator('.app')).toHaveClass(/sidebar-compact/);await page.getByRole('button',{name:'Розгорнути бічне меню',exact:true}).focus();await expect(page.locator('#warehouse-sidebar')).toBeVisible();await page.getByRole('button',{name:'Розгорнути бічне меню',exact:true}).click();}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`No overflow ${theme}/${width}`);await page.screenshot({animations:'disabled',path:`${dir}/settings-${theme}-${width}.png`});
  await page.goto('/inventory');await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  if(width===390){await page.getByRole('button',{name:'Відкрити меню',exact:true}).click();await expect(page.getByRole('dialog',{name:'Навігація Warehouse'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Відкрити меню',exact:true})).toBeFocused();}
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(`${dir}/report.json`,JSON.stringify({target:'LOCAL_REAL_AUTH_POSTGRES_TEST_RECORDS',results,themes:['light','dark'],widths:[1440,1920,390],keyboard:true,mobileMenu:true,errors},null,2));console.log('3-brand free plan save/reopen/no stock; settings tabs, day/night 1440/1920/390, keyboard/mobile: PASS');
}finally{await browser.close()}
