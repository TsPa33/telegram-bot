import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local test DB required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Workshop worker',email:`workshop-${viewport.width}-${Date.now()}@example.test`,password:'local-workshop-long-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),p=await post('/parts',{vehicle_id:v.id,name:'Фара майстерні',selling_price:'100.25',currency:'UAH',oem_number:'OEM56',article_number:'ART56',location:'A-01'});
 await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:2,reason:'Local test stock'});
 const state=async()=> (await context.request.get(origin+`/api/v1/parts/${p.id}`,{headers:{'X-Warehouse-Client':'5'}})).json();
 // Simulate frontend finishing Auto Deploy before backend: never expose new
 // actions on 404, wrong contract, wrong schema or incomplete capabilities.
 const readiness='**/api/v1/workshop/readiness',blockedGate=page.getByRole('region',{name:'Оновлення майстерні'});
 let readinessBody=null,readinessStatus=404;
 await page.route(readiness,route=>route.fulfill({status:readinessStatus,json:readinessBody||{detail:'Not found'}}));
 await page.goto(origin+'/inventory');await expect(blockedGate.getByRole('button',{name:'Перевірити готовність'})).toBeEnabled();await expect(page.getByRole('button',{name:'Продати',exact:true})).toHaveCount(0);
 for(const body of [
  {status:'ready',contract_version:6,database_revisions:['d86f21a90b34'],features:[]},
  {status:'ready',contract_version:7,database_revisions:['old'],features:[]},
  {status:'ready',contract_version:7,database_revisions:['d86f21a90b34'],features:['actual_quick_sale_price']}
 ]){readinessStatus=200;readinessBody=body;await blockedGate.getByRole('button',{name:'Перевірити готовність'}).click();await expect(blockedGate.getByRole('button',{name:'Перевірити готовність'})).toBeEnabled();await expect(page.getByRole('button',{name:'Продати',exact:true})).toHaveCount(0);}
 await page.unroute(readiness);await blockedGate.getByRole('button',{name:'Перевірити готовність'}).click();await expect(blockedGate).toHaveCount(0);
 await page.getByRole('button',{name:p.name,exact:true}).filter({visible:true}).first().click();
 const detail=page.getByRole('dialog',{name:p.name,exact:true});await expect(detail.getByRole('button',{name:'Продати',exact:true})).toBeVisible();
 for(const name of ['Зарезервувати','Перемістити','Списати'])await expect(detail.getByRole('button',{name,exact:true})).not.toBeVisible();
 await detail.getByRole('button',{name:'Додати нотатку',exact:true}).click();let modal=page.getByRole('dialog',{name:`Нотатка: ${p.name}`,exact:true});await modal.getByLabel('Внутрішня нотатка',{exact:true}).fill('Подряпина на корпусі');await modal.getByRole('button',{name:'Зберегти нотатку'}).click();await expect(detail).toContainText('Подряпина на корпусі');
 // Concurrent edit must remain on server, and attempted local text remains visible.
 await detail.getByRole('button',{name:'Додати нотатку',exact:true}).click();modal=page.getByRole('dialog',{name:`Нотатка: ${p.name}`,exact:true});
 const remote=await context.request.patch(origin+`/api/v1/parts/${p.id}/notes`,{headers,data:{internal_notes:'Інший працівник оновив',expected_notes:'Подряпина на корпусі'}});assert(remote.ok());
 await modal.getByLabel('Внутрішня нотатка',{exact:true}).fill('Моя зміна');await modal.getByRole('button',{name:'Зберегти нотатку'}).click();await expect(modal.getByRole('alert')).toContainText('вже змінено');assert.equal((await state()).internal_notes,'Інший працівник оновив');await modal.getByRole('button',{name:'Закрити',exact:true}).click();
 await detail.getByText('Ще',{exact:true}).click();await detail.getByRole('button',{name:'Стан і перевірка',exact:true}).click();modal=page.getByRole('dialog',{name:`Стан і перевірка: ${p.name}`,exact:true});await modal.getByLabel('Фізичний стан',{exact:true}).selectOption('damaged');await modal.getByRole('button',{name:'Зберегти стан'}).click();assert.equal((await state()).quantity,2);await expect(detail).toContainText('Пошкоджена');
 await detail.getByRole('button',{name:'Змінити ціну',exact:true}).click();modal=page.getByRole('dialog',{name:'Ціна запчастини',exact:true});await modal.getByLabel('Сума',{exact:true}).fill('20.09');await modal.getByLabel('Валюта',{exact:true}).selectOption('USD');await modal.getByRole('button',{name:'Зберегти',exact:true}).click();await expect(detail).toContainText('20,09');
 await fs.mkdir('test-results',{recursive:true});await detail.getByText('Ще',{exact:true}).click();await page.screenshot({path:`test-results/workshop-card-${viewport.width}.png`,fullPage:false});
 // A lost success response plus double click must create exactly one priced sale.
 const pattern=`**/api/v1/parts/${p.id}/operations`;let requests=0,firstKey;
 await page.route(pattern,async route=>{requests++;firstKey=route.request().postDataJSON().request_key;await route.fetch();await route.abort('failed');});
 await detail.getByRole('button',{name:'Продати',exact:true}).click();modal=page.getByRole('dialog',{name:`Продати: ${p.name}`,exact:true});await modal.getByLabel('Фактична ціна продажу',{exact:true}).fill('15,07');await modal.getByRole('button',{name:'Підтвердити',exact:true}).evaluate(b=>{b.click();b.click();});await expect(modal.getByRole('alert')).toBeVisible();assert.equal(requests,1);assert.equal((await state()).quantity,1);
 await page.unroute(pattern);await page.reload();await page.getByRole('button',{name:'Перевірити: Продати',exact:true}).click();modal=page.getByRole('dialog',{name:`Продати: ${p.name}`,exact:true});await expect(modal.getByLabel('Фактична ціна продажу',{exact:true})).toHaveValue('15,07'.replace(',','.')); // normalized exact replay
 let replayKey;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith(`/parts/${p.id}/operations`))replayKey=r.postDataJSON().request_key;});await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();assert.equal(replayKey,firstKey);assert.equal((await state()).quantity,1);
 // Last unit remains in records and cannot be sold twice.
 const row=page.locator('.desktop-table:visible tbody tr, .seller-card:visible').filter({has:page.getByRole('button',{name:p.name,exact:true})});await row.getByRole('button',{name:'Продати',exact:true}).click();modal=page.getByRole('dialog',{name:`Продати: ${p.name}`,exact:true});await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();assert.equal((await state()).quantity,0);
 await page.getByRole('switch',{name:'Показати без залишку',exact:true}).check();await expect(row).toBeVisible();await expect(row.getByRole('button',{name:'Продати',exact:true})).toBeDisabled();
 await row.getByRole('button',{name:`Дії ${p.name}`,exact:true}).click();await row.getByRole('button',{name:'Архівувати',exact:true}).click();modal=page.getByRole('dialog',{name:'Архівувати запчастину?',exact:true});await expect(modal).toContainText('не продаж');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect.poll(async()=>(await state()).archived).toBe(true);
 await page.goto(origin+'/sales');await expect(page.getByRole('region',{name:'Фактичні продажі'}).locator('article')).toHaveCount(2);await expect(page.getByRole('region',{name:'Фактичні продажі'})).toContainText('15,07');await expect(page.getByRole('region',{name:'Фактичні продажі'})).toContainText('20,09');
 await page.getByLabel('Пошук продажів',{exact:true}).fill('ART56');await expect(page.getByRole('region',{name:'Фактичні продажі'}).locator('article')).toHaveCount(2);await page.getByLabel('Джерело продажів',{exact:true}).selectOption('order');await expect(page.getByText('Продажів не знайдено',{exact:true})).toBeVisible();await page.getByLabel('Джерело продажів',{exact:true}).selectOption('quick');await expect(page.getByRole('region',{name:'Фактичні продажі'}).locator('article')).toHaveCount(2);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:`test-results/workshop-sales-${viewport.width}.png`,fullPage:true});assert.deepEqual(errors,[]);
 const blocked=await post('/parts',{name:'Непідтверджений запит',selling_price:'1.00'});await post(`/parts/${blocked.id}/operations`,{type:'receipt',quantity:1,reason:'Local blocked fixture'});
 await page.evaluate(({account,id})=>sessionStorage.setItem(`warehouse-stock-pending:${account}:${id}:sale`,'{invalid'),{account:blocked.account_id,id:blocked.id});await page.goto(origin+'/inventory');
 const blockedRow=page.locator('.desktop-table:visible tbody tr, .seller-card:visible').filter({has:page.getByRole('button',{name:blocked.name,exact:true})});await blockedRow.getByRole('button',{name:'Продати',exact:true}).click();const blockedDialog=page.getByRole('dialog',{name:`Продати: ${blocked.name}`,exact:true});await expect(blockedDialog.getByRole('alert')).toContainText('заблоковано');await expect(blockedDialog.getByRole('button',{name:'Підтвердити',exact:true})).toBeDisabled();
 assert.equal((await (await context.request.get(origin+`/api/v1/parts/${blocked.id}`)).json()).quantity,1);
 await context.close();console.log(`PASS workshop priced sales/replay/last-unit/notes-conflict/damage/price/archive/ledger ${viewport.width}`);
}}finally{await browser.close();}
