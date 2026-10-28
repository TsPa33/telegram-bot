// Real LOCAL API and production assets; requires a separately seeded *_test DB.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Set WAREHOUSE_E2E=1; never use staging/production');
const origin=process.env.CATALOGUE_TEST_ORIGIN||'http://127.0.0.1:18766';
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Only loopback test origins allowed');
const email=process.env.CATALOGUE_TEST_EMAIL,password=process.env.CATALOGUE_TEST_PASSWORD;
if(!email||!password)throw Error('Set local test platform-owner credentials');
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
function csv(article,sub='Бампери',category='Кузов'){
 const values=[['schema_version','source','source_article','manufacturer','model','category','subcategory','part_name','oem','condition','price_uah','price_usd','source_url','observed_at'],
  ['2','aleto',article,'BMW','X5',category,sub,'Синтетичний передній бампер','TEST-ONLY-OEM','synthetic test fixture','12.34','','https://aleto.ua/ua/detail/test-fixture/','2026-10-27T12:00:00+00:00']];
 return Buffer.from(values.map(row=>row.map(v=>'"'+v.replaceAll('"','""')+'"').join(',')).join('\n'));
}
try{
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const context=await browser.newContext({baseURL:origin,viewport});
  const login=await context.request.post('/api/v1/auth/login',{data:{email,password}});assert.equal(login.status(),200);
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/administration/catalogue/import');
  await expect(page.getByRole('heading',{name:'Імпорт глобального каталогу',exact:true})).toBeVisible();
  const run=Date.now(),category=`Синтетичний кузов ${run}-${viewport.width}`,name=`synthetic-${run}-${viewport.width}.csv`,article=`BROWSER-SYNTHETIC-${run}-${viewport.width}`;
  const before=(await(await context.request.get('/api/v1/catalogue')).json()).total;
  await page.getByLabel('Файл каталогу').setInputFiles({name,mimeType:'text/csv',buffer:csv(article,'Бампери',category)});
  await page.getByRole('button',{name:'Завантажити файл',exact:true}).click();
  await page.getByRole('button',{name:'Побудувати preview',exact:true}).click();
  await expect(page.getByText(/Каталог не змінено\./)).toBeVisible();
  assert.equal((await(await context.request.get('/api/v1/catalogue')).json()).total,before);
  await page.reload();
  await page.getByRole('button',{name:`${name} · Готово`,exact:true}).click();
  const apply=page.getByRole('button',{name:'Застосувати імпорт',exact:true});await expect(apply).toBeDisabled();
  await page.getByRole('checkbox',{name:/Підтверджую застосування/}).check();
  await apply.click();await expect(page.getByText(/Дані застосовано\./)).toBeVisible();
  assert.equal((await(await context.request.get('/api/v1/catalogue')).json()).total,before+1);
  // Ambiguous name: resolve explicitly, invalidate the old preview, then apply.
  await page.getByLabel('Файл каталогу').setInputFiles({name:`review-${viewport.width}.csv`,mimeType:'text/csv',buffer:csv(article+'-review','Комп',category)});
  await page.getByRole('button',{name:'Завантажити файл',exact:true}).click();
  await page.getByRole('button',{name:'Побудувати preview',exact:true}).click();
  const resolution=page.getByLabel(/^Рішення для Комп/);
  await expect(resolution).toBeVisible();
  const target=await resolution.locator('option').filter({hasText:'Об’єднати:'}).first().getAttribute('value');
  await resolution.selectOption(target);
  await expect(page.getByText('Рішення змінено — потрібен новий preview.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Застосувати імпорт',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Побудувати preview',exact:true}).click();
  await expect(page.getByText(/невирішених відповідностей: 0/)).toBeVisible();
  await page.getByRole('checkbox',{name:/Підтверджую застосування/}).check();
  await page.getByRole('button',{name:'Застосувати імпорт',exact:true}).click();
  await expect(page.getByText(/Дані застосовано\./)).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await fs.mkdir('test-results',{recursive:true});
  await page.screenshot({path:`test-results/catalogue-import-v2-${viewport.width}.png`,fullPage:true});
  await page.goto('/catalog');await page.getByText('Спільний каталог CarPot v2',{exact:true}).click();
  await page.getByLabel('Назва, OEM або артикул').fill(article);
  await expect(page.getByText('Пропозицій: 1',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Синтетичний передній бампер',exact:true})).toBeVisible();
  await fs.mkdir('test-results',{recursive:true});
  await page.screenshot({path:`test-results/catalogue-v2-${viewport.width}.png`,fullPage:true});
  assert.deepEqual(errors,[]);await context.close();
  console.log(`PASS catalogue v2 real backend: owner upload/preview/reload/explicit merge/apply/shared read ${viewport.width}px`);
 }
 // A different DIRECTOR cannot see the menu or use a direct admin URL.
 const context=await browser.newContext({baseURL:origin});
 const signup=await context.request.post('/api/v1/auth/register',{data:{email:`nonowner-${Date.now()}@example.test`,name:'Ordinary warehouse owner',password:'nonowner-browser-password'}});
 assert.equal(signup.status(),201);
 const page=await context.newPage();await page.goto('/administration/catalogue/import');
 await expect(page.getByRole('heading',{name:'Доступ обмежено',exact:true})).toBeVisible();
 await expect(page.getByRole('link',{name:'Адміністрування → Каталог → Імпорт',exact:true})).toHaveCount(0);
 assert.equal((await context.request.get('/api/v1/catalogue/admin/jobs')).status(),403);
 await context.close();console.log('PASS catalogue v2 non-platform DIRECTOR: hidden menu + direct API denied');
}finally{await browser.close();}
