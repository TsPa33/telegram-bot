// Deterministic HTTP fault scenarios against local production assets and real local owner auth.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local E2E opt-in required');
const origin=process.env.CATALOGUE_TEST_ORIGIN||'http://127.0.0.1:18770';
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Only loopback allowed');
const email=process.env.CATALOGUE_TEST_EMAIL,password=process.env.CATALOGUE_TEST_PASSWORD;
if(!email||!password)throw Error('Local owner fixture credentials required');
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  const context=await browser.newContext({baseURL:origin,viewport});
  assert.equal((await context.request.post('/api/v1/auth/login',{data:{email,password}})).status(),200);
  const id='SYNTHETIC-review-'+viewport.width,sha='a'.repeat(64),issues=Array.from({length:6},(_,i)=>({key:'synthetic-'+i,kind:'subcategory',name:'Вузол '+(i+1),reason:'Потрібна українська відповідність',allowed_actions:['create_name','target','skip'],candidates:[]}));
  let mode='review',posts=0,getFailures=0,sent={},checked={},token='old-token',opId='previous-op',applyCalls=0;
  function job(){
   return {id,filename:'Синтетичні шість відповідностей.zip',file_sha256:sha,format:'v2-zip',status:mode==='done'?'ready':'review',resolutions:checked,preview_token:token,
    report:{issues:mode==='done'?[]:issues,unresolved_total:mode==='done'?0:6,counts:{offers:{inserted:10222,updated:0,unchanged:0}},input_rows:29922,suggestion_total:9542,suggestions:[],committed:false},
    operation:{id:opId,kind:'preview',status:mode==='queued'?'running':mode==='error'?'error':'done',submitted_resolutions:sent,progress:{done:500,total:10222},error:mode==='error'?'Неприпустима назва у відповідності 2':null}};
  }
  await context.route('**/api/v1/catalogue/admin/**',async route=>{
   const request=route.request(),path=new URL(request.url()).pathname;
   if(path.endsWith('/apply')){applyCalls++;return route.fulfill({status:500,json:{detail:'Synthetic test forbids apply'}});}
   if(path.endsWith('/preview')){
    posts++;sent=request.postDataJSON().resolutions;opId='preview-'+posts;mode='queued';
    if(posts===2)return route.fulfill({status:504,json:{detail:'Шлюз не дочекався відповіді'}});
    return route.fulfill({status:202,json:job()}); // still old report/resolutions
   }
   if(path==='/api/v1/catalogue/admin/jobs')return route.fulfill({json:{items:[job()],total:1}});
   if(path==='/api/v1/catalogue/admin/jobs/'+id){
    if(getFailures>0){getFailures--;return route.fulfill({status:503,json:{detail:'Тимчасова помилка читання статусу'}});}
    return route.fulfill({json:job()});
   }
   return route.continue();
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/administration/catalogue/import');
  await page.getByRole('button',{name:/Синтетичні шість відповідностей/}).click();
  for(let i=0;i<6;i++){
   await page.getByLabel('Рішення для Вузол '+(i+1),{exact:true}).selectOption('create_name');
   await page.getByLabel('Український відповідник для Вузол '+(i+1),{exact:true}).fill('Українська назва '+(i+1));
   if(i===3)await expect(page.getByText(/Підтверджено 4 із 6/)).toBeVisible();
  }
  await page.getByRole('button',{name:'Зберегти чернетку',exact:true}).click();
  await expect(page.getByText(/Чернетку збережено в цій вкладці/)).toBeVisible();
  await page.getByRole('button',{name:'Перевірити рішення',exact:true}).click();
  await expect.poll(()=>posts).toBe(1);
  for(let i=0;i<6;i++)await expect(page.getByLabel('Український відповідник для Вузол '+(i+1),{exact:true})).toHaveValue('Українська назва '+(i+1));
  await expect(page.getByRole('region',{name:'Актуальний результат перевірки'})).not.toBeVisible();
  await expect(page.getByRole('button',{name:'Перевірити рішення',exact:true})).toBeDisabled();
  await page.reload();
  for(let i=0;i<6;i++)await expect(page.getByLabel('Український відповідник для Вузол '+(i+1),{exact:true})).toHaveValue('Українська назва '+(i+1));
  assert.equal(posts,1); // reload polls; never re-enqueues
  getFailures=5;
  await expect(page.getByText(/Не вдалося оновити статус: Тимчасова помилка/)).toBeVisible({timeout:6000});
  await expect(page.getByLabel('Український відповідник для Вузол 1',{exact:true})).toHaveValue('Українська назва 1');
  getFailures=0;checked=structuredClone(sent);token='ready-first';mode='done';
  await expect(page.getByRole('heading',{name:'Перевірку завершено: готово',exact:true})).toBeVisible({timeout:6000});
  await expect(page.getByText('Перевірено сервером',{exact:true})).toHaveCount(6);
  await expect(page.getByRole('button',{name:'Застосувати імпорт',exact:true})).not.toBeVisible();
  await page.getByRole('checkbox',{name:/Підтверджую застосування/}).check();
  await expect(page.getByRole('button',{name:'Застосувати імпорт',exact:true})).toBeVisible();
  await page.getByLabel('Український відповідник для Вузол 1',{exact:true}).fill('Виправлена українська назва');
  await expect(page.getByRole('button',{name:'Застосувати імпорт',exact:true})).not.toBeVisible();
  await expect(page.getByRole('region',{name:'Актуальний результат перевірки'})).not.toBeVisible();
  await page.getByRole('button',{name:'Перевірити рішення',exact:true}).click(); // 504 but command is accepted
  await expect.poll(()=>posts).toBe(2);
  await expect(page.getByRole('button',{name:'Перевірити рішення',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Український відповідник для Вузол 1',{exact:true})).toHaveValue('Виправлена українська назва');
  mode='error';
  await expect(page.getByText('Неприпустима назва у відповідності 2',{exact:true})).toBeVisible({timeout:6000});
  await page.reload();
  await expect(page.getByLabel('Український відповідник для Вузол 1',{exact:true})).toHaveValue('Виправлена українська назва');
  await expect(page.getByText('Неприпустима назва у відповідності 2',{exact:true})).toBeVisible();
  assert.equal(posts,2);assert.equal(applyCalls,0);
  await page.getByRole('button',{name:'Перевірити рішення',exact:true}).click();
  await expect.poll(()=>posts).toBe(3);
  checked=structuredClone(sent);token='ready-repeat';mode='done';
  await expect(page.getByRole('heading',{name:'Перевірку завершено: готово',exact:true})).toBeVisible({timeout:6000});
  assert.equal(await page.getByRole('checkbox',{name:/Підтверджую застосування/}).isChecked(),false);
  await expect(page.getByText(/Рекомендації: нові записи \(9542\) — необов’язкова перевірка/)).toBeVisible();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);assert.equal(applyCalls,0);
  await fs.mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/catalogue-review-${viewport.width}.png`,fullPage:true});
  // The real reported staging case: ready/done with six server resolutions,
  // but no browser draft from the previous frontend release. No new POST.
  await page.evaluate(()=>sessionStorage.clear());await page.reload();
  await page.getByRole('button',{name:/Синтетичні шість відповідностей/}).click();
  await expect(page.getByText('Перевірено сервером',{exact:true})).toHaveCount(6);
  await expect(page.getByLabel('Український відповідник для Збережена відповідність 1',{exact:true})).toHaveValue('Виправлена українська назва');
  assert.equal(posts,3);assert.equal(applyCalls,0);
  await context.close();console.log(`PASS ${viewport.width}: six drafts, old 202, polling/reload, API failure, 504, explicit retry, stale-apply guard; no apply`);
 }
}finally{await browser.close();}
