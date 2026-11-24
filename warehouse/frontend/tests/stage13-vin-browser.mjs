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
    await expect(dialog.getByText(/Доступний частковий план/)).toBeVisible();
    await expect(dialog.getByText(/50 грн|Перевірка API-балансу|Тест VINState/)).toHaveCount(0);
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
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:width===390?844:1000});
      assert.equal(await dialog.evaluate(element=>element.scrollWidth>element.clientWidth+1),false);
      assert.equal(await dialog.locator('.vin-footer').evaluate(element=>getComputedStyle(element).position),'sticky');
      await dialog.screenshot({path:`${output}/${theme}-${width}.png`,animations:'disabled'});
      console.log('PASS',theme,width);
    }
    await dialog.getByRole('button',{name:'Скасувати',exact:true}).click();
    await expect(dialog).not.toBeVisible();
  }

  await page.setViewportSize({width:390,height:844});
  await open();
  await dialog.getByRole('button',{name:'Вручну',exact:true}).click();
  await expect(dialog.getByRole('textbox',{name:'Марка',exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'Із каталогу',exact:true}).click();
  await expect(dialog.getByRole('form',{name:'Автомобіль із каталогу'})).toBeVisible();
  await dialog.getByRole('button',{name:'За VIN',exact:true}).click();

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

  await dialog.getByLabel('Характеристики перевірено',{exact:true}).check();
  await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  const vehicles=await (await context.request.get('/api/v1/vehicles')).json();
  assert.equal(vehicles.items.length,1);
  const donor=vehicles.items[0];
  assert.equal(donor.vin,vin);
  assert.equal(donor.model,'3 Series');
  const parts=await (await context.request.get('/api/v1/parts?vehicle_id='+donor.id)).json();
  assert.equal(parts.total,0);
  const plan=await (await context.request.get('/api/v1/vehicles/'+donor.id+'/dismantling-v3')).json();
  assert.equal(plan.items.length,1);
  assert.equal(plan.items[0].name,'Synthetic engine');
  assert.deepEqual(errors,[]);
  assert.deepEqual(paid,[]);
  console.log('PASS mode switching, stale catalogue response, real API save, one pinned item, zero stock and paid requests');
}finally{
  await context.close();
  await browser.close();
}
