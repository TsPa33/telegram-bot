// End-to-end authorization uses the actual Stage 2 backend and disposable PostgreSQL.
// No route mocking, dependency overrides or fake readiness responses are used.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local PostgreSQL required');
const width=Number(process.env.WAREHOUSE_VIEWPORT_WIDTH||1440),viewport={width,height:width===1440?1000:width===768?1024:844};
const origin='http://127.0.0.1:5173',stamp=`${width}-${Date.now()}`;
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const errors=[];
try{
 const owner=await browser.newContext({viewport}),page=await owner.newPage();page.on('pageerror',e=>errors.push(e.message));
 const auth=await owner.request.post(origin+'/api/v1/auth/register',{data:{name:'Майстерня Stage3 Audit',email:`owner-${stamp}@example.test`,password:'local-director-password'}});assert.equal(auth.status(),201);const director=await auth.json();
 const headers={'X-CSRF-Token':director.csrf_token};
 async function get(path,context=owner){const r=await context.request.get(origin+'/api/v1'+path,{headers:{'X-Warehouse-Client':'5'}});assert.equal(r.status(),200,await r.text());return r.json();}
 async function post(path,data){const r=await owner.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 async function update(row,changes){const r=await owner.request.patch(origin+'/api/v1/team/'+row.id,{headers,data:{name:row.name,role:row.role,permissions:row.permissions,is_active:row.is_active,...changes}});assert.equal(r.status(),200,await r.text());return r.json();}
 const readiness=await get('/team/readiness');assert.equal(readiness.employee_creation_enabled,true);
 const groups=(await get('/team/permissions')).groups,registry=Object.assign({},...Object.values(groups));assert.equal(Object.keys(registry).length,31);
 const vehicle=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010});
 const part=await post('/parts',{name:'Генератор Stage3 Audit',vehicle_id:vehicle.id,unit_cost:'98765.43',selling_price:'120.25',currency:'USD'});
 await post('/parts/'+part.id+'/operations',{type:'receipt',quantity:3,reason:'Local Stage3 audit'});
 const original=['inventory.view','inventory.edit','parts.view_cost','parts.change_price','sales.view','sales.view_financials','audit.view','analytics.view','analytics.financial','vehicles.view','catalog.view','parts.notes','sales.create'];
 let staff=await post('/team',{name:'Іван Stage3 Audit',email:`worker-${stamp}@example.test`,password:'local-temporary-password',role:'MANAGER',permissions:original});
 const workerContext=await browser.newContext({viewport}),worker=await workerContext.newPage();worker.on('pageerror',e=>errors.push(e.message));
 async function activate(context,email){
  let r=await context.request.post(origin+'/api/v1/auth/login',{data:{email,password:'local-temporary-password'}});assert.equal(r.status(),200);const csrf=(await r.json()).csrf_token;
  r=await context.request.post(origin+'/api/v1/auth/password',{headers:{'X-CSRF-Token':csrf},data:{current_password:'local-temporary-password',password:'local-personal-password'}});assert.equal(r.status(),200);
  r=await context.request.post(origin+'/api/v1/auth/login',{data:{email,password:'local-personal-password'}});assert.equal(r.status(),200);
 }
 await activate(workerContext,staff.email);
 // A real CSRF 403 must refresh identity without remount/retry loops when
 // permissions did not change. No server response is mocked here.
 await worker.goto(origin+'/');
 const rows=worker.locator('.desktop-table:visible tbody tr,.seller-card:visible');
 await rows.getByRole('button',{name:'Ціна '+part.name,exact:true}).click();
 const pricing=worker.getByRole('dialog',{name:'Ціна запчастини',exact:true});
 const csrfCookie=(await workerContext.cookies()).find(c=>c.name==='warehouse_csrf');assert(csrfCookie);
 await workerContext.addCookies([{...csrfCookie,value:'intentionally-invalid-local-csrf'}]);
 await pricing.getByLabel('Сума',{exact:true}).fill('555.55');
 const checked=worker.waitForResponse(r=>r.url().endsWith('/api/v1/auth/me'));
 await pricing.getByRole('button',{name:'Зберегти',exact:true}).click();await checked;
 await expect(pricing).toBeVisible();await expect(pricing.getByRole('alert')).toContainText('CSRF');
 assert.equal((await get('/parts/'+part.id)).selling_price,'120.25');
 await workerContext.addCookies([csrfCookie]);await pricing.getByRole('button',{name:'Закрити',exact:true}).click();
 await worker.goto(origin+'/analytics');await expect(worker.locator('pre').first()).toContainText('98765.43');
 staff=await update(staff,{permissions:original.filter(p=>!['parts.view_cost','sales.view_financials','analytics.financial'].includes(p))});
 await worker.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await expect(worker.locator('pre').first()).not.toContainText('unit_cost');await expect(worker.locator('pre').first()).not.toContainText('98765.43');
 assert(!JSON.stringify(await get('/audit',workerContext)).includes('unit_cost'));
 await expect(worker.getByRole('heading',{name:'Вартість запасів за валютами'})).toHaveCount(0);
 // Zero-right lookup permissions must not trigger repeated 403/remount loops.
 staff=await update(staff,{permissions:['inventory.view','sales.view','audit.view','analytics.view','catalog.view']});
 await worker.evaluate(()=>window.dispatchEvent(new Event('focus')));
 const forbidden=[];worker.on('response',r=>{if(r.status()===403)forbidden.push(new URL(r.url()).pathname);});
 for(const path of ['/','/inventory','/sales','/analytics','/catalog','/statistics']){
  await worker.goto(origin+path);await expect(worker.locator('main h1').first()).toBeVisible();
  await expect(worker.getByRole('heading',{name:'Перевіряємо доступ'})).toHaveCount(0);
 }
 await expect(worker.getByRole('heading',{name:'Фінансовий огляд'})).toHaveCount(0);
 await worker.goto(origin+'/catalog');await expect(worker.getByRole('button',{name:'Імпорт категорій'})).toHaveCount(0);assert.deepEqual(forbidden,[]);
 const noRightsPage=await workerContext.newPage();await noRightsPage.goto(origin+'/team');await expect(noRightsPage.getByRole('heading',{name:'Доступ обмежено'})).toBeVisible();await noRightsPage.close();
 // Revocation must not discard an uncertain order's original idempotency key.
 const orderRights=['inventory.view','orders.view','orders.create'];
 staff=await update(staff,{permissions:orderRights});
 await post('/buyers',{name:'Покупець Idempotency',phone:'0507777777'});
 await worker.goto(origin+'/orders');await worker.getByRole('button',{name:'Нове замовлення',exact:true}).click();
 let orderForm=worker.getByRole('dialog',{name:'Оформити замовлення',exact:true});
 await orderForm.getByLabel('Додати запчастину',{exact:true}).fill(part.name);
 await orderForm.getByRole('button',{name:new RegExp(part.name+' · Вільних')}).click();
 await orderForm.getByLabel('Погоджена ціна '+part.name,{exact:true}).fill('13.20');
 await orderForm.getByLabel('Телефон покупця',{exact:true}).fill('0507777777');await orderForm.getByRole('button',{name:'Покупець Idempotency · 0507777777',exact:true}).click();
 await expect(orderForm.getByRole('checkbox',{name:'Після збереження зарезервувати'})).toHaveCount(0);
 let originalCommand;
 await worker.route('**/api/v1/orders',async route=>{
  if(route.request().method()!=='POST')return route.continue();
  originalCommand=route.request().postDataJSON();const committed=await route.fetch();assert.equal(committed.status(),201);await route.abort('failed');
 });
 await orderForm.getByRole('button',{name:'Зберегти замовлення',exact:true}).click();await expect(orderForm.getByRole('alert')).toBeVisible();await worker.unroute('**/api/v1/orders');
 assert.equal((await get('/orders')).total,1);
 staff=await update(staff,{permissions:orderRights.filter(p=>p!=='orders.create')});
 await worker.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(orderForm).not.toBeVisible();
 const replay=worker.getByRole('button',{name:'Перевірити результат запиту',exact:true});
 await replay.click();await expect(replay).toBeEnabled();
 await expect(worker.getByRole('alert')).toContainText('Недостатньо прав');
 const retained=await worker.evaluate(id=>JSON.parse(sessionStorage.getItem('warehouse-order-pending:'+id)),staff.id);
 assert.deepEqual(retained.body,originalCommand);assert.equal((await get('/orders')).total,1);
 staff=await update(staff,{permissions:orderRights});await worker.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await worker.getByRole('button',{name:'Перевірити результат запиту',exact:true}).click();
 await expect(worker.getByRole('heading',{name:'Замовлення №1',exact:true})).toBeVisible();
 assert.equal((await get('/orders')).total,1);assert.equal((await get('/parts/'+part.id)).quantity,3);
 // An admin manages managers only; broader retained rights cannot be reset/re-enabled.
 staff=await update(staff,{permissions:['inventory.view','vehicles.view','catalog.view','sales.create'],is_active:false});
 const adminRights=['inventory.view','vehicles.view','catalog.view','team.view','team.manage_managers'];
 const admin=await post('/team',{name:'Олена Stage3 Admin',email:`admin-${stamp}@example.test`,password:'local-temporary-password',role:'ADMIN',permissions:adminRights});
 const adminContext=await browser.newContext({viewport}),adminPage=await adminContext.newPage();adminPage.on('pageerror',e=>errors.push(e.message));await activate(adminContext,admin.email);
 await adminPage.goto(origin+'/team');const adminCard=adminPage.locator('.team-list article').filter({has:adminPage.getByRole('heading',{name:staff.name,exact:true})});
 await expect(adminPage.locator('.team-list')).not.toContainText('Олена Stage3 Admin');await expect(adminPage.locator('.team-list')).not.toContainText('Майстерня Stage3 Audit');
 await expect(adminCard.getByRole('button',{name:'Скинути доступ: '+staff.name,exact:true})).toBeDisabled();
 await adminCard.getByRole('button',{name:'Права та доступ: '+staff.name,exact:true}).click();let dialog=adminPage.getByRole('dialog',{name:'Права працівника'});
 assert.equal(await dialog.getByLabel('Роль',{exact:true}).locator('option').count(),1);
 await dialog.getByRole('checkbox',{name:'Доступ активний',exact:true}).check();await expect(dialog.getByRole('alert')).toContainText('Для активації відкличте права');await expect(dialog.getByRole('button',{name:'Зберегти працівника'})).toBeDisabled();
 await dialog.getByRole('checkbox',{name:registry['sales.create'],exact:true}).uncheck();await expect(dialog.getByRole('checkbox',{name:registry['sales.create'],exact:true})).toBeDisabled();
 await dialog.getByRole('button',{name:'Зберегти працівника'}).click();await expect(dialog).not.toBeVisible();
 staff=(await get('/team')).items.find(u=>u.id===staff.id);assert.equal(staff.is_active,true);assert.deepEqual([...staff.permissions].sort(),['catalog.view','inventory.view','vehicles.view']);
 // Director reset is real, single-submit, revokes old sessions, and forces change.
 await page.goto(origin+'/team');let ownerCard=page.locator('.team-list article').filter({has:page.getByRole('heading',{name:staff.name,exact:true})});
 await ownerCard.getByRole('button',{name:'Скинути доступ: '+staff.name,exact:true}).click();dialog=page.getByRole('dialog',{name:'Скидання доступу'});
 await dialog.getByLabel('Тимчасовий пароль',{exact:true}).fill('local-reset-temporary-password');let resets=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/team/'+staff.id+'/reset-password'))resets++;});
 await dialog.getByRole('button',{name:'Зберегти працівника'}).evaluate(el=>{el.click();el.click();});await expect(dialog).not.toBeVisible();assert.equal(resets,1);
 const expired=await workerContext.request.get(origin+'/api/v1/auth/me');assert.equal(expired.status(),401);
 await worker.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(worker.getByRole('button',{name:'Увійти',exact:true})).toBeVisible();
 const resetLogin=await workerContext.request.post(origin+'/api/v1/auth/login',{data:{email:staff.email,password:'local-reset-temporary-password'}});assert.equal(resetLogin.status(),200);
 await worker.reload();await expect(worker.getByRole('heading',{name:'Змініть тимчасовий пароль'})).toBeVisible();assert.equal((await workerContext.request.get(origin+'/api/v1/parts')).status(),403);
 // Optional dedicated pagination fixture uses only this local workspace.
 if(width===1440){
  for(let i=0;i<49;i++)await post('/team',{name:'Pagination worker '+i,email:`page-${i}-${stamp}@example.test`,password:'local-temporary-password',permissions:[]});
  const pages=[];page.on('request',r=>{if(r.url().includes('/api/v1/team?'))pages.push(new URL(r.url()).searchParams);});
  await page.reload();await expect(page.getByRole('button',{name:'Наступні працівники'})).toBeEnabled();await page.getByRole('button',{name:'Наступні працівники'}).click();await expect(page.locator('.pager')).toContainText('Сторінка 2');
  await expect(page.locator('.team-list article')).toHaveCount(2);assert(pages.some(p=>p.get('offset')==='50'&&p.get('limit')==='50'));await page.getByRole('button',{name:'Попередні працівники'}).click();
 }
 await page.getByRole('searchbox',{name:'Пошук працівників на сторінці'}).fill(staff.name);await expect(page.locator('.team-list article')).toHaveCount(1);
 await page.getByRole('button',{name:'Права та доступ: '+staff.name,exact:true}).click();dialog=page.getByRole('dialog',{name:'Права працівника'});assert.equal(await dialog.locator('.permission-groups input[type=checkbox]').count(),31);
 await fs.mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/team-stage3-security-${width}.png`});
 for(const current of [page,worker,adminPage])assert(await current.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal((await get('/parts/'+part.id)).quantity,3);assert.deepEqual(errors,[]);
 await owner.close();await workerContext.close();await adminContext.close();
 console.log('PASS real Stage3 permission cache/restricted lookups/admin bounds/reset/pagination',width);
}finally{await browser.close();}
