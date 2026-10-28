// Controlled synthetic HTTP faults against production assets and real local owner auth.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
const origin=process.env.WAREHOUSE_STAGE2C_ORIGIN||'http://127.0.0.1:5186';
if(process.env.WAREHOUSE_E2E!=='1'||new URL(origin).hostname!=='127.0.0.1')throw Error('Local test only');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const width of [1440,390]){
 const context=await browser.newContext({baseURL:origin,viewport:{width,height:900}});assert.equal((await context.request.post('/api/v1/auth/login',{data:{email:'stage2c-owner@example.test',password:'local-stage2c-password'}})).status(),200);
 let mode='queued',id=null,posts=0,getFailures=0,timeout=false,publishPosts=0;
 let report={canonical_types:216,placements:227,mapped_offers:1,source_offers:2,unprocessed_records:1,ambiguous_mappings:0,committed:false,issues:[]};
 function run(){return {id,mode:'preview',status:mode,token:'a'.repeat(64),snapshot_sha:'b'.repeat(64),report:mode==='done'?report:{...report,committed:true},error:mode==='error'?'Нормалізацію перервано. Каталог не змінено.':null};}
 await context.route('**/api/v1/catalogue/admin/canonical/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  if(path.endsWith('/diagnostics'))return route.fulfill({json:{catalogue_v2:{offers:2,paths:2,models:1},canonical:{published:false,rules_current:false,types:0,placements:0,mapped_offers:0,unprocessed_records:0},latest_run_id:id}});
  if(path.endsWith('/rules/preview')&&req.method()==='POST'){assert.equal(req.postDataJSON().expected_revision,1);report={...report,expected_revision:1};mode='done';id='synthetic-current-group';return route.fulfill({status:202,json:run()});}
  if(path.endsWith('/runs')&&req.method()==='POST'){
   if(req.postDataJSON().mode==='publish'){publishPosts++;return route.fulfill({status:409,json:{detail:'Джерела змінилися; потрібна нова перевірка нормалізації'}});}
   posts++;id='synthetic-preview-'+posts;mode='queued';if(timeout)return route.fulfill({status:504,json:{detail:'Шлюз не дочекався відповіді'}});return route.fulfill({status:202,json:run()});
  }
  if(path.includes('/runs/')){if(getFailures>0){getFailures--;return route.fulfill({status:503,json:{detail:'Точна помилка читання статусу'}});}return route.fulfill({json:run()});}
  return route.continue();
 });
 const page=await context.newPage();await page.goto('/administration/catalogue/import');const admin=page.getByRole('region',{name:'Публікація конструктивного каталогу'});await expect(admin).toBeVisible();
 getFailures=1;await admin.getByRole('button',{name:'Перевірити нормалізацію',exact:true}).evaluate(b=>{b.click();b.click();});await expect(admin.getByText(/Не вдалося прочитати стан/)).toBeVisible();assert.equal(posts,1);await expect(admin.getByRole('heading',{name:'Результат перевірки',exact:true})).toHaveCount(0);await expect(admin.getByRole('button',{name:'Опублікувати каталог',exact:true})).toHaveCount(0);
 mode='done';await expect(admin.getByRole('heading',{name:'Результат перевірки',exact:true})).toBeVisible({timeout:12000});await admin.getByLabel('Підтверджую публікацію перевіреного довідника без зміни складу',{exact:true}).check();await admin.getByRole('button',{name:'Опублікувати каталог',exact:true}).click();await expect(admin.getByRole('alert')).toHaveText('Джерела змінилися; потрібна нова перевірка нормалізації');assert.equal(publishPosts,1);await expect(admin.getByRole('button',{name:'Опублікувати каталог',exact:true})).toBeDisabled();
 timeout=true;await admin.getByRole('button',{name:'Перевірити нормалізацію',exact:true}).click();await expect(admin.getByText(/Перевірка: Очікує/)).toBeVisible();assert.equal(posts,2);await expect(admin.getByRole('heading',{name:'Результат перевірки',exact:true})).toHaveCount(0);
 await page.reload();await expect(admin.getByText(/Перевірка: Очікує/)).toBeVisible();assert.equal(posts,2);mode='error';await expect(admin.getByText('Нормалізацію перервано. Каталог не змінено.',{exact:true}).first()).toBeVisible({timeout:12000});await expect(admin.getByRole('button',{name:'Опублікувати каталог',exact:true})).toHaveCount(0);
 report={kind:'rule-preview',criteria:{phrase:'точна тестова назва',category:'Електрика',subcategory:'Насоси',manufacturer:'',model:'',conditions:{}},type_id:'synthetic-type',evidence:'Synthetic revision safety fixture',current_revision:1,expected_revision:0,matched_count:1,will_link_count:1,exception_count:0,conflict_count:0,examples:[]};mode='done';await page.reload();await expect(admin.getByRole('button',{name:'Перевірити актуальне правило',exact:true})).toBeVisible();await expect(admin.getByRole('button',{name:'Зберегти правило',exact:true})).toBeDisabled();await admin.getByRole('button',{name:'Перевірити актуальне правило',exact:true}).click();await expect(admin.getByRole('button',{name:'Перевірити актуальне правило',exact:true})).toHaveCount(0);await admin.getByLabel('Підтверджую точне групове правило',{exact:true}).check();await expect(admin.getByRole('button',{name:'Зберегти правило',exact:true})).toBeEnabled();
 console.log(`PASS ${width}px synthetic owner faults: stale 202 report hidden, poll 503 recovery, explicit stale-token 409, lost enqueue 504 recovery, reload/error, no duplicate publication, current-revision re-preview`);await context.close();
}}finally{await browser.close();}
