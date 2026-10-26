import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local PostgreSQL required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const owner=await browser.newContext({viewport}),page=await owner.newPage();
 const auth=await owner.request.post(origin+'/api/v1/auth/register',{data:{name:'Майстерня UX58',email:`director-${viewport.width}-${Date.now()}@example.test`,password:'local-director-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await owner.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),part=await post('/parts',{name:'Генератор UX58',vehicle_id:v.id,selling_price:'120.25',currency:'UAH',unit_cost:'30.00'});
 await post('/parts/'+part.id+'/operations',{type:'receipt',quantity:2,reason:'Local team test'});
 await page.goto(origin+'/settings');await page.getByRole('link',{name:'Команда',exact:true}).click();await expect(page.getByRole('heading',{name:'Команда',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Створити співробітника',exact:true}).click();let dialog=page.getByRole('dialog',{name:'Новий співробітник'});
 const email=`worker-${viewport.width}-${Date.now()}@example.test`,temp='local-temporary-password',password='local-personal-new-password';
 await dialog.getByLabel('Ім’я',{exact:true}).fill('Іван UX58');await dialog.getByLabel('Електронна пошта',{exact:true}).fill(email);await dialog.getByLabel('Тимчасовий пароль',{exact:true}).fill(temp);
 for(const name of ['Проведення продажів','Внутрішні нотатки','Зміна ціни','Статистика залишків'])await dialog.getByRole('checkbox',{name,exact:true}).check();
 await dialog.getByRole('button',{name:'Зберегти працівника',exact:true}).click();await expect(dialog).not.toBeVisible();
 const card=page.locator('.team-list article').filter({has:page.getByRole('heading',{name:'Іван UX58',exact:true})});await expect(card).toContainText('Менеджер');
 const employee=await browser.newContext({viewport}),worker=await employee.newPage();
 async function login(pw){const r=await employee.request.post(origin+'/api/v1/auth/login',{data:{email,password:pw}});assert(r.ok(),await r.text());return r.json();}
 await login(temp);await worker.goto(origin+'/');await expect(worker.getByRole('heading',{name:'Змініть тимчасовий пароль'})).toBeVisible();await worker.getByLabel('Поточний пароль',{exact:true}).fill(temp);await worker.getByLabel('Новий пароль',{exact:true}).fill(password);await worker.getByRole('button',{name:'Змінити пароль',exact:true}).click();await expect(worker.getByRole('button',{name:'Увійти',exact:true})).toBeVisible();
 await login(password);await worker.reload();const results=worker.locator('.desktop-table:visible tbody tr,.seller-card:visible');await expect(results).toHaveCount(1);
 await expect(worker.locator('.user')).toContainText('Менеджер');if(viewport.width<=800){const identity=worker.getByRole('region',{name:'Працівник і склад'});await expect(identity).toBeVisible();await expect(identity).toContainText('Іван UX58');await expect(identity).toContainText('Менеджер');await expect(identity).toContainText('Майстерня UX58');}await expect(worker.getByRole('link',{name:'Замовлення',exact:true})).toHaveCount(0);
 await worker.goto(origin+'/statistics');await expect(worker.getByRole('heading',{name:'Огляд складу',exact:true})).toBeVisible();await expect(worker.getByRole('heading',{name:'Фінансовий огляд',exact:true})).toHaveCount(0);await expect(worker.getByRole('heading',{name:'Останні операції',exact:true})).toHaveCount(0);await worker.goto(origin+'/');await expect(results).toHaveCount(1);
 await results.getByRole('button',{name:'Дії Генератор UX58',exact:true}).click();await results.getByRole('button',{name:'Додати нотатку',exact:true}).click();
 const note=worker.getByRole('dialog',{name:'Нотатка: Генератор UX58',exact:true});await note.getByLabel('Внутрішня нотатка',{exact:true}).fill('Перевірено Іваном');await note.getByRole('button',{name:'Зберегти нотатку',exact:true}).click();await expect(note).not.toBeVisible();
 const staff=(await (await owner.request.get(origin+'/api/v1/team')).json()).items.find(u=>u.email===email);const auditPage=await owner.newPage();await auditPage.goto(origin+'/analytics?actor_id='+staff.id);await expect(auditPage.getByText('Автор: Іван UX58',{exact:true})).toBeVisible();await auditPage.close();
 await fs.mkdir('test-results',{recursive:true});await worker.screenshot({path:`test-results/team-worker-${viewport.width}.png`,fullPage:true});
 await card.getByRole('button',{name:'Права та доступ: Іван UX58',exact:true}).click();dialog=page.getByRole('dialog',{name:'Права працівника'});
 await page.screenshot({path:`test-results/team-permissions-${viewport.width}.png`,fullPage:true});
 await dialog.getByRole('checkbox',{name:'Проведення продажів',exact:true}).uncheck();await dialog.getByRole('button',{name:'Зберегти працівника',exact:true}).click();await expect(dialog).not.toBeVisible();
 // A stale UI cannot bypass the revoked right. The server returns 403 before stock is changed.
 await results.getByRole('button',{name:'Продати',exact:true}).click();const sale=worker.getByRole('dialog',{name:'Продати: Генератор UX58',exact:true});await sale.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(sale).not.toBeVisible();
 assert.equal((await (await owner.request.get(origin+'/api/v1/parts/'+part.id)).json()).quantity,2);await expect(results.getByRole('button',{name:'Продати',exact:true})).toHaveCount(0);
 await worker.goto(origin+'/settings');await expect(worker.getByRole('link',{name:'Команда',exact:true})).toHaveCount(0);
 await card.getByRole('button',{name:'Права та доступ: Іван UX58',exact:true}).click();dialog=page.getByRole('dialog',{name:'Права працівника'});await dialog.getByRole('checkbox',{name:'Доступ активний',exact:true}).uncheck();await dialog.getByRole('button',{name:'Зберегти працівника',exact:true}).click();await expect(dialog).not.toBeVisible();await expect(card).toContainText('Заблокований');await worker.reload();await expect(worker.getByRole('button',{name:'Увійти',exact:true})).toBeVisible();
 await card.getByRole('button',{name:'Права та доступ: Іван UX58',exact:true}).click();dialog=page.getByRole('dialog',{name:'Права працівника'});await dialog.getByLabel('Роль',{exact:true}).selectOption('ADMIN');await dialog.getByRole('checkbox',{name:'Доступ активний',exact:true}).check();await dialog.getByRole('button',{name:'Зберегти працівника',exact:true}).click();await expect(dialog).not.toBeVisible();await expect(card).toContainText('Адміністратор');

 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert(await worker.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await employee.close();await owner.close();console.log('PASS Team create/activate/rights/revoke/403/block/unblock/role/private menus',viewport.width);
}}finally{await browser.close();}
