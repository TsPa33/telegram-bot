// Local two-database financial acceptance. Hosted page/return and provider evidence are synthetic.
import {chromium,webkit,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit disposable browser acceptance only');
const origin=process.env.GLOBAL_BILLING_ORIGIN||'http://127.0.0.1:5255',out=process.env.GLOBAL_BILLING_OUTPUT||'/tmp/carpot-global-billing';
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Local browser only');
const fixtureKey=process.env.BILLING_BROWSER_FIXTURE_KEY||'local-browser-driver-secret-123456789';fs.mkdirSync(out,{recursive:true});
const report=[];
for(const [engineName,engine] of Object.entries(process.env.GLOBAL_BILLING_ENGINE==='chromium'?{chromium}:process.env.GLOBAL_BILLING_ENGINE==='webkit'?{webkit}:{chromium,webkit})){
 const browser=await engine.launch({headless:true});
 try{for(const width of (process.env.GLOBAL_BILLING_WIDTHS?process.env.GLOBAL_BILLING_WIDTHS.split(',').map(Number):[320,390,430,1440]))for(const style of (process.env.GLOBAL_BILLING_STYLES?process.env.GLOBAL_BILLING_STYLES.split(','):['light','onyx','gold','forest'])){
  const c=await browser.newContext({baseURL:origin,viewport:{width,height:900}}),page=await c.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const auth=await c.request.post('/api/v1/auth/register',{headers:{'X-Forwarded-For':'198.18.'+crypto.randomInt(1,250)+'.'+crypto.randomInt(1,250)},data:{name:'Synthetic Billing Browser',email:'global-'+crypto.randomUUID()+'@example.test',password:'global-browser-only-password'}});assert.equal(auth.status(),201,await auth.text());
  let inviterContext,inviterPage,inviterLink;
  if(width===390&&style==='forest'){
   inviterContext=await browser.newContext({baseURL:origin,viewport:{width,height:900}});inviterPage=await inviterContext.newPage();
   const invited=await inviterContext.request.post('/api/v1/auth/register',{headers:{'X-Forwarded-For':'198.19.'+crypto.randomInt(1,250)+'.'+crypto.randomInt(1,250)},data:{name:'Synthetic Referrer',email:'referrer-'+crypto.randomUUID()+'@example.test',password:'global-browser-only-password'}});
   assert.equal(invited.status(),201,await invited.text());
   await inviterPage.goto('/settings?section=referrals');const refs=inviterPage.getByRole('region',{name:'Реферальна програма',exact:true});
   await refs.getByRole('button',{name:'Підключити компанію',exact:true}).click();
   await refs.getByRole('button',{name:'Отримати посилання',exact:true}).click();
   await expect(refs.getByRole('textbox',{name:'Персональне посилання'})).toBeVisible();
   inviterLink=await refs.getByRole('textbox',{name:'Персональне посилання'}).inputValue();
   assert.match(inviterLink,/\/settings\?section=referrals&ref=[A-F0-9]{16}$/);
   await page.goto(inviterLink);const invite=page.getByRole('region',{name:'Реферальна програма',exact:true});
   await invite.getByRole('button',{name:'Підключити компанію',exact:true}).click();
   await invite.getByRole('button',{name:'Підтвердити запрошення',exact:true}).click();
   await expect(invite).toContainText('Запрошення вже прив’язане до вашої компанії.'.replace('’',"'"));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await page.goto('/settings?section=general');
  const themeNames={light:/Світла/,onyx:/Onyx/,gold:/Midnight Gold/,forest:/Forest Slate/};
  await page.getByRole('region',{name:'Оформлення',exact:true}).getByRole('button',{name:themeNames[style]}).click();
  await page.goto('/settings?section=payments');const panel=page.getByRole('region',{name:'Підписка та оплата',exact:true});
  if(!inviterContext)await panel.getByRole('button',{name:'Підключити оплату CarPot',exact:true}).click();await expect(panel.getByRole('button',{name:'Обрати Standard',exact:true})).toBeEnabled();
  let invoiceLost=false,invoiceCalls=0;
  if(width===390&&style==='gold')await page.route('**/api/v1/billing/invoices',async route=>{invoiceCalls++;await route.fetch();invoiceLost=true;await route.abort('failed');});
  await panel.getByRole('button',{name:'Обрати Standard',exact:true}).click();
  if(width===390&&style==='gold'){
   await expect(panel.getByRole('button',{name:'Відновити запит оплати',exact:true})).toBeVisible();await expect.poll(()=>invoiceLost).toBe(true);await expect(panel.getByRole('alert')).toBeVisible();await page.unroute('**/api/v1/billing/invoices');await page.reload();await panel.getByRole('button',{name:'Відновити запит оплати',exact:true}).click();assert.equal(invoiceCalls,1);
  }
  const summary=panel.getByRole('region',{name:'Підтвердження оплати',exact:true});await expect(summary).toContainText('Standard');await expect(summary).toContainText('1 000');
  let orderId,hostedRequests=0;
  await page.route('https://www.liqpay.ua/api/3/checkout',async route=>{
   hostedRequests++;const form=new URLSearchParams(route.request().postData());const data=form.get('data'),signature=form.get('signature');
   assert.equal(crypto.createHash('sha3-256').update('sandbox_global_browser_private'+data+'sandbox_global_browser_private').digest('base64'),signature);
   const payload=JSON.parse(Buffer.from(data,'base64').toString());assert.equal(payload.amount,'1000.00');assert.equal(payload.currency,'UAH');assert.equal(payload.version,7);assert.equal(payload.public_key,'sandbox_global_browser_public');assert(!Object.hasOwn(payload,'private_key'));orderId=payload.order_id;
   const returnUrl=origin+'/settings?section=payments&billing_order='+encodeURIComponent(orderId);
   await route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><title>Synthetic hosted checkout</title><p>Локальна синтетична сторінка. Реальних коштів немає.</p><a href="'+returnUrl+'">Повернутися до CarPot</a>'});
  });
  let checkoutLost=false;
  if(width===430&&style==='forest')await page.route('**/api/v1/billing/checkout',async route=>{await route.fetch();checkoutLost=true;await route.abort('failed');});
  await summary.getByRole('button',{name:'Оплатити через LiqPay',exact:true}).click();
  if(width===430&&style==='forest'){
   await expect(panel.getByRole('button',{name:'Відновити запит оплати',exact:true})).toBeVisible();await expect.poll(()=>checkoutLost).toBe(true);await expect(panel.getByRole('alert')).toBeVisible();await page.unroute('**/api/v1/billing/checkout');await page.reload();await panel.getByRole('button',{name:'Відновити запит оплати',exact:true}).click();
  }
  try{await page.getByRole('link',{name:'Повернутися до CarPot',exact:true}).click();}catch(e){console.log(JSON.stringify({url:page.url(),hostedRequests,alerts:await page.getByRole('alert').allTextContents(),errors}));await page.screenshot({path:out+'/failure.png'});throw e;}await expect(panel.getByRole('region',{name:'Стан оплати',exact:true})).toContainText('Очікуємо підтвердження LiqPay');
  await page.screenshot({path:out+'/'+engineName+'-'+width+'-'+style+'-pending.png',animations:'disabled'});
  assert.equal(hostedRequests,1);assert(orderId);
  const confirmation=await c.request.post('/api/v1/__billing_fixture/confirm',{headers:{'X-Fixture-Key':fixtureKey},data:{order_id:orderId}});assert.equal(confirmation.status(),200,await confirmation.text());assert.equal((await confirmation.json()).synthetic_only,true);
  await expect(panel).toContainText('Оплату підтверджено. Підписку активовано.',{timeout:20000});await expect(panel).toContainText('Автомобілі 0/10');await expect(panel).toContainText('Оплачено до');await expect(panel).toContainText('Поточний період до');await expect(panel.getByRole('heading',{name:'Оплату успішно підтверджено',exact:true})).toBeVisible();await expect(panel.getByRole('img',{name:'Автомобілі: зайнято 0, місткість 10, вільно 10, понад ліміт 0'})).toBeVisible();await expect(panel.getByRole('button',{name:'Повернутися до оплат',exact:true})).toBeVisible();
  const check=await c.request.get('/api/v1/__billing_fixture/order/'+orderId,{headers:{'X-Fixture-Key':fixtureKey}});assert.equal(check.status(),200);assert.deepEqual(await check.json(),{settlements:1,orders:1,amount_minor:100000,synthetic_only:true});
  await expect(panel.getByRole('heading',{name:'Історія оплат',exact:true})).toBeVisible();assert.equal(await page.locator('input[autocomplete=cc-number],input[autocomplete=cc-csc]').count(),0);if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)){await page.screenshot({path:out+'/overflow-'+engineName+'-'+width+'-'+style+'.png'});console.log(await page.locator('body *').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().right>innerWidth+1).map(n=>({tag:n.tagName,class:n.className,text:n.textContent?.slice(0,80)})).slice(-20)));}assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:out+'/'+engineName+'-'+width+'-'+style+'-active.png',animations:'disabled'});assert.deepEqual(errors,[]);
  if(inviterContext){
   await inviterPage.reload();const refs=inviterPage.getByRole('region',{name:'Реферальна програма',exact:true});
   await expect(refs.getByText('Історія винагород',{exact:true})).toBeVisible();
   const dashboard=await inviterContext.request.get('/api/v1/billing/referrals');assert.equal(dashboard.status(),200,await dashboard.text());const d=await dashboard.json();assert.equal(d.invited,1);assert.equal(d.converted,1);assert.equal(d.balances.pending_minor,20000);assert.equal(d.balances.available_minor,0);assert.equal(d.rewards.length,1);
   await expect(refs).toContainText('200,00');await inviterPage.screenshot({path:out+'/'+engineName+'-referrals.png',animations:'disabled'});await inviterContext.close();
  }
  report.push({engine:engineName,width,style,invoiceLost,checkoutLost,serverConfirmed:true,settlements:1,providerOrders:1,realLiqPayTest:false});await c.close();console.log('PASS synthetic global billing '+engineName+' '+width+' '+style);
 }}finally{await browser.close();}
}
fs.writeFileSync(out+'/report.json',JSON.stringify(report,null,2));
