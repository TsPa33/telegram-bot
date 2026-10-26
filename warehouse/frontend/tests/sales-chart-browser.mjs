import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local PostgreSQL required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport}),page=await context.newPage();
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Майстерня · аналітика',email:`chart-${viewport.width}-${Date.now()}@example.test`,password:'local-director-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 await page.goto(origin+'/statistics');const trend=page.getByRole('region',{name:'Динаміка продажів',exact:true});
 await expect(trend).toContainText('За обраний період проведених продажів немає.');
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010});
 for(const currency of ['UAH','USD']){
  const p=await post('/parts',{name:'Генератор · '+currency,vehicle_id:v.id,selling_price:'999.99',currency,condition:'used'});
  await post('/parts/'+p.id+'/operations',{type:'receipt',quantity:3,reason:'Local isolated chart test'});
  const body={type:'sale',quantity:2,sale_price:'12.34',sale_currency:currency,request_key:crypto.randomUUID()};
  await post('/parts/'+p.id+'/operations',body);await post('/parts/'+p.id+'/operations',body);
 }
 await page.reload();await expect(trend).toContainText('Продано одиниць: 4');
 for(const currency of ['UAH','USD']){
  const chart=trend.getByRole('region',{name:'Сума продажів · '+currency,exact:true});
  await expect(chart.getByRole('button').first()).toContainText('24,68');const bar=chart.getByRole('button').filter({hasText:'24,68'});await expect(bar).toHaveCount(1);
  await bar.scrollIntoViewIfNeeded();await bar.focus();await page.keyboard.press('Enter');
  await expect(bar).toHaveAttribute('aria-pressed','true');await expect(bar).toHaveAttribute('title',/24,68.*2 од/);
  await expect(chart.getByRole('status')).toContainText('24,68');
 }
 for(const interval of ['week','month','day']){
  await trend.getByLabel('Групування продажів',{exact:true}).selectOption(interval);
  await expect(trend.getByRole('region',{name:'Сума продажів · USD',exact:true})).toContainText('24,68');
 }
 await trend.getByLabel('Часовий пояс продажів',{exact:true}).selectOption('UTC');
 await expect(trend).toContainText('Продано одиниць: 4');
 await trend.getByLabel('Продажі від',{exact:true}).fill('2020-01-01');await trend.getByLabel('Продажі до',{exact:true}).fill('2020-01-02');await trend.getByRole('button',{name:'Показати',exact:true}).click();
 await expect(trend).toContainText('За обраний період проведених продажів немає.');
 await trend.getByRole('button',{name:'Останні 7 днів',exact:true}).click();await expect(trend).toContainText('Продано одиниць: 4');
 // Test error rendering only; data tests above use real SQL responses.
 await page.route('**/api/v1/sales/summary?*',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Тимчасово недоступно'})}));
 await trend.getByLabel('Групування продажів',{exact:true}).selectOption('week');
 await expect(trend.getByRole('alert')).toContainText('Тимчасово недоступно');
 await expect(trend.getByRole('region',{name:'Сума продажів · USD',exact:true})).toHaveCount(0);
 await page.unroute('**/api/v1/sales/summary?*');await trend.getByRole('button',{name:'Повторити завантаження продажів',exact:true}).click();
 await expect(trend).toContainText('Продано одиниць: 4');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 const geometry=await trend.locator('.chart-bar').evaluateAll(rows=>rows.every(row=>{
  const children=[...row.children],boxes=children.map(el=>el.getBoundingClientRect());
  const noOverlap=boxes.every((a,i)=>boxes.every((b,j)=>i===j||Math.min(a.right,b.right)-Math.max(a.left,b.left)<=1||Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)<=1));
  return noOverlap&&children.every(el=>el.scrollWidth<=el.clientWidth+1);
 }));assert(geometry,'Chart date/track/value must neither overlap nor overflow');

 await fs.mkdir('test-results',{recursive:true});await trend.scrollIntoViewIfNeeded();await page.screenshot({path:`test-results/ux581-sales-chart-${viewport.width}.png`,fullPage:true});await trend.screenshot({path:`test-results/ux581-sales-detail-${viewport.width}.png`});
 await context.close();console.log('PASS actual SQL sale chart/replay/currencies/periods/empty/keyboard/error',viewport.width);
}}finally{await browser.close();}
