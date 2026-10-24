import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local disposable database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try {for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))paid.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'UX5 test',email:`ux5-${Date.now()}@example.test`,password:'offline-ux5-test-password'}});assert(auth.ok());
 const authData=await auth.json(),headers={'X-CSRF-Token':authData.csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const volvo=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010}),bmw=await post('/vehicles',{manufacturer:'BMW',model:'X3',year:2012});
 await post('/categories/import',{source:'ux5-local',nodes:[{key:'body',name:'Кузов UX5',kind:'category'},{key:'panels',parent_key:'body',name:'Панелі UX5',kind:'subcategory'}]});
 const categories=(await (await context.request.get(origin+'/api/v1/categories')).json()).items;
 const category_id=categories.find(c=>c.external_key==='body').id,subcategory_id=categories.find(c=>c.external_key==='panels').id;
 const hood=await post('/parts',{vehicle_id:volvo.id,name:'Капот UX5',category_id,subcategory_id,oem_number:'OEM-UX5',article_number:'ART-UX5',selling_price:'123.45'});
 await post(`/parts/${hood.id}/operations`,{type:'receipt',quantity:3,reason:'Local stock'});
 const other=await post('/parts',{vehicle_id:bmw.id,name:'Капот BMW UX5',selling_price:'90.00'});await post(`/parts/${other.id}/operations`,{type:'receipt',quantity:1,reason:'Local stock'});
 for(let i=0;i<4;i++){const p=await post('/parts',{vehicle_id:volvo.id,name:`Капот підказка ${i}`});await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:1,reason:'Local stock'});}
 await page.goto(origin+'/inventory');await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await page.getByRole('button',{name:/Volvo XC90.*2010/}).click();
 await expect(page.getByRole('heading',{name:'Volvo XC90 · 2010 · №1',exact:true})).toBeVisible();await page.getByRole('checkbox',{name:'Запам’ятати цей автомобіль',exact:true}).check();
 const tree=page.locator('.donor-stock-tree');await tree.locator('summary').filter({hasText:'Кузов UX5'}).click();await expect(tree.getByRole('heading',{name:/Панелі UX5/})).toBeVisible();await tree.locator('.donor-stock-subcategory>summary').filter({hasText:'Панелі UX5'}).click();
 const row=()=>tree.locator('.donor-part-row').filter({has:page.getByRole('button',{name:'Капот UX5',exact:true})});
 await expect(row()).toContainText('У наявності: 3');assert(await row().getByRole('button',{name:'Капот UX5',exact:true}).evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=14));await page.screenshot({path:`test-results/ux5-donor-${viewport.width}.png`,fullPage:true});
 const search=page.getByRole('searchbox',{name:'Пошук запчастин',exact:true});
 for(const term of ['ка','OEM-UX5','ART-UX5']){await search.fill(term);await expect(row()).toBeVisible();await expect(tree.getByRole('button',{name:'Капот BMW UX5',exact:true})).toHaveCount(0);}
 await row().getByRole('button',{name:'Ціна Капот UX5',exact:true}).click();let modal=page.getByRole('dialog',{name:'Ціна запчастини',exact:true});await modal.getByLabel('Сума',{exact:true}).fill('456.78');await modal.getByLabel('Валюта',{exact:true}).selectOption('USD');await modal.getByRole('button',{name:'Зберегти',exact:true}).click();await expect(row()).toContainText('456,78');
 await row().getByRole('button',{name:'Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();await expect(row()).toContainText('У наявності: 2');
 await page.getByRole('button',{name:'Загальний склад',exact:true}).click();
 let general=page.locator(viewport.width>800?'.desktop-table tbody tr':'.seller-card').filter({has:page.getByRole('button',{name:'Капот UX5',exact:true})});await expect(general).toContainText('456,78');await expect(general).toContainText('USD');
 await general.getByRole('button',{name:'Ціна Капот UX5',exact:true}).click();modal=page.getByRole('dialog',{name:'Ціна запчастини',exact:true});await modal.getByLabel('Сума',{exact:true}).fill('567.89');await modal.getByRole('button',{name:'Зберегти',exact:true}).click();await expect(general).toContainText('567,89');
 await general.getByRole('button',{name:'Продати',exact:true}).click();modal=page.locator('dialog[open]').last();await modal.getByRole('button',{name:'Підтвердити',exact:true}).click();
 await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await tree.locator('summary').filter({hasText:'Кузов UX5'}).click();await tree.locator('.donor-stock-subcategory>summary').filter({hasText:'Панелі UX5'}).click();await expect(row()).toContainText('У наявності: 1');
 await page.goto(origin+'/');await page.goto(origin+'/inventory');await expect(page.getByRole('button',{name:'За автомобілями',exact:true})).toHaveAttribute('aria-pressed','true');await expect(page.getByLabel('Автомобіль складу',{exact:true})).toHaveValue(volvo.id);
 await page.getByLabel('Автомобіль складу',{exact:true}).selectOption(bmw.id);await expect(page.getByRole('heading',{name:'BMW X3 · 2012 · №2',exact:true})).toBeVisible();
 await page.getByLabel('Автомобіль складу',{exact:true}).selectOption(volvo.id);
 // Existing plan component retains category bulk selection without changing stock.
 await page.locator('.donor-potential>summary').click();const plan=page.getByRole('region',{name:'Каталог запчастин автомобіля'});await expect(plan.getByText(/У довіднику: 33/)).toBeVisible();
 const categoryBox=plan.getByRole('checkbox',{name:/Вибрати категорію/}).first();await categoryBox.uncheck();await expect(categoryBox).not.toBeChecked();await categoryBox.check();await expect(categoryBox).toBeChecked();
 assert.equal((await (await context.request.get(origin+`/api/v1/parts/${hood.id}`)).json()).quantity,1);
 await page.goto(origin+'/inventory?vehicle_id=missing-donor');await expect(page.getByRole('region',{name:'Автомобілі на складі'})).toBeVisible();await expect(page.getByLabel('Автомобіль складу',{exact:true})).toHaveCount(0);
 // Suggestions must survive parent clipping and appear on top of results, before and after scroll.
 await page.goto(origin+'/');const combo=page.getByRole('combobox',{name:'Пошук запчастин',exact:true});await combo.fill('ка');
 const list=page.getByRole('listbox',{name:'Підказки запчастин'});await expect(list).toBeVisible();
 async function hitTest(){assert(await list.evaluate(el=>{const r=el.getBoundingClientRect(),x=r.left+20,y=Math.min(r.bottom-10,innerHeight-10);const target=document.elementFromPoint(x,y);return y>r.top&&el.contains(target);}), 'Suggestions must be the top hit-tested element');}
 await hitTest();await page.screenshot({path:`test-results/ux5-suggestions-${viewport.width}.png`,fullPage:true});await page.evaluate(()=>scrollBy(0,120));await hitTest();
 await combo.press('ArrowDown');await combo.press('Enter');await expect(page.locator('dialog[open]')).toBeVisible();await page.getByRole('button',{name:'Закрити',exact:true}).click();
 await combo.focus();await expect(list).toBeVisible();const option=list.getByRole('option').first();if(viewport.width<800)await option.tap();else await option.click();await expect(page.locator('dialog[open]')).toBeVisible();await page.getByRole('button',{name:'Закрити',exact:true}).click();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
 await page.screenshot({path:`test-results/ux5-${viewport.width}.png`,fullPage:true});
 // A large read-only API fixture validates lazy rendering without fake stock mutations.
 await page.route('**/api/v1/parts?*',async route=>{
  const url=new URL(route.request().url());if(url.searchParams.get('vehicle_id')!==volvo.id)return route.continue();
  const offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||50);
  const items=Array.from({length:Math.max(0,Math.min(limit,1001-offset))},(_,i)=>({...hood,id:'ux5-large-'+(offset+i),name:'Тестова деталь '+(offset+i),quantity:1,available_quantity:1}));
  await route.fulfill({json:{items,total:1001,offset,limit}});
 });
 await page.goto(origin+'/inventory');await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await page.getByRole('button',{name:/Volvo XC90.*2010/}).click();
 await expect(tree.locator('summary').filter({hasText:'Кузов UX5'})).toContainText('1001');await expect(tree.locator('.donor-part-row')).toHaveCount(0);
 await tree.locator('summary').filter({hasText:'Кузов UX5'}).click();await expect(tree.locator('.donor-part-row')).toHaveCount(0);await tree.locator('.donor-stock-subcategory>summary').filter({hasText:'Панелі UX5'}).click();await expect(tree.locator('.donor-part-row')).toHaveCount(50);await tree.getByRole('button',{name:'Ще 50 деталей',exact:true}).click();await expect(tree.locator('.donor-part-row')).toHaveCount(100);
 await page.unroute('**/api/v1/parts?*');
 // The preference belongs to the account, not the whole browser.
 await context.request.post(origin+'/api/v1/auth/logout',{headers});await page.goto(origin+'/');
 const second=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Another user',email:`ux5-other-${Date.now()}@example.test`,password:'offline-ux5-test-password'}});assert(second.ok());await page.goto(origin+'/inventory');await expect(page.getByRole('button',{name:'Загальний склад',exact:true})).toHaveAttribute('aria-pressed','true');
 await context.close();console.log(`PASS UX5 mode/donor persistence, tree/search, shared price/stock/sale, category plan, unavailable donor, account isolation, suggestion hit-testing/scroll/keyboard/touch ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
