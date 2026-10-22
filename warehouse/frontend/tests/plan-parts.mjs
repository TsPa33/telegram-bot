// Production assets + mocked backend. No provider calls or shared fixture catalogue.
import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const fixture=async name=>JSON.parse(await readFile(new URL('../../backend/tests/fixtures/'+name,import.meta.url),'utf8')).data.results;
const brands=await fixture('plan_parts_brands_708.json');
const year=v=>v===null?null:Number(v.slice(0,4));
const models=(await fixture('plan_parts_models_vw_121_292.json')).map(m=>({...m,year_from:year(m.year_from),year_to:year(m.year_to)}));
const mods=(await fixture('plan_parts_modifications_golf4_1994_35.json')).map(m=>({...m,year_from:year(m.year_from),year_to:year(m.year_to)}));
const origin='http://127.0.0.1:18764';
const server=spawn(process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','18764','--strictPort'],{stdio:'pipe'});
let browser;
try {
 for(let i=0;i<50;i++){try{if((await fetch(origin)).ok)break;}catch{}if(i===49)throw Error('Preview timeout');await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  const context=await browser.newContext({viewport}),page=await context.newPage();
  const requests=[],errors=[];let saved, unavailable=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   requests.push(p);const reply=data=>route.fulfill({json:data});
   if(p.endsWith('/auth/me'))return reply({id:'account',name:'Тест',email:'test@example.test'});
   if(p.endsWith('/vehicle-catalog'))return reply({complete:false,brands:[{name:'Volkswagen',models:['Golf','Passat']},{name:'Volvo',models:['XC90']}]});
   if(p.endsWith('/brands/lookup'))return unavailable ? route.fulfill({status:503,json:{detail:'Plan.Parts вимкнено'}}) : reply(brands);
   if(p.endsWith('/models/lookup')){assert.equal(url.searchParams.get('mfa_id'),'121');return reply(models);}
   if(p.endsWith('/modifications/lookup')){assert.equal(url.searchParams.get('ms_id'),'1994');return reply(mods);}
   if(p.endsWith('/vehicles')&&req.method()==='POST'){saved=req.postDataJSON();return reply({id:'new',donor_id:'AUTO-test',...saved});}
   if(p.endsWith('/vehicles'))return reply({items:[],total:0});
   if(p.endsWith('/analytics'))return reply({positions:0,stock_units:0});
   if(p.endsWith('/plan-parts-checklist'))return reply({items:[],total:0,historical_total:0,ktype:saved?.ktype,synced:false});
   throw Error('Unexpected request '+p);
  });
  const combo=name=>page.getByRole('combobox',{name,exact:true});
  async function choose(name,query,option){const input=combo(name);await input.fill(query);await page.getByRole('option',{name:option,exact:true}).click();}
  const open=async()=>page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
  const save=async()=>{await page.getByRole('dialog').getByRole('button',{name:'Додати автомобіль',exact:true}).click();await expect(page.getByRole('dialog')).not.toBeVisible();};
  const paid=()=>requests.filter(p=>p.includes('/plan-parts/')).length;
  await page.goto(origin+'/vehicles');await open();
  await expect(page.getByRole('dialog').getByRole('textbox')).toHaveCount(0);
  await expect(page.getByLabel('VIN',{exact:true})).toHaveCount(0);
  await combo('Марка').fill('VoLk');await expect(page.getByRole('option',{name:'Volkswagen',exact:true})).toBeVisible();await combo('Марка').press('ArrowDown');await combo('Марка').press('Enter');
  await combo('Модель').focus();await expect(page.getByRole('option',{name:'XC90',exact:true})).toHaveCount(0);
  // Keyboard search and confirmation.
  await combo('Модель').fill('go');await combo('Модель').press('Enter');
  await combo('Рік випуску').selectOption('2001');
  const years=await combo('Рік випуску').locator('option').evaluateAll(nodes=>nodes.map(n=>n.value).filter(v=>/^\d+$/.test(v)).map(Number));
  assert(years.every((v,i)=>!i||v<years[i-1]));
  await page.screenshot({path:`/tmp/warehouse-quick-${viewport.width}.png`});
  assert.equal(paid(),0);await save();await expect(page.getByRole('dialog')).not.toBeVisible();
  assert.deepEqual(saved,{manufacturer:'Volkswagen',model:'Golf',year:2001,engine:'',ktype:null});
  await expect(page.getByRole('button',{name:'Відкрити картку',exact:true})).toBeVisible();
  await open();await choose('Марка','Volks','Volkswagen');await choose('Модель','Golf','Golf');await combo('Рік випуску').selectOption('2001');
  await choose('Марка','Volvo','Volvo');await expect(combo('Модель')).toHaveValue('');await expect(combo('Рік випуску')).toHaveValue('');
  await choose('Модель','XC90','XC90');await combo('Рік випуску').selectOption('2005');
  // Controlled manual entry, never mistaken for catalogue records.
  await choose('Марка','Нова марка','Використати «Нова марка»');
  await choose('Модель','Власна модель','Використати «Власна модель»');
  await combo('Рік випуску').selectOption('2000');await save();assert.equal(saved.manufacturer,'Нова марка');assert.equal(paid(),0);
  await open();await page.getByText('Точний підбір Plan.Parts',{exact:true}).click();await page.getByRole('checkbox',{name:'Використати Plan.Parts'}).check();
  assert.equal(paid(),0);
  await page.getByRole('button',{name:'Завантажити марки / повторити',exact:true}).click();
  await choose('Марка','VW','VW');
  await page.getByRole('button',{name:'Завантажити моделі / повторити',exact:true}).click();
  await choose('Модель','GOLF IV (1J1)','GOLF IV (1J1)');
  await expect(combo('Рік випуску').locator('option[value="1996"]')).toHaveCount(0);
  await expect(combo('Рік випуску').locator('option[value="2009"]')).toHaveCount(0);
  await combo('Рік випуску').selectOption('2001');
  await page.getByRole('button',{name:'Завантажити модифікації / повторити',exact:true}).click();
  await expect(combo('Двигун / модифікація')).toHaveValue('');
  await combo('Двигун / модифікація').fill('K-Type 16063');
  await page.getByRole('option',{name:/K-Type 16063$/}).click();
  await save();assert.equal(saved.ktype,16063);assert.equal(saved.engine,'1.9 TDI');assert.equal(paid(),3);
  // Provider failure never blocks the local fallback.
  await open();await expect(combo('Двигун / модифікація')).toHaveValue('');
  await page.getByText('Точний підбір Plan.Parts',{exact:true}).click();
  await page.getByRole('checkbox',{name:'Використати Plan.Parts'}).check();unavailable=true;
  await page.getByRole('button',{name:'Завантажити марки / повторити',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Plan.Parts вимкнено');
  await page.getByRole('checkbox',{name:'Використати Plan.Parts'}).uncheck();
  await choose('Марка','Volvo','Volvo');await choose('Модель','XC90','XC90');
  await combo('Рік випуску').selectOption('2005');await save();assert.equal(saved.ktype,null);
  assert.equal(paid(),4);
  assert(!requests.some(p=>p.endsWith('/parts')||p.includes('/categories')));assert.deepEqual(errors,[]);
  await context.close();console.log(`PASS quick/manual/provider vehicle selection ${viewport.width}x${viewport.height}`);
 }
}finally{await browser?.close();server.kill('SIGTERM');}
