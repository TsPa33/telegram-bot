import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local DB required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Smart Search worker',email:`smart-${viewport.width}-${Date.now()}@example.test`,password:'local-smart-search-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC60',year:2016}),b=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2014});
 const records=[];for(const [name,vehicle,quantity] of [['Блок керування двигуном',v,1],['Блок керування двигуном BMW',b,1],['Задній ліхтар правий',v,1],['Задній ліхтар лівий',v,1],['Передні ліві двері',v,1],['Радіатор охолодження',v,1],['Капот',v,1],['Кардан',v,0]]){
  const p=await post('/parts',{name,vehicle_id:vehicle.id,selling_price:'123.45',currency:'USD',oem_number:name==='Капот'?'OEM-57-01':'',article_number:name==='Капот'?'ART-57-01':''});records.push(p);if(quantity)await post(`/parts/${p.id}/operations`,{type:'receipt',quantity,reason:'Local Smart Search fixture'});
 }
 let smartRequests=0;page.on('request',r=>{if(r.url().includes('/smart-search/parts?')){smartRequests++;const u=new URL(r.url());assert(Number(u.searchParams.get('limit'))<=100);}});
 await page.route('**/api/v1/smart-search/readiness',route=>route.fulfill({status:404,json:{detail:'Old backend'}}));await page.goto(origin+'/');await expect(page.getByRole('button',{name:'Розумний пошук',exact:true})).toBeDisabled();assert.equal(smartRequests,0);await expect(page.getByRole('button',{name:'Перевірити пошук'})).toBeVisible();
 // Standard search stays usable while the Smart backend is unavailable.
 await page.getByRole('combobox',{name:'Пошук запчастин',exact:true}).fill('Капот');
 await expect(page.locator('.desktop-table:visible tbody tr,.seller-card:visible')).toHaveCount(1);
 const good={status:'ready',contract_version:8,required_revision:'a73e05b9c842',database_revisions:['a73e05b9c842'],features:['tenant_ranked_parts','direction_constraints','dictionary_aliases','bounded_typo_search']};
 await page.unroute('**/api/v1/smart-search/readiness');
 const bad=[
  {status:503,json:{detail:'Not ready'}},{status:200,json:null},{status:201,json:good},{status:200,json:{...good,status:'starting'}},
  {status:200,json:{...good,contract_version:7}},{status:200,json:{...good,required_revision:'d86f21a90b34'}},
  ...[undefined,[],['unknown'],['a73e05b9c842','unknown'],['a73e05b9c842','d86f21a90b34'],['a73e05b9c842','a73e05b9c842']].map(database_revisions=>({status:200,json:{...good,database_revisions}})),
  ...good.features.map(f=>({status:200,json:{...good,features:good.features.filter(x=>x!==f)}})),
  {network:true}
 ];
 for(const response of bad){
  await page.route('**/api/v1/smart-search/readiness',route=>response.network?route.abort('failed'):route.fulfill(response));
  await page.getByRole('button',{name:'Перевірити пошук'}).click();
  await expect(page.getByRole('button',{name:'Перевірити пошук'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Розумний пошук',exact:true})).toBeDisabled();
  assert.equal(smartRequests,0);await page.unroute('**/api/v1/smart-search/readiness');
 }
 await page.getByRole('button',{name:'Перевірити пошук'}).click();const mode=page.getByRole('button',{name:'Розумний пошук',exact:true});await expect(mode).toBeEnabled();await mode.click();
 const input=page.getByRole('combobox',{name:'Пошук запчастин',exact:true}),results=page.getByRole('region',{name:'Результати пошуку'});
 const visibleNames=()=>results.locator('.desktop-table:visible tbody tr, .seller-card:visible');
 await input.fill('мозги мотора XC60');await expect(visibleNames()).toHaveCount(1);await expect(results).toContainText('Блок керування двигуном');await expect(results).toContainText('Збіг за словником');await expect(visibleNames()).not.toContainText('BMW');
 await fs.mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/smart-search-${viewport.width}.png`,fullPage:true});
 // Keyboard opens the existing real Part detail with unchanged Workshop actions.
 await input.press('ArrowDown');await input.press('Enter');let detail=page.getByRole('dialog',{name:'Блок керування двигуном',exact:true});await expect(detail).toBeVisible();for(const name of ['Продати','Додати нотатку','Змінити ціну','Оформити замовлення'])await expect(detail.getByRole('button',{name,exact:true})).toBeVisible();await detail.getByRole('button',{name:'Закрити',exact:true}).click();
 for(const [q,name] of [['правий задній стоп','Задній ліхтар правий'],['лівий задній стоп','Задній ліхтар лівий'],['передня ліва дверка','Передні ліві двері'],['radik volvo','Радіатор охолодження'],['капотт','Капот'],['OEM-57-01','Капот'],['ART-57-01','Капот']]){await input.fill(q);await expect(visibleNames()).toHaveCount(1);await expect(visibleNames()).toContainText(name);}
 await input.fill('невідома вигадана назва');await expect(visibleNames()).toHaveCount(0);await expect(page.getByRole('heading',{name:'Нічого не знайдено',exact:true})).toBeVisible();
 await input.fill('стоп');await expect(page.getByRole('status').filter({hasText:'Уточніть'})).toBeVisible();await expect(visibleNames()).toHaveCount(0);
 await input.fill('Кардан');await expect(visibleNames()).toHaveCount(0);await page.getByRole('switch',{name:'Показати без залишку',exact:true}).check();await expect(visibleNames()).toHaveCount(1);await expect(visibleNames().getByRole('button',{name:'Продати',exact:true})).toBeDisabled();
 await input.fill('радік');await expect(visibleNames()).toHaveCount(1);let release;const gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/v1/smart-search/parts?*',async route=>{if(new URL(route.request().url()).searchParams.get('q')==='мозги мотора'){const response=await route.fetch();await gate;await route.fulfill({response});}else await route.continue();});
 const staleResponse=page.waitForResponse(r=>r.url().includes('/smart-search/parts?')&&new URL(r.url()).searchParams.get('q')==='мозги мотора');
 const sent=page.waitForRequest(r=>r.url().includes('/smart-search/parts?')&&new URL(r.url()).searchParams.get('q')==='мозги мотора');await input.fill('мозги мотора');await sent;await input.fill('правий задній стоп');await expect(visibleNames()).toHaveCount(1);await expect(visibleNames()).toContainText('Задній ліхтар правий');release();await staleResponse;await expect(visibleNames()).toContainText('Задній ліхтар правий');await page.unroute('**/api/v1/smart-search/parts?*');
 await page.route('**/api/v1/smart-search/parts?*',route=>route.fulfill({status:503,json:{detail:'Пошук перевищив ліміт часу. Уточніть запит.'}}));
 await input.fill('складний запит');await expect(page.getByRole('alert')).toContainText('Уточніть запит');await expect(visibleNames()).toHaveCount(0);
 await page.unroute('**/api/v1/smart-search/parts?*');await page.getByRole('button',{name:'Повторити пошук',exact:true}).click();await expect(page.getByRole('alert')).toHaveCount(0);
 await page.route('**/api/v1/smart-search/parts?*',route=>route.abort('failed'));await input.fill('помилка мережі');await expect(page.getByRole('alert')).toBeVisible();await expect(visibleNames()).toHaveCount(0);await page.unroute('**/api/v1/smart-search/parts?*');await page.getByRole('button',{name:'Очистити пошук',exact:true}).click();await expect(input).toHaveValue('');
 await page.getByRole('combobox',{name:'Автомобіль пошуку',exact:true}).selectOption(v.id);await page.getByRole('button',{name:'Звичайний пошук',exact:true}).click();await expect(page.getByRole('combobox',{name:'Автомобіль пошуку',exact:true})).toHaveValue(v.id);
 // Existing priced sale from a Smart result must use the same ledger operation.
 await page.getByRole('button',{name:'Розумний пошук',exact:true}).click();await input.fill('OEM-57-01');await expect(visibleNames()).toHaveCount(1);
 const hood=records.find(p=>p.name==='Капот');let saleCalls=0;
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith(`/parts/${hood.id}/operations`))saleCalls++;});
 await visibleNames().getByRole('button',{name:'Продати',exact:true}).click();const sale=page.getByRole('dialog',{name:'Продати: Капот',exact:true});
 await sale.getByLabel('Фактична ціна продажу',{exact:true}).fill('99.09');await sale.getByRole('button',{name:'Підтвердити',exact:true}).evaluate(b=>{b.click();b.click();});
 await expect(sale).not.toBeVisible();assert.equal(saleCalls,1);assert.equal((await (await context.request.get(origin+`/api/v1/parts/${hood.id}`)).json()).quantity,0);
 await expect(visibleNames()).toHaveCount(1);await expect(visibleNames().getByRole('button',{name:'Продати',exact:true})).toBeDisabled();
 // Pagination uses real server rows; filters survive a page change.
 for(let i=0;i<53;i++){
  const p=await post('/parts',{name:`Стартер пагінації ${i}`,vehicle_id:v.id,selling_price:'12.01',currency:'UAH'});
  await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:1,reason:'Local pagination fixture'});
 }
 await input.fill('Стартер пагінації');await expect(visibleNames()).toHaveCount(50);
 const first=await visibleNames().getByRole('button',{name:/^Стартер пагінації/}).allTextContents();
 await page.getByRole('button',{name:'Наступна сторінка',exact:true}).click();await expect(visibleNames()).toHaveCount(3);
 const next=await visibleNames().getByRole('button',{name:/^Стартер пагінації/}).allTextContents();assert(next.every(n=>!first.includes(n)));
 await expect(page.getByRole('combobox',{name:'Автомобіль пошуку',exact:true})).toHaveValue(v.id);
 await page.getByRole('button',{name:'Попередня сторінка',exact:true}).click();await expect(visibleNames()).toHaveCount(50);
 assert.deepEqual(await visibleNames().getByRole('button',{name:/^Стартер пагінації/}).allTextContents(),first);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 const countBefore401=smartRequests;
 await page.route('**/api/v1/smart-search/readiness',route=>route.fulfill({status:401,json:{detail:'Unauthorized'}}));await page.reload();
 await expect(page.getByRole('button',{name:'Увійти',exact:true})).toBeVisible();assert.equal(smartRequests,countBefore401);await context.close();console.log(`PASS Smart Search real records, donor/side/OEM, legacy switch, keyboard, stale/network, zero-stock ${viewport.width}`);
}}finally{await browser.close();}
