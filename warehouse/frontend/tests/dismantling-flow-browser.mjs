// Presentation state matrix. Built application + local auth; provider responses intercepted.
import {chromium,expect as baseExpect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local fixture guard required');
const origin='http://127.0.0.1:5227',out='/tmp/carpot-dismantling-redesign';fs.mkdirSync(out,{recursive:true});
const expect=baseExpect.configure({timeout:12000});
const scenarios=['empty','selected','partial','complete','saved_pp','unavailable','tokens','base','saved','stock','stale','limited','limited_saved','taxonomy'];
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const results=[];
try{
 for(const width of [1440,390]){
  const context=await browser.newContext({baseURL:origin,viewport:{width,height:width===390?844:1000}});
  const signup=await context.request.post('/api/v1/auth/register',{data:{name:'UX QA fixture',email:`ux-${crypto.randomUUID()}@example.test`,password:'synthetic-local-ux-matrix-password'}});
  assert.equal(signup.status(),201);const auth=await signup.json();
  for(const scenario of scenarios){
   const ktype=['selected','tokens','saved_pp','limited_saved'].includes(scenario)?9743:null;
   const created=await context.request.post('/api/v1/vehicles',{headers:{'X-CSRF-Token':auth.csrf_token},data:{manufacturer:'Volvo',model:'XC90 II',year:2018,engine:'2.0',drive_type:'AWD',ktype,donor_id:scenario+'-'+width}});
   assert.equal(created.status(),201);const vehicle=await created.json();
   const page=await context.newPage(),errors=[],writes=[];let paid=0,directoryCalls=0;
   page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url())});
   if(scenario.startsWith('limited'))await page.route('**/api/v1/auth/me',async route=>{const response=await route.fetch();const user=await response.json();await route.fulfill({json:{...user,role:'MANAGER',permissions:['vehicles.view','catalog.view','inventory.view']}})});
   const ownSaved=['base','saved','stock','stale'].includes(scenario),ppSaved=['saved_pp','limited_saved'].includes(scenario);
   await page.route(`**/api/v1/vehicles/${vehicle.id}/unified-catalogue**`,async route=>{
    const url=new URL(route.request().url());if(url.searchParams.has('model_id'))directoryCalls++;
    if(scenario==='unavailable')return route.fulfill({json:{saved:false,available:false,items:[]}});
    if(ownSaved)return route.fulfill({json:{saved:true,source:scenario==='base'?'base':'catalogue',type_count:3,modification:{description:'T6 AWD'},review_required:scenario==='stale'}});
    return route.fulfill({json:{saved:false,available:true,items:url.searchParams.has('model_id')?[{source_modification_id:107555,model_id:13084,modification:{description:'T6 AWD'},coverage_verified:['complete','taxonomy'].includes(scenario),taxonomy_status:scenario==='taxonomy'?'draft':'reviewed'}]:[]}});
   });
   if(ppSaved)await page.route(`**/api/v1/vehicles/${vehicle.id}/plan-parts-checklist?*`,route=>route.fulfill({json:{items:[],total:96,synced:true,ktype:9743}}));
   await page.route('**/api/v1/plan-parts/workspace?*',route=>route.fulfill({json:{categories:ppSaved?[{pt_id:1,name:'Starter',name_uk:'Стартер',article_count:1}]:[],parts:[],receipts:[],responses:[],saved_modifications:[{ktype:9743,modification:'2.0 бензин'}],saved_plan_ktypes:[],policy:{terms_confirmed:true,max_tokens:{categories:1,ktype:1}},summary:{}}}));
   await page.route(`**/api/v1/vehicles/${vehicle.id}/dismantling-workspace?*`,route=>route.fulfill({json:{items:Array.from({length:ppSaved?96:3},(_,i)=>['Стартер','Генератор','Фара'][i%3]).map((name,i)=>({key:'fixture:'+i,name,original:name,translated:true,category:i%3===2?'Освітлення':'Електрика та електроніка',kind:'part',pt_id:ppSaved?i+1:null,state:scenario==='stock'&&i===2?'received':'planned',parts:scenario==='stock'&&i===2?[{id:'synthetic-part',name,quantity:1,reserved_quantity:0,available_quantity:1,archived:false}]:[],included:true})),progress:{planned:3,received:scenario==='stock'?1:0},translation:{translated:3,pending:0}}}));
   if(scenario==='tokens'){
    await page.route('**/api/v1/plan-parts/categories/recover?*',route=>route.fulfill({status:409,json:{detail:'No saved categories'}}));
    await page.route('**/api/v1/plan-parts/categories/lookup?*',route=>{paid++;return route.fulfill({status:402,json:{detail:'Недостатньо токенів API'}})});
   }
   await page.goto('/vehicles?donor='+vehicle.id);
   const flow=page.getByRole('region',{name:'Розбір автомобіля',exact:true});await expect(flow).toBeVisible();
   await expect(flow.getByText('Перевіряємо збережені дані…',{exact:true})).toHaveCount(0);
   if(ownSaved||ppSaved){
    await expect(flow.locator('.wd-board')).toHaveCount(1);await expect(flow.locator('.uf-stage')).toHaveCount(0);
    await expect(flow.getByLabel('Показники розбору')).toBeVisible();
    if(scenario==='stock')await expect(flow.locator('.uf-status')).toHaveText('У процесі розбору');
    if(scenario==='stale'){await expect(flow.getByRole('alert')).toContainText('Характеристики автомобіля змінилися');await expect(flow.getByRole('button',{name:'Додати 1 шт.',exact:true}).first()).toBeDisabled();}
    if(scenario==='saved_pp'){
      assert.equal(directoryCalls,0,'Saved plan should not wait for remote Catalogue lookup');
      await expect(flow).toContainText('повторне відкриття без оплати');
      await expect(flow.locator('.uf-metrics')).toContainText('96');
      await flow.getByLabel('Пошук деталей плану').fill('Генератор');
      await expect(flow.locator('article.wd-row')).toHaveCount(10);
      await flow.getByLabel('Пошук деталей плану').fill('');
      await flow.locator('article.wd-row').first().click();
      await expect(page.getByRole('dialog',{name:'Швидкий перегляд запчастини'})).toBeVisible();
      await page.getByRole('button',{name:'Закрити швидкий перегляд'}).click();
      await expect(page.getByRole('dialog',{name:'Швидкий перегляд запчастини'})).toHaveCount(0);
      await flow.getByLabel('Вибрати всі відфільтровані позиції').check();
      await expect(flow.getByRole('group',{name:'Дії з вибраними'})).toContainText('96');
      await flow.getByRole('button',{name:'Зняти вибір',exact:true}).click();
      await expect(flow.getByRole('group',{name:'Дії з вибраними'})).toHaveCount(0);
    }
   }else if(scenario==='limited'){
    await expect(flow).toContainText('зверніться до керівника');await expect(flow.getByRole('button',{name:'Продовжити',exact:true})).toBeDisabled();
   }else if(scenario==='selected'||scenario==='tokens'){
    await expect(flow.getByRole('heading',{name:'Підготуйте план запчастин'})).toBeVisible();
    if(scenario==='tokens'){
     await flow.getByLabel('Варіант плану').selectOption('professional');
     await flow.getByRole('button',{name:'Сформувати план розбору',exact:true}).click();
     await expect(flow.getByRole('alertdialog')).toContainText('1 токенів');assert.equal(paid,0);
     await flow.getByRole('button',{name:'Підтвердити та отримати',exact:true}).click();
     await expect(flow.getByRole('alert')).toContainText('Недостатньо токенів');assert.equal(paid,1);
     await flow.getByLabel('Варіант плану').selectOption('base');
    }
   }else{
    await expect(flow.getByRole('heading',{name:'Оберіть комплектацію автомобіля'})).toBeVisible();
    if(scenario==='empty')await expect(flow.getByRole('button',{name:'Продовжити',exact:true})).toBeDisabled();
    if(['partial','complete','taxonomy'].includes(scenario)){
     await flow.getByLabel('Модифікація',{exact:true}).selectOption('catalogue:107555');
     await flow.getByRole('button',{name:'Продовжити',exact:true}).click();
     if(scenario==='complete')await expect(flow.getByLabel('Варіант плану')).toHaveValue('catalogue');
     else {await expect(flow).toContainText(scenario==='taxonomy'?'українські категорії ще потребують перевірки':'Частину запчастин знайдено');await expect(flow.getByLabel('Варіант плану')).toHaveValue('base');}
    }
    if(scenario==='unavailable'){await flow.getByRole('button',{name:'Продовжити без уточнення',exact:true}).click();await expect(flow.getByLabel('Варіант плану')).toHaveValue('base');}
   }
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${scenario}/${width} overflow`);
   assert.deepEqual(errors,[]);if(scenario!=='tokens')assert.deepEqual(writes,[]);
   if(['empty','partial','saved_pp','stock'].includes(scenario))await page.screenshot({path:`${out}/${scenario}-${width}.png`,fullPage:true});
   results.push({scenario,width,js_errors:errors,writes:writes.length,simulated_paid:paid});await page.close();
  }
  await context.close();
 }
 fs.writeFileSync(out+'/state-matrix.json',JSON.stringify(results,null,2));console.log('PASS 14 presentation states × 1440/390; paid response simulated only');
}finally{await browser.close()}
