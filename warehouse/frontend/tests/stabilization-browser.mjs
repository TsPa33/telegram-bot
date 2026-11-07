// Real local API/PostgreSQL, offline provider, no staging data.
import {chromium,expect as originalExpect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local fixture only');
const f=JSON.parse(fs.readFileSync('/tmp/vehicle-workspace-fixture.json'));assert(f.synthetic);
const out='/tmp/carpot-stabilization-browser';fs.mkdirSync(out,{recursive:true});
const b=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const expect=originalExpect.configure({timeout:15000});
try{
 const c=await b.newContext({baseURL:'http://127.0.0.1:5223',viewport:{width:1440,height:1000}});
 assert.equal((await c.request.post('/api/v1/auth/login',{data:{email:f.email,password:f.password}})).status(),200);
 const p=await c.newPage();p.setDefaultTimeout(15000);const errors=[],calls=[];p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>calls.push({url:r.url(),method:r.method()}));
 await p.goto('/vehicles?donor='+f.vehicle.id);const board=p.getByRole('region',{name:'Єдиний план розбору',exact:true});await expect(board).toBeVisible();
 await expect(board.locator('.wd-metric').first()).toContainText('96');
 for(const [kind,id] of [['tool',10001],['kit',10002],['consumable',10003],['review',10004]]){
  await board.getByLabel('Тип позицій',{exact:true}).selectOption(kind);await expect(board.locator('.wd-row[aria-label]')).toHaveCount(1);await expect(board.locator('[data-entry-key="pp:131094:'+id+'"]')).toBeVisible();
 }
 await board.getByLabel('Тип позицій',{exact:true}).selectOption('part');
 const start=calls.length;
 await board.locator('.wd-th input').check();await board.locator('.wd-aside').getByRole('button',{name:'Додати на склад',exact:true}).click();await expect(board.locator('.wd-notice')).toContainText('Додано: 93.');
 assert.equal(calls.slice(start).filter(r=>r.url.includes('/donor-parts/add-batch')&&r.method==='POST').length,1);
 await expect(board.getByRole('alertdialog',{name:'Підтвердження складу',exact:true})).toHaveCount(0);
 await board.locator('.wd-th input').check();await board.locator('.wd-aside').getByRole('button',{name:'Додати на склад',exact:true}).click();await expect(board.locator('.wd-notice')).toContainText('Додано: 0. Уже існують: 96.');
 let saved=await(await c.request.get('/api/v1/parts?vehicle_id='+f.vehicle.id+'&limit=200')).json();assert.equal(saved.total,96);const inventoryBefore=Object.fromEntries(saved.items.map(x=>[x.id,[x.quantity,x.reserved_quantity,x.selling_price,x.currency,x.oem_number,x.article_number]]));
 for(const width of [1440,390]){await p.setViewportSize({width,height:1000});await p.waitForTimeout(400);await p.screenshot({path:out+'/dismantling-'+width+'.png',fullPage:true});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
 await p.setViewportSize({width:1440,height:1000});await p.goto('/inventory?vehicle_id='+f.vehicle.id);
 await p.getByText('Уточнити категорії цього автомобіля',{exact:true}).click();await p.getByRole('button',{name:'Перевірити категорії',exact:true}).click();await expect(p.getByRole('button',{name:'Застосувати перевірені категорії',exact:true})).toBeVisible();await p.getByRole('button',{name:'Застосувати перевірені категорії',exact:true}).click();await expect(p.getByText('Категорії збережено.',{exact:true})).toBeVisible();
 saved=await(await c.request.get('/api/v1/parts?vehicle_id='+f.vehicle.id+'&limit=200')).json();assert(saved.items.every(x=>x.category_id));for(const x of saved.items)assert.deepEqual([x.quantity,x.reserved_quantity,x.selling_price,x.currency,x.oem_number,x.article_number],inventoryBefore[x.id]);
 const category=p.getByLabel('Категорія складу',{exact:true});await expect(category).toContainText('Електрика та електроніка');assert(!/carpot\.v3|Гальмівний супорт/.test(await category.textContent()));
 await p.getByRole('searchbox',{name:'Пошук запчастин',exact:true}).fill('SYN-1-1');
 const target=p.locator('article.ui3-part').filter({hasText:'SYN-1-1'});await expect(target).toHaveCount(1);const part=await(await c.request.get('/api/v1/parts/'+f.part)).json();
 const qty=target.locator('.inventory-quantity');await qty.getByRole('button',{name:'Додати 1 шт. '+part.name,exact:true}).click();await expect(qty.locator('b')).toHaveText('2 шт.');
 // Commit succeeds but browser loses its response. Persisted retry must not receive twice.
 let abort=true;await p.route('**/api/v1/parts/'+f.part+'/operations',async route=>{if(abort){abort=false;await route.fetch();await route.abort('failed');}else await route.continue();});
 await qty.getByRole('button',{name:'Додати 1 шт. '+part.name,exact:true}).click();await expect(qty.getByRole('button',{name:'Повторити збережений запит',exact:true})).toBeVisible();
 await p.reload();await p.getByRole('searchbox',{name:'Пошук запчастин',exact:true}).fill('SYN-1-1');await expect(qty.getByRole('button',{name:'Повторити збережений запит',exact:true})).toBeVisible();await qty.getByRole('button',{name:'Повторити збережений запит',exact:true}).click();await expect(qty.locator('b')).toHaveText('3 шт.');await p.unroute('**/api/v1/parts/'+f.part+'/operations');
 await qty.getByRole('button',{name:'Списати 1 шт. '+part.name,exact:true}).click();await qty.getByLabel('Причина зміни залишку',{exact:true}).fill('Пошкоджена одиниця: локальний тест');await qty.getByRole('button',{name:'Зберегти',exact:true}).click();await expect(qty.locator('b')).toHaveText('2 шт.');
 await qty.getByRole('button',{name:'Уточнити залишок '+part.name,exact:true}).click();await qty.getByLabel('Новий залишок',{exact:true}).fill('4');await qty.getByLabel('Причина зміни залишку',{exact:true}).fill('Інвентаризація: локальний тест');await qty.getByRole('button',{name:'Зберегти',exact:true}).click();await expect(qty.locator('b')).toHaveText('4 шт.');
 const after=await(await c.request.get('/api/v1/parts/'+f.part)).json();assert.equal(after.quantity,4);for(const k of ['selling_price','currency','oem_number','article_number','article_brand'])assert.equal(after[k],part[k],k);
 for(const width of [1440,390]){await p.setViewportSize({width,height:1000});await p.waitForTimeout(400);await p.screenshot({path:out+'/inventory-'+width+'.png',fullPage:true});assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'inventory overflow '+width);}
 assert.deepEqual(errors,[]);assert.equal(calls.filter(r=>r.url.includes('/lookup')).length,0);
 const result={local:true,physical_parts:96,service_types_separated:4,batch_http_requests:1,new_from_batch:93,repeated_added:0,categorized:96,quantity_plus_minus_correction:true,response_lost_reload_retry_no_duplicate:true,prices_oem_articles_preserved:true,desktop_mobile:true,js_errors:errors,paid_lookup_requests:0};
 fs.writeFileSync(out+'/results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await c.close();
}finally{await b.close();}
