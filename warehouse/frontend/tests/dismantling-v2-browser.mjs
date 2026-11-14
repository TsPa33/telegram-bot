// Real auth/API/PostgreSQL and production build. Only failures/delivery timing are injected.
import {chromium,expect} from '@playwright/test';import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Isolated local only');
const dir=process.env.DV2_OUTPUT||'/tmp/dv2-browser';fs.mkdirSync(dir,{recursive:true});
const executablePath=process.env.WAREHOUSE_CHROMIUM_PATH||(!process.env.CI&&fs.existsSync('/usr/bin/chromium')?'/usr/bin/chromium':undefined);
const browser=await chromium.launch({...(executablePath?{executablePath}:{}),args:['--no-sandbox']});
try{
 const c=await browser.newContext({baseURL:'http://127.0.0.1:5260',viewport:{width:1440,height:1000}});
 const reg=await c.request.post('/api/v1/auth/register',{data:{name:'Dismantling V2 QA',email:`dv2-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(reg.status(),201);const auth=await reg.json();
 const post=async(path,data)=>{const r=await c.request.post('/api/v1'+path,{data,headers:{'X-CSRF-Token':auth.csrf_token}});assert.ok(r.ok(),path+' '+await r.text());return r.json()};
 const get=async(path)=>{const r=await c.request.get('/api/v1'+path,{headers:{'X-Warehouse-Client':'5'}});assert.ok(r.ok(),path);return r.json()};
 const page=await c.newPage();page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));const vehicles=[];
 async function shot(name){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'No horizontal page overflow: '+name);await page.screenshot({path:`${dir}/${name}.png`,animations:'disabled'});}
 for(const [index,maker,model] of [[0,'PEUGEOT','5008 QA'],[1,'Renault','ZOE QA'],[2,'Volkswagen','Golf QA']]){
  const v=await post('/vehicles',{manufacturer:maker,model,year:2020});vehicles.push(v);await page.goto('/vehicles?donor='+v.id);
  await expect(page.getByRole('button',{name:'Розібрати на запчастини',exact:true})).toBeVisible();assert.equal(await page.locator('.assembly-workspace').count(),0,'No empty workbench');assert.equal(await page.locator('.managed-bulk-bar').count(),0);
  for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();if(index===0)await shot(`start-${theme==='День'?'light':'dark'}-${width}`);}
  await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'День',exact:true}).click();
  if(index===0){await page.route(`**/vehicles/${v.id}/dismantling-v3/preview`,async route=>{await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Контрольний локальний збій. Повторіть спробу.'})})});await page.getByRole('button',{name:'Розібрати на запчастини',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Повторіть');}
  let release;const gate=new Promise(r=>release=r);let calls=0;const pattern=`**/vehicles/${v.id}/dismantling-v3/preview`;
  await page.route(pattern,async route=>{calls++;await gate;await route.continue()});
  await page.getByRole('button',{name:'Розібрати на запчастини',exact:true}).evaluate(b=>{b.click();b.click()});await expect(page.getByRole('progressbar')).toBeVisible();if(index===0){for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();await shot(`generating-${theme==='День'?'light':'dark'}-${width}`);}}else await shot(`generating-${index}`);release();
  await expect(page.getByRole('heading',{name:'Каталог автомобіля готовий',exact:true})).toBeVisible();await page.unroute(pattern);assert.equal(calls,1,'Repeated clicks create one generation');assert.equal((await get(`/parts?vehicle_id=${v.id}&limit=1`)).total,0);
  if(index===0)for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();await shot(`result-${theme==='День'?'light':'dark'}-${width}`);}
  await page.getByRole('button',{name:'Переглянути результати',exact:true}).click();await expect(page.locator('.assembly-workspace')).toBeVisible();
  await page.reload();await expect(page.locator('.assembly-workspace')).toBeVisible();const visiblePlan=await get(`/vehicles/${v.id}/dismantling-v3`);assert.equal(visiblePlan.total,227);assert.equal(Object.hasOwn(visiblePlan.generator,'baseline_positions'),false,'Source counts private on API');
 }
 const path=v=>`/vehicles/${v.id}/dismantling-v3`;
 async function selectIds(v,ids){await page.goto('/vehicles?donor='+v.id);await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Список',exact:true}).click();for(const id of ids){const button=page.locator(`[id="assembly-node-${id}"]`);while(!await button.count()){await page.getByRole('button',{name:'Показати ще 50 позицій',exact:true}).click();}await button.locator('..').getByRole('checkbox').check();}}
 async function receipt(){await page.getByRole('button',{name:'Додати вибрані на склад',exact:true}).click();const d=page.getByRole('dialog').last();await expect(d.getByRole('heading',{name:'Додати на склад',exact:true})).toBeVisible();return d;}
 async function confirm(d,n){await d.getByRole('checkbox',{name:new RegExp(`Підтверджую фактичну наявність, демонтаж і надходження ${n} `)}).check();}
 // Five unchecked: one confirmation, edit quantity, preserve category/search/selected card.
 const v=vehicles[0],items=(await get(path(v))).items;const ids=items.slice(0,5).map(i=>i.id);await selectIds(v,ids);
 await page.locator(`[id="assembly-node-${ids[0]}"]`).click();const card=page.getByRole('region',{name:'Картка запчастини',exact:true});await expect(card).toBeVisible();await page.locator('.assembly-categories summary button').filter({hasText:items[0].category}).first().click();await page.getByRole('textbox',{name:'Пошук у дереві',exact:true}).fill('Гальм');
 for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();await shot(`work-selected-${theme==='День'?'light':'dark'}-${width}`);}await page.setViewportSize({width:1440,height:1000});
 const d=await receipt();await expect(d.getByRole('button',{name:'Додати 5 деталей на склад',exact:true})).toBeDisabled();await d.getByText('Переглянути деталі та уточнити кількість (5)',{exact:true}).click();await d.getByRole('spinbutton').first().fill('3');await d.getByText('Переглянути деталі та уточнити кількість (5)',{exact:true}).click();await confirm(d,5);
 for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('dialog').evaluate(el=>el.scrollTop=0); // modal is the only overlay; theme is applied through the same persisted app setting
   await page.evaluate(t=>{localStorage.setItem('warehouse.theme',t);window.dispatchEvent(new StorageEvent('storage',{key:'warehouse.theme',newValue:t,storageArea:localStorage}))},theme==='День'?'light':'dark');await shot(`receipt-five-${theme==='День'?'light':'dark'}-${width}`);}
 await page.setViewportSize({width:1440,height:1000});await d.getByRole('button',{name:'Додати 5 деталей на склад',exact:true}).click();await expect(d).not.toBeVisible();await expect(page.getByRole('status').filter({hasText:'Додано на склад: 5'})).toBeVisible();await expect(card).toBeVisible();await expect(card.locator('.assembly-stock-label')).toContainText('На складі');for(const theme of ['День','Ніч'])for(const width of [1440,1920,390]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:theme,exact:true}).click();await shot(`receipt-done-${theme==='День'?'light':'dark'}-${width}`);}await page.setViewportSize({width:1440,height:1000});
 await expect(page.getByRole('textbox',{name:'Пошук у дереві',exact:true})).toHaveValue('Гальм');await expect(page.locator('.assembly-categories summary button').filter({hasText:items[0].category}).first()).toHaveAttribute('aria-pressed','true');let stock=await get(`/parts?vehicle_id=${v.id}&limit=200`);assert.equal(stock.total,5);assert.equal(stock.items.reduce((n,p)=>n+p.quantity,0),7);await page.reload();assert.equal((await get(`/parts?vehicle_id=${v.id}&limit=1`)).total,5);await shot('five-after-reload');
 // Mixed selection: unknown, present, damaged, excluded, absent, already received, sold.
 const mixed=vehicles[2],mi=(await get(path(mixed))).items.slice(0,7),mids=mi.map(i=>i.id);
 async function bulk(v,ids,action,extra={}){const p=await post(path(v)+'/bulk/preview',{ids,action,...(action==='receipt'?{confirm_physical:true}:{})});return post(path(v)+'/bulk',{ids,action,etag:p.etag,request_key:crypto.randomUUID(),confirm:action==='receipt'||action==='dismantled',reason:'Ізольована QA перевірка',...(action==='receipt'?{confirm_physical:true,preview_token:p.preview_token,lines:p.eligible_ids.map(id=>({id,quantity:1,confirm_physical:true}))}:{}),...extra});}
 const received=await bulk(mixed,[mids[0],mids[5]],'receipt');const bound=(await get(path(mixed))).items;const soldId=bound.find(i=>i.id===mids[5]).part_id;await post(`/parts/${soldId}/operations`,{type:'sale',quantity:1,sale_price:'1.00',sale_currency:'UAH',request_key:crypto.randomUUID()});
 await bulk(mixed,[mids[1]],'present');await bulk(mixed,[mids[2]],'absent');await bulk(mixed,[mids[4]],'exclude');const preview=await get(`/vehicles/${mixed.id}/assemblies/${mids[3]}/preview`);await post(`/vehicles/${mixed.id}/assemblies`,{action:'inspect',item_id:mids[3],token:preview.token,presence:'damaged',quantity:1,note:'QA damaged state',request_key:crypto.randomUUID()});
 await selectIds(mixed,mids);const md=await receipt();await expect(md).toContainText('До надходження після підтвердження: 3');await confirm(md,3);await md.getByRole('button',{name:'Додати 3 деталей на склад',exact:true}).click();await expect(md).not.toBeVisible();stock=await get(`/parts?vehicle_id=${mixed.id}&limit=200`);assert.equal(stock.total,5);assert.equal(stock.items.find(p=>p.id===soldId).quantity,0);assert.ok(stock.items.some(p=>p.condition==='damaged'));await shot('mixed-result');
 // 227 positions; lose the already-committed second response, reload, replay exact key.
 const large=vehicles[1];await page.goto('/vehicles?donor='+large.id);await page.getByRole('checkbox',{name:'Вибрати всі за поточними фільтрами',exact:true}).check();const ld=await receipt();await confirm(ld,227);let responses=0;let lost=false;
 const bulkPattern=`**/vehicles/${large.id}/dismantling-v3/bulk`;let releaseFirst,releaseSecond;const firstGate=new Promise(r=>{releaseFirst=r}),secondGate=new Promise(r=>{releaseSecond=r});
 await page.route(bulkPattern,async route=>{responses++;if(responses===1){await firstGate;await route.continue()}else if(responses===2){await secondGate;const r=await route.fetch();assert.equal(r.status(),200);lost=true;await route.abort('failed')}else await route.continue()});
 try{
   await ld.getByRole('button',{name:'Додати 227 деталей на склад',exact:true}).click();
   const progress=ld.getByRole('progressbar');
   await expect(progress).toBeVisible();
   await expect(progress).toHaveAttribute('aria-valuenow','0');
   await expect(progress).toHaveAttribute('aria-valuemax','227');
   await expect(ld.getByRole('button',{name:'Додаємо на склад…',exact:true})).toBeDisabled();
   await expect(ld.locator('.wh-operation-spinner').first()).toBeVisible();
   await shot('receipt-live-progress-zero');
   releaseFirst();
   await expect(progress).toHaveAttribute('aria-valuenow','100',{timeout:60000});
   await expect(ld).toContainText('Оброблено: 100 / 227');
   await expect(ld).toContainText('Додано: 100');
   await shot('receipt-live-progress-100');
 }finally{releaseFirst();releaseSecond();}
 await expect(ld.getByRole('alert')).toBeVisible();
 await expect(ld.getByRole('progressbar')).toHaveAttribute('aria-valuenow','100');
 await expect(ld).toContainText('Операцію призупинено');
 await expect(ld.locator('.wh-operation-spinner')).toHaveCount(0);assert.ok(lost);assert.equal((await get(`/parts?vehicle_id=${large.id}&limit=1`)).total,200);await shot('large-response-lost');await page.unroute(bulkPattern);await page.reload();await page.getByRole('button',{name:'Продовжити надходження',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Додано на склад: 227'})).toBeVisible({timeout:60000});assert.equal((await get(`/parts?vehicle_id=${large.id}&limit=1`)).total,227);await page.reload();assert.equal((await get(`/parts?vehicle_id=${large.id}&limit=1`)).total,227);await shot('large-227-complete');await page.getByRole('checkbox',{name:'Вибрати всі за поточними фільтрами',exact:true}).check();const repeat=await receipt();await expect(repeat).toContainText('немає доступних до надходження');assert.equal(await repeat.getByRole('button',{name:/Додати 0/}).count(),0);await repeat.getByRole('button',{name:'Повернутися до деталей',exact:true}).click();
 // Guarded physical assemblies: local fixture, one root, reference-only children, qty6 blocked.
 const cc=await browser.newContext({baseURL:'http://127.0.0.1:5260',viewport:{width:1440,height:1000}});const cr=await cc.request.post('/api/v1/auth/register',{data:{name:'Assembly QA',email:`dv2-assembly-${crypto.randomUUID()}@example.test`,password:'synthetic-test-only-password'}});assert.equal(cr.status(),201);const ca=await cr.json();const seed=await cc.request.post('http://127.0.0.1:8060/__dv2_fixture',{headers:{'X-CSRF-Token':ca.csrf_token,Cookie:(await cc.cookies()).map(v=>`${v.name}=${v.value}`).join('; ')}});assert.equal(seed.status(),200);const f=await seed.json();const assemblyPage=await cc.newPage();await assemblyPage.goto('/vehicles?donor='+f.vehicle_id);
 for(const row of f.rows.filter(n=>[1,6].includes(n.quantity)&&/Бампер/.test(n.name))){await assemblyPage.locator(`[id="assembly-node-${row.id}"]`).click();const panel=assemblyPage.getByRole('region',{name:'Картка запчастини',exact:true});await panel.locator('.assembly-physical-split summary').click();if(row.quantity===6)await expect(panel).toContainText('один фізичний вузол');else await expect(panel.locator('.assembly-split-row').first()).toBeVisible();await assemblyPage.screenshot({path:`${dir}/assembly-quantity-${row.quantity}.png`,animations:'disabled'});await panel.getByRole('button',{name:'Закрити картку',exact:true}).click();}
 assert.equal((await c.request.get('/api/v1'+path(vehicles[0])+'/sources')).status(),403);assert.equal(await page.getByText('Джерела підбору',{exact:true}).count(),0);
 // Integrated flow: sell TWO of the same actual Parts received above, not separately seeded SKUs.
 const actual=(await get(`/parts?vehicle_id=${v.id}&limit=200`)).items;
 const actualTree=(await get(`/vehicles/${v.id}/assemblies`)).items;
 const sellable=actual.filter(part=>part.available_quantity>0&&actual.filter(other=>other.name===part.name).length===1&&actualTree.some(node=>node.part_id===part.id&&!node.parent_id&&!node.completeness&&!node.consumed_operation_id));
 assert.ok(sellable.length>=2,'Two distinct, received, standalone Parts required');
 const [first,second]=sellable;
 const buyer=await post('/buyers',{name:'DV2 Integrated Buyer',phone:'0509998877'});
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'День',exact:true}).click();
 await page.goto('/inventory?vehicle_id='+v.id);
 const firstRow=page.locator('article.ui3-part').filter({has:page.getByRole('button',{name:'Дії '+first.name,exact:true})});
 await firstRow.getByRole('button',{name:'Дії '+first.name,exact:true}).click();
 await page.getByRole('menuitem',{name:'Оформити замовлення',exact:true}).click();
 const checkoutDialog=page.getByRole('dialog',{name:'Оформити замовлення'});
 await expect(checkoutDialog.getByRole('heading',{name:'Кошик · 1 позицій',exact:true})).toBeVisible();
 await checkoutDialog.getByRole('button',{name:'+ Додати товар',exact:true}).click();
 const picker=checkoutDialog.getByRole('region',{name:'Пошук для замовлення'});
 await picker.getByRole('combobox',{name:'Автомобіль для замовлення'}).selectOption(v.id);
 await picker.getByRole('searchbox',{name:'Пошук позицій замовлення'}).fill(second.name);
 await picker.locator('.order-picker-results').getByText(second.name,{exact:true}).click();
 await expect(checkoutDialog.locator('.order-line-editor')).toHaveCount(2);
 await checkoutDialog.getByLabel('Погоджена ціна '+first.name,{exact:true}).fill('125.50');
 await checkoutDialog.getByLabel('Погоджена ціна '+second.name,{exact:true}).fill('80.25');
 await checkoutDialog.getByRole('textbox',{name:'Телефон покупця',exact:true}).fill(buyer.phone);
 await checkoutDialog.getByRole('button',{name:/DV2 Integrated Buyer/}).click();
 await checkoutDialog.getByRole('combobox',{name:'Дія з замовленням'}).selectOption('sell');
 await checkoutDialog.getByRole('checkbox',{name:'Підтверджую продаж і списання всіх позицій',exact:true}).check();
 const checkoutResponse=page.waitForResponse(response=>response.url().endsWith('/api/v1/orders/checkout')&&response.request().method()==='POST');
 await shot('integrated-checkout');
 await checkoutDialog.getByRole('button',{name:'Підтвердити продаж',exact:true}).click();
 const response=await checkoutResponse;assert.equal(response.status(),201,await response.text());
 const order=await response.json();assert.ok(order.sold_at);assert.deepEqual(order.totals_by_currency,{UAH:'205.75'});
 assert.deepEqual(order.lines.map(line=>line.part_id).sort(),[first.id,second.id].sort());
 await expect(page.getByRole('heading',{name:'Замовлення №'+order.number,exact:true})).toBeVisible();
 // Exact request replay must recover the same order without creating a second sale.
 const replay=await post('/orders/checkout',response.request().postDataJSON());assert.equal(replay.id,order.id);
 for(const original of [first,second])assert.equal((await get('/parts/'+original.id)).quantity,original.quantity-1);
 const salesBefore=(await get('/audit?type=sale&vehicle_id='+v.id+'&limit=200')).items;
 assert.equal(salesBefore.length,2);assert.ok(salesBefore.every(op=>op.after.sale.order_id===order.id));
 await page.getByRole('button',{name:'Підтвердити передачу покупцеві',exact:true}).click();
 await page.getByRole('dialog',{name:'Покупець отримав замовлення?',exact:true}).getByRole('button',{name:'Підтвердити',exact:true}).click();
 await expect(page.getByText('Завершено',{exact:true})).toBeVisible();
 assert.equal((await get('/orders/'+order.id)).status,'completed');
 for(const original of [first,second])assert.equal((await get('/parts/'+original.id)).quantity,original.quantity-1);
 assert.equal((await get('/audit?type=sale&vehicle_id='+v.id+'&limit=200')).total,2,'Receipt confirmation must not deduct again');
 assert.equal((await get('/orders?buyer_id='+buyer.id)).total,1,'Buyer history exact link');
 const soldPlanIds=actualTree.filter(node=>[first.id,second.id].includes(node.part_id)).map(node=>node.id);
 const noNewReceipt=await post(path(v)+'/bulk/preview',{ids:soldPlanIds,action:'receipt',confirm_physical:true});
 assert.deepEqual(noNewReceipt.eligible_ids,[],'Previously received or sold plan items cannot restock');
 await shot('integrated-completed-order');
 const integratedCheckout={actualReceivedParts:2,checkoutTotal:'205.75',currency:'UAH',oneOrder:true,saleOperations:2,replaySafe:true,receivedWithoutSecondDeduction:true,repeatReceiptBlocked:true};
 assert.deepEqual(errors,[]);
 const owner=await c.request.post('http://127.0.0.1:8060/__dv2_owner',{headers:{'X-CSRF-Token':auth.csrf_token,Cookie:(await c.cookies()).map(v=>`${v.name}=${v.value}`).join('; ')}});assert.equal(owner.status(),200);await page.goto('/vehicles?donor='+vehicles[0].id);await page.getByText('Джерела підбору',{exact:true}).click();await expect(page.locator('.dv2-sources')).toContainText('Унікальних позицій: 227');const source=await get(path(vehicles[0])+'/sources');assert.equal(Object.values(source.counts).reduce((a,b)=>a+b,0),227);await shot('platform-owner-sources');
 assert.equal((await (await cc.request.get(`/api/v1/parts?vehicle_id=${f.vehicle_id}&limit=200`)).json()).total,4,'References create no SKU');assert.equal((await c.request.get(`/api/v1/vehicles/${f.vehicle_id}`)).status(),404,'Workspace isolation');await cc.close();assert.deepEqual(errors,[]);


 fs.writeFileSync(`${dir}/report.json`,JSON.stringify({target:'LOCAL_REAL_AUTH_POSTGRES_TEST_RECORDS',threeMakes:true,planPositions:227,five:{parts:5,units:7},mixed:{parts:5,newParts:3,soldQuantity:0,damagePreserved:true},large:{parts:227,lossAfterCommittedSecondBatch:true,reloadReplay:true},qty6:'BLOCKED_AS_REQUIRED',referenceStockUnchanged:true,filtersAndInspectorPreserved:true,sourceAccess:{directorDenied:true,platformOwnerAllowed:true,uniqueSourcePositions:227},integratedCheckout,pageErrors:errors},null,2));console.log('LOCAL E2E PASS: 3 makes, generation/error/retry, five/mixed/227 intake, committed-response loss/reload/replay, qty1/qty6, day/night widths, integrated stock checkout + exact replay + completion PASS');
}finally{await browser.close()}
