import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local disposable database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/cdn\.plan\.parts|\/plan-parts\//.test(r.url()))paid.push(r.url());});
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'UX512',email:`ux512-${Date.now()}@example.test`,password:'local-ux512-test-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010});
 await post('/categories/import',{source:'ux512-local',nodes:[{key:'body',name:'Кузов',kind:'category'},{key:'panels',parent_key:'body',name:'Панелі кузова',kind:'subcategory'}]});
 const cats=(await(await context.request.get(origin+'/api/v1/categories')).json()).items;
 const category_id=cats.find(c=>c.external_key==='body').id,subcategory_id=cats.find(c=>c.external_key==='panels').id;
 const names=['Капот','Передня ліва внутрішня панель кріплення крила Volvo XC90 з довгою назвою','Двері передні праві'];const parts=[];
 for(const name of names){const p=await post('/parts',{vehicle_id:v.id,name,category_id,subcategory_id,location:'Полиця A1',selling_price:'125.67',currency:'USD'});await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:3,reason:'Local visual test'});parts.push(p);}
 await page.goto(origin+'/inventory');await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await page.getByRole('button',{name:/Відкрити склад Volvo XC90/}).click();
 const tree=page.locator('.donor-stock-tree'),category=tree.locator(':scope>details'),summary=category.locator(':scope>summary');await expect(summary).toContainText('Кузов');await expect(summary).toContainText('3');await summary.click();await expect(category).toHaveAttribute('open','');
 const sub=tree.locator('.donor-stock-subcategory'),subSummary=sub.locator(':scope>summary');await expect(subSummary).toContainText('Панелі кузова');await expect(subSummary).toContainText('3');
 const row=name=>tree.locator('.donor-part-row').filter({has:page.getByRole('button',{name,exact:true})});await expect(row(names[0])).toHaveCount(0);await subSummary.click();await expect(row(names[0])).toBeVisible();await subSummary.click();await expect(row(names[0])).not.toBeVisible();await subSummary.press('Enter');await expect(row(names[0])).toBeVisible();
 const sale=row(names[0]).getByRole('button',{name:'Продати',exact:true}),title=row(names[0]).getByRole('button',{name:names[0],exact:true});
 assert.equal(await sale.evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(255, 255, 255)');assert(await sale.evaluate(el=>parseFloat(getComputedStyle(el).borderTopWidth)>=1&&el.getBoundingClientRect().height>=44));
 assert(await title.evaluate(el=>parseFloat(getComputedStyle(el).fontWeight)>=600&&parseFloat(getComputedStyle(el).fontSize)>=14));
 assert.notEqual(await summary.evaluate(el=>getComputedStyle(el).backgroundColor),await subSummary.evaluate(el=>getComputedStyle(el).backgroundColor));
 for(const name of names){const item=row(name);assert(await item.evaluate(el=>{const r=el.getBoundingClientRect();return el.scrollWidth<=el.clientWidth&&r.width<=innerWidth;}));const button=item.getByRole('button',{name,exact:true});assert(await button.evaluate(el=>{const s=getComputedStyle(el);return s.whiteSpace!=='nowrap'&&s.textOverflow!=='ellipsis';}));}
 if(viewport.width>=800)assert(await row(names[0]).evaluate(el=>el.getBoundingClientRect().height<=80),'Desktop rows must remain compact');
 if(viewport.width<800){assert(await row(names[0]).evaluate(el=>el.getBoundingClientRect().height<=140));const long=row(names[1]);assert(await long.evaluate(el=>{const price=el.querySelector('.seller-price').getBoundingClientRect(),actions=el.querySelector('.seller-actions').getBoundingClientRect();return price.right<=actions.left&&Math.abs(price.top-actions.top)<4;}));}
 await title.click();const card=page.getByRole('dialog',{name:names[0],exact:true});await expect(card).toBeVisible();await card.getByRole('button',{name:'Закрити',exact:true}).click();
 await row(names[0]).getByRole('button',{name:'Дії Капот',exact:true}).click();await expect(row(names[0]).locator('.stock-actions-menu')).toBeVisible();await page.keyboard.press('Escape');
 await page.screenshot({path:`test-results/ux512-tree-${viewport.width}.png`,fullPage:true});
 await sale.click();const confirmation=page.getByRole('dialog',{name:'Продати: Капот',exact:true}),confirm=confirmation.getByRole('button',{name:'Підтвердити',exact:true});await expect(confirm).toHaveClass(/primary/);assert.notEqual(await confirm.evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(255, 255, 255)');await confirm.click();await expect(confirmation).not.toBeVisible();await expect(row(names[0])).toContainText('У наявності: 2');
 assert.equal((await(await context.request.get(origin+`/api/v1/audit?part_id=${parts[0].id}&type=sale`)).json()).total,1);
 await summary.click();await expect(category).not.toHaveAttribute('open','');await summary.press('Enter');await expect(row(names[0])).toBeVisible();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
 await context.close();console.log(`PASS UX512 neutral hierarchy, category/subcategory toggles, long names, compact outline actions, card/menu, prominent confirmed sale ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
