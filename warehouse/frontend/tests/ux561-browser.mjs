import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local DB required');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const origin='http://127.0.0.1:5173',before=!!process.env.LAYOUT_BEFORE;
await fs.mkdir('test-results',{recursive:true});
try{for(const size of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport:size}),page=await context.newPage();
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Layout worker',email:`layout-${size.width}-${Date.now()}@example.test`,password:'offline-layout-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010});
 await post('/categories/import',{source:'layout-local',nodes:[{key:'power',name:'Силовий агрегат',kind:'category'},{key:'engine',name:'Двигун та навісне',parent_key:'power',kind:'subcategory'}]});
 const cats=(await (await context.request.get(origin+'/api/v1/categories')).json()).items;
 for(const [i,name] of ['Генератор','Генератор із дуже довгою назвою та додатковими характеристиками кріплення без скорочення тексту','Деталь без підкатегорії'].entries()){
 const p=await post('/parts',{vehicle_id:v.id,name,category_id:cats.find(c=>c.external_key==='power').id,...(i<2?{subcategory_id:cats.find(c=>c.external_key==='engine').id}:{}),condition:'used',availability:'unchecked',internal_notes:'Потрібно перевірити контакти. Довга внутрішня нотатка\nДругий рядок нотатки',...(i===0?{selling_price:'1234.56',location:'Стелаж-А / полиця-123456789012345678901234567890'}:{})});
 await post(`/parts/${p.id}/operations`,{type:'receipt',quantity:2,reason:'Layout fixture'});
 }
 await page.goto(origin+'/inventory');await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await page.getByRole('button',{name:/Volvo XC90.*2010/}).click();
 await page.locator('.donor-stock-tree>details>summary').click();
 for(const s of await page.locator('.donor-stock-subcategory>summary').all())await s.click();
 await expect(page.locator('.donor-part-row')).toHaveCount(3);
 for(const zoom of [1,1.25,1.5]){
 // CSS zoom exercises layout at enlarged content size; physical browser UI zoom is not automated here.
 await page.evaluate(z=>document.documentElement.style.zoom=String(z),zoom);
 await page.screenshot({path:`test-results/ux561-${before?'before':'after'}-${size.width}-${zoom}.png`,fullPage:true});
 console.log('geometry',size.width,zoom,await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,inner:innerWidth,rect:document.documentElement.getBoundingClientRect().width,offenders:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+2).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])})));
 const collisions=await page.locator('.donor-part-row').evaluateAll(rows=>rows.flatMap(row=>{const els=[...row.children],out=[];for(let i=0;i<els.length;i++)for(let j=i+1;j<els.length;j++){const a=els[i].getBoundingClientRect(),b=els[j].getBoundingClientRect();if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)out.push([els[i].tagName,els[j].tagName]);}return out;}));
 if(before)console.log('BASELINE overlaps',size.width,zoom,JSON.stringify(collisions));else {assert.deepEqual(collisions,[],`overlap ${size.width}/${zoom}`);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'horizontal overflow');}
 }
 await page.evaluate(()=>document.documentElement.style.zoom='1');
 await page.getByRole('button',{name:'Генератор',exact:true}).click();await expect(page.getByRole('dialog',{name:'Генератор',exact:true})).toBeVisible();await page.getByRole('button',{name:'Закрити',exact:true}).click();
 await page.getByRole('button',{name:'Загальний склад',exact:true}).click();await expect(page.locator('.desktop-table:visible tbody tr,.seller-card:visible')).toHaveCount(3);
 for(const zoom of [1,1.25,1.5]){
 await page.evaluate(z=>document.documentElement.style.zoom=String(z),zoom);
 await page.screenshot({path:`test-results/ux561-general-${size.width}-${zoom}.png`,fullPage:true});
 if(!before)assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'general warehouse overflow');
 }

 await context.close();console.log('PASS layout',size.width,before?'baseline':'fixed');
}}finally{await browser.close();}
