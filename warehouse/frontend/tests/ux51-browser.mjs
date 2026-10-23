import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local disposable database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))paid.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'UX51 owner',email:`ux51-${Date.now()}@example.test`,password:'local-ux51-test-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),p=await post('/parts',{vehicle_id:v.id,name:'Капот UX51',oem_number:'OEM-51',article_number:'ART-51',selling_price:'100.25',currency:'USD',internal_notes:'Примітка продавця',description:'Опис капота',location:'A-01'});
 await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:5,reason:'Local receipt'});
 for(const op of [{type:'sale',quantity:1},{type:'reserve',quantity:1,reason:'Local reserve'},{type:'release',quantity:1,reason:'Local release'},{type:'transfer',location:'B-02',reason:'Local transfer'},{type:'write_off',quantity:1,reason:'Local writeoff'},{type:'correction',quantity:4,reason:'Local correction'}])await post(`/parts/${p.id}/operations`,op);
 await page.goto(origin+'/inventory');await expect(page.getByRole('switch',{name:'Показати без залишку',exact:true})).toBeVisible();await expect(page.getByText('Додаткові фільтри',{exact:true})).toHaveCount(0);
 const row=page.locator(viewport.width>800?'.desktop-table tbody tr':'.seller-card').filter({has:page.getByRole('button',{name:'Капот UX51',exact:true})});
 await row.getByRole('button',{name:'Дії Капот UX51',exact:true}).click();const menu=row.locator('.stock-actions-menu');await expect(menu).toBeVisible();assert(await menu.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}));
 await menu.getByRole('button',{name:'Архівувати',exact:true}).scrollIntoViewIfNeeded();await expect(menu).toBeVisible();await page.screenshot({path:`test-results/ux51-menu-${viewport.width}.png`});
 await menu.getByRole('button',{name:'Відкрити картку',exact:true}).click();let card=page.getByRole('dialog',{name:'Капот UX51',exact:true});
 for(const text of ['OEM: OEM-51','Артикул: ART-51','Примітка продавця','Опис капота','B-02'])await expect(card).toContainText(text);
 for(const name of ['Продати','Редагувати','Зарезервувати','Перемістити','Списати','Історія'])await expect(card.getByRole('button',{name,exact:true})).toBeVisible();
 assert(await card.evaluate(el=>{const r=el.getBoundingClientRect();return el.scrollWidth<=el.clientWidth&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}),'Part dialog must fit the viewport');
 await card.getByText('Докладніше',{exact:true}).click();await card.locator('.stock-summary').scrollIntoViewIfNeeded();if(viewport.width<800)assert(await card.evaluate(el=>el.scrollTop>0),'Mobile dialog scroll must reach lower content');await card.getByText('Докладніше',{exact:true}).click();
 await page.screenshot({path:`test-results/ux51-card-${viewport.width}.png`});
 await card.getByRole('button',{name:'Перемістити',exact:true}).click();let modal=page.getByRole('dialog',{name:'Перемістити: Капот UX51',exact:true});await modal.getByLabel('Нове місце',{exact:true}).fill('C-03');await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(card).toContainText('C-03');
 await card.getByRole('button',{name:'Зарезервувати',exact:true}).click();modal=page.getByRole('dialog',{name:'Зарезервувати: Капот UX51',exact:true});await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(card).toContainText('У наявності: 3');
 await card.getByRole('button',{name:'Історія',exact:true}).click();let history=page.getByRole('dialog',{name:'Історія: Капот UX51',exact:true});await history.getByLabel('Тип історії',{exact:true}).selectOption('sale');await expect(history.locator('.stock-history-event')).toHaveCount(1);await expect(history).toContainText('100,25');await expect(history).toContainText('USD');await expect(history).toContainText('Ціна у картці на момент операції');await expect(history).toContainText('UX51 owner');
 assert(await history.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}));
 await history.getByRole('button',{name:'Закрити',exact:true}).click();await card.getByRole('button',{name:'Закрити',exact:true}).click();
 await row.getByRole('button',{name:'Дії Капот UX51',exact:true}).click();await menu.getByRole('button',{name:'Зняти резерв',exact:true}).click();modal=page.locator('dialog[open]').last();await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(modal).not.toBeVisible();
 await page.getByRole('button',{name:'Історія операцій',exact:true}).click();const log=page.getByRole('region',{name:'Історія операцій',exact:true});await log.getByLabel('Автомобіль історії',{exact:true}).selectOption(v.id);await log.getByLabel('Запчастина історії',{exact:true}).selectOption(p.id);
 for(const type of ['sale','reserve','release','write_off','correction']){await log.getByLabel('Тип історії',{exact:true}).selectOption(type);await expect(log.locator('.stock-history-event')).toHaveCount(['reserve','release'].includes(type)?2:1);}
 await log.getByLabel('Тип історії',{exact:true}).selectOption('transfer');await expect(log.locator('.stock-history-event')).toHaveCount(2);await expect(log).toContainText('C-03');
 await log.getByLabel('Історія від',{exact:true}).fill('2099-01-01');await expect(log.getByRole('heading',{name:'Операцій не знайдено',exact:true})).toBeVisible();await log.getByLabel('Історія від',{exact:true}).fill('');await expect(log.locator('.stock-history-event')).toHaveCount(2);
 await page.screenshot({path:`test-results/ux51-history-${viewport.width}.png`,fullPage:true});
 await page.getByRole('button',{name:'Запчастини',exact:true}).click();await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await page.getByRole('button',{name:/Volvo XC90.*2010/}).click();await expect(page.getByText('Каталог деталей автомобіля',{exact:true})).toBeVisible();await page.getByText('Каталог деталей автомобіля',{exact:true}).click();await expect(page.getByText(/Виберіть деталі, які є на автомобілі/)).toBeVisible();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
 await context.close();console.log(`PASS UX51 compact detail, bounded top-layer menu, nested dialogs, shared transfer, truthful audit and server filters ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
