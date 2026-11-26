import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chromium,expect} from '@playwright/test';

const origin=new URL(process.env.WAREHOUSE_BROWSER_URL||'http://127.0.0.1:5236');
assert.equal(process.env.WAREHOUSE_E2E,'1');
assert.equal(origin.hostname,'127.0.0.1');
const output=process.env.WAREHOUSE_STAGE13_SCREENSHOTS||'/tmp/carpot-stage13-screenshots';
fs.mkdirSync(output,{recursive:true});
const browser=await chromium.launch({
  executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',
  args:['--no-sandbox'],
});
const context=await browser.newContext({baseURL:origin.href,viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[];
const paid=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{
  if(/\/vin\/(paid|vinstate|vincario|tecalliance)|\/plan-parts\//.test(request.url()))paid.push(request.url());
});

try{
  const registration=await context.request.post('/api/v1/auth/register',{data:{
    name:'Stage 13 QA',email:'stage13-'+crypto.randomUUID()+'@example.test',password:'isolated-browser-fixture-password',
  }});
  assert.equal(registration.status(),201,await registration.text());
  const dialog=page.getByRole('dialog',{name:'Новий автомобіль-донор'});
  const vin='WBAAAAAAAAAAAAA01';
  async function open(){
    await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
    await expect(dialog).toBeVisible();
  }
  async function decode(value=vin){
    await dialog.getByRole('textbox',{name:'VIN',exact:true}).fill(value);
    await dialog.getByRole('button',{name:'Визначити автомобіль',exact:true}).click();
  }
  async function ready(){
    await expect(dialog.getByRole('region',{name:'Зведення автомобіля'})).toContainText('Aster Mobility · 3 Series · 2015');
    await dialog.getByRole('combobox',{name:/^Доступні модифікації/}).selectOption({index:1});
    await expect(dialog.getByText(/Доступний частковий план/)).toBeVisible();
    await expect(dialog.locator('.vin-ready')).toContainText('Категорії: 0');
    await expect(dialog.locator('.vin-ready')).toContainText('Запчастини: 1');
    await expect(dialog.getByText(/50 грн|Перевірка API-балансу|Тест VINState/)).toHaveCount(0);
  }
  async function checkFooter(){
    const content=await dialog.locator('.vin-content').boundingBox();
    const footer=await dialog.locator('.vin-footer').boundingBox();
    const shell=await dialog.boundingBox();
    assert(content&&footer&&shell);
    assert(content.y+content.height<=footer.y+1);
    assert(footer.y+footer.height<=shell.y+shell.height+1);
    assert.equal(await dialog.evaluate(element=>element.scrollWidth>element.clientWidth+1),false);
  }
  await page.goto('/vehicles');
  for(const theme of ['light','onyx','gold','forest']){
    await page.evaluate(theme=>{
      localStorage.setItem('warehouse.theme',theme==='light'?'light':'dark');
      localStorage.setItem('warehouse.nightStyle',theme==='light'?'forest':theme);
      window.dispatchEvent(new StorageEvent('storage',{key:null,storageArea:localStorage}));
    },theme);
    await expect(page.locator('html')).toHaveAttribute('data-theme',theme==='light'?'light':'dark');
    if(theme!=='light')await expect(page.locator('html')).toHaveAttribute('data-night-style',theme);
    await open();
    await decode();
    await ready();
    await dialog.getByText('Виправити характеристики',{exact:true}).click();
    const modelYear=dialog.getByRole('combobox',{name:'Модельний рік',exact:true});
    await expect(modelYear).toHaveValue('2015');
    await modelYear.selectOption('2016');
    await expect(modelYear).toHaveValue('2016');
    await modelYear.selectOption('2015');
    await dialog.getByText('Виправити характеристики',{exact:true}).click();
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:width===390?844:1000});
      await checkFooter();
      await dialog.screenshot({path:`${output}/${theme}-${width}.png`,animations:'disabled'});
      console.log('PASS',theme,width);
    }
    await dialog.getByRole('button',{name:'Скасувати',exact:true}).click();
    await expect(dialog).not.toBeVisible();
  }

  await page.setViewportSize({width:390,height:844});
  await open();
  await decode();
  await ready();
  await dialog.getByText('Виправити характеристики',{exact:true}).click();
  await dialog.getByRole('combobox',{name:'Модельний рік',exact:true}).selectOption('2016');
  await dialog.getByRole('button',{name:'Застосувати зміни'}).click();
  await expect(dialog.getByRole('region',{name:'Зведення автомобіля'})).toContainText('2016');
  await dialog.getByText('Виправити характеристики',{exact:true}).click();
  await dialog.getByRole('combobox',{name:/^Доступні модифікації/}).selectOption({index:1});
  await expect(dialog.locator('.vin-ready')).toBeVisible();
  const createVehiclePattern='**/api/v1/vehicles';
  let failedVinKey;
  await page.route(createVehiclePattern,route=>{
    failedVinKey=route.request().postDataJSON().intake_request_key;
    return route.fulfill({status:503,json:{detail:'Тимчасова помилка збереження VIN'}});
  },{times:1});
  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('Тимчасова помилка збереження VIN');
  await dialog.getByRole('button',{name:'Із каталогу',exact:true}).click();
  await expect(dialog.getByRole('form',{name:'Автомобіль із каталогу'})).toBeVisible();
  await expect(dialog.getByRole('heading',{name:'Підбір із каталогу'})).toBeVisible();
  await dialog.getByText('Пошук у каталозі',{exact:true}).click();
  await expect(dialog.getByRole('textbox',{name:'Пошук марки'})).toBeVisible();
  await dialog.getByText('Пошук у каталозі',{exact:true}).click();
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  const year=dialog.getByRole('combobox',{name:'Рік автомобіля',exact:true});
  await expect(year).toBeDisabled();
  await dialog.getByRole('combobox',{name:'Марка',exact:true}).selectOption('840');
  await dialog.getByRole('combobox',{name:'Модель',exact:true}).selectOption('701');
  await expect(year.locator('option[value="2010"]')).toHaveCount(0);
  await year.selectOption('2015');
  const temporaryCatalogueFailure='**/api/v1/vehicles/vin/source-graph?*';
  await page.route(temporaryCatalogueFailure,route=>route.fulfill({status:503,json:{detail:'Service unavailable'}}),{times:1});
  await dialog.getByRole('combobox',{name:'Модифікація',exact:true}).selectOption('900');
  await expect(dialog.getByRole('alert')).toContainText('Каталог запчастин тимчасово недоступний');
  await expect(year).toHaveValue('2015');
  await expect(year.locator('option[value="2013"]')).toHaveCount(0);
  await expect(dialog.getByRole('combobox',{name:'Модифікація',exact:true})).toHaveValue('900');
  await expect(dialog.getByRole('button',{name:'Додати автомобіль',exact:true})).toBeDisabled();
  await dialog.getByRole('button',{name:'Повторити',exact:true}).click();
  await expect(dialog.getByText(/План розбору готовий/)).toBeVisible();
  await expect(dialog.getByRole('region',{name:'Зведення автомобіля'})).toContainText('Aster Mobility · 3 (F30) · 2015');
  await expect(dialog.getByRole('region',{name:'Зведення автомобіля'})).toContainText('1,995 л');
  await expect(dialog.getByText('Усі характеристики',{exact:true})).toBeVisible();
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:width===390?844:1000});
    await checkFooter();
    await dialog.screenshot({path:`${output}/catalogue-${width}.png`,animations:'disabled'});
  }
  const createCatalogue=page.waitForResponse(response=>response.url().endsWith('/api/v1/vehicles')&&response.request().method()==='POST');
  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  const catalogueCreated=await createCatalogue;
  assert.equal(catalogueCreated.status(),201,await catalogueCreated.text());
  const catalogueRequest=catalogueCreated.request().postDataJSON();
  assert.equal(Object.hasOwn(catalogueRequest,'vin'),false);
  assert(failedVinKey);
  assert.notEqual(catalogueRequest.intake_request_key,failedVinKey);
  assert.equal((await catalogueCreated.json()).vin,null);
  await expect(dialog).not.toBeVisible();

  await page.goto('/vehicles');
  await open();
  await dialog.getByRole('button',{name:'Вручну',exact:true}).click();
  await dialog.getByRole('textbox',{name:'Марка',exact:true}).fill('Unknown manufacturer');
  await dialog.getByRole('textbox',{name:'Модель',exact:true}).fill('Manual vehicle');
  await expect(dialog.getByRole('button',{name:'Додати автомобіль',exact:true})).toBeDisabled();
  await dialog.getByRole('checkbox',{name:'Додати з базовим каталогом CarPot'}).check();
  const createManual=page.waitForResponse(response=>response.url().endsWith('/api/v1/vehicles')&&response.request().method()==='POST');
  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  const manualCreated=await createManual;
  assert.equal(manualCreated.status(),201,await manualCreated.text());
  assert.equal((await manualCreated.json()).dismantling_v3.unified_base,true);
  await expect(dialog).not.toBeVisible();

  await page.goto('/vehicles');
  await open();

  // Exercise independent maker cursors and a clarification from a later variant page.
  const resolutionPattern='**/api/v1/vehicles/vin/resolution?*';
  const model={kind:'passenger',manufacturer_id:840,model_id:701,model:'3 Series'};
  const modelCursors=[
    {maker:'passenger:840',after:150,kind:'passenger'},
    {maker:'commercial:841',after:250,kind:'commercial'},
  ];
  let clarifiedScope;
  await page.route(resolutionPattern,async route=>{
    const query=new URL(route.request().url()).searchParams;
    const headers=route.request().headers();
    const clarification=JSON.parse(decodeURIComponent(headers['x-vin-clarifications']));
    const scoped=query.has('model_id');
    const after=query.get('after');
    if(clarification.answers.drive_type)clarifiedScope=[query.get('maker'),query.get('model_id'),after,clarification.answers.drive_type];
    await route.fulfill({json:{
      items:[], models:[model], review:[], search_complete:false, status:'incomplete', automatic:null,
      model_cursors:query.has('maker')?[]:modelCursors,
      next_after:scoped&&after==='0'&&!clarification.answers.drive_type?915:null,
      questions:scoped&&after==='915'?[{field:'drive_type',options:['FWD','AWD']}]:[],
    }});
  });
  await decode();
  await dialog.getByRole('button',{name:'Наступні моделі · легкові',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Наступні моделі · легкові',exact:true})).toHaveCount(0);
  await dialog.getByRole('button',{name:'Наступні моделі · комерційні',exact:true}).click();
  await dialog.getByRole('button',{name:'Переглянути всі модифікації моделі',exact:true}).click();
  await dialog.getByRole('button',{name:'Наступні модифікації',exact:true}).click();
  await dialog.getByRole('combobox',{name:/^Привід/}).selectOption('AWD');
  await expect.poll(()=>clarifiedScope).toEqual(['passenger:840','701','0','AWD']);
  await page.unroute(resolutionPattern);
  await dialog.getByRole('button',{name:'Скасувати',exact:true}).click();
  await open();

  // Hold the previous VIN's catalogue response while the active VIN is changed.
  let release;
  let started;
  const hold=new Promise(resolve=>{release=resolve});
  const previousRequest=new Promise(resolve=>{started=resolve});
  const pattern='**/api/v1/vehicles/vin/resolution?*';
  let first=true;
  await page.route(pattern,async route=>{
    if(!first){await route.continue();return;}
    first=false;
    const response=await route.fetch();
    started();
    await hold;
    const body=await response.json();
    body.items=body.items.map(item=>({...item,modification:'STALE RESULT'}));
    try{await route.fulfill({response,json:body})}catch{/* The browser cancels the stale request. */}
  });
  await decode('WBAAAAAAAAAAAAA02');
  await previousRequest;
  await decode();
  await ready();
  release();
  await page.unrouteAll({behavior:'wait'});
  await expect(dialog.getByText('STALE RESULT',{exact:false})).toHaveCount(0);


  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  const vehicles=await (await context.request.get('/api/v1/vehicles')).json();
  assert.equal(vehicles.items.length,3);
  const vinDonors=vehicles.items.filter(item=>item.vin===vin);
  assert.equal(vinDonors.length,1);
  const donor=vinDonors[0];
  assert.equal(donor.vin,vin);
  assert.equal(donor.model,'3 Series');
  const parts=await (await context.request.get('/api/v1/parts?vehicle_id='+donor.id)).json();
  assert.equal(parts.total,0);
  const plan=await (await context.request.get('/api/v1/vehicles/'+donor.id+'/dismantling-v3')).json();
  assert.equal(plan.items.length,1);
  assert.equal(plan.items[0].name,'Synthetic engine');

  await page.goto('/vehicles');
  await open();
  await decode();
  await ready();
  const conflict=page.waitForResponse(response=>response.url().endsWith('/api/v1/vehicles')&&response.request().method()==='POST');
  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  const duplicate=await conflict;
  assert.equal(duplicate.status(),409);
  assert.equal((await duplicate.json()).detail.vehicle_id,donor.id);
  await expect(dialog.getByRole('alert')).toContainText('уже існує');
  await dialog.getByRole('button',{name:'Відкрити наявний автомобіль'}).click();
  await expect(page).toHaveURL(url=>url.searchParams.get('donor')===donor.id);
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button',{name:'Розбір і запчастини'}).click();
  await expect(page.getByText('Synthetic engine',{exact:true}).first()).toBeVisible();

  const historical=await context.request.post('/api/v1/vehicles',{
    headers:{'X-CSRF-Token':(await registration.json()).csrf_token},
    data:{manufacturer:'ASTER MOBILITY',model:'3 series',year:2017,status:'planned'},
  });
  assert.equal(historical.status(),201,await historical.text());
  await page.goto('/vehicles');
  const brandFilter=page.getByRole('combobox',{name:'Фільтр марки'});
  const modelFilter=page.getByRole('combobox',{name:'Фільтр моделі'});
  await brandFilter.selectOption('aster mobility');
  await expect(brandFilter.getByRole('option',{name:/^aster mobility$/i})).toHaveCount(1);
  await modelFilter.selectOption('3 series');
  await expect(modelFilter.getByRole('option',{name:/^3 series$/i})).toHaveCount(1);
  const yearFilter=page.getByRole('combobox',{name:'Фільтр року'});
  await expect(yearFilter.locator('option[value="2015"]')).toHaveCount(1);
  await expect(yearFilter.locator('option[value="2017"]')).toHaveCount(1);
  await page.getByRole('button',{name:'Таблиця',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:/aster mobility 3 series/i})).toHaveCount(2);
  assert.deepEqual(errors,[]);
  assert.deepEqual(paid,[]);
  console.log('PASS VIN → catalogue reset, year bounds, duplicate card and plan, case-insensitive filters, manual intake and zero automatic stock');
}finally{
  await context.close();
  await browser.close();
}
