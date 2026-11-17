// Narrow password-only UI acceptance; explicit synthetic loopback fixture only.
import { chromium, webkit } from '@playwright/test';
import fs from 'node:fs';
import assert from 'node:assert/strict';
if(process.env.CONTROL_CENTER_BROWSER_TEST !== '1') throw Error('Local fixture opt-in required');
const origin=process.env.CONTROL_CENTER_BROWSER_ORIGIN || 'http://127.0.0.1:5269';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw Error('Loopback fixture only');
const fixture=JSON.parse(fs.readFileSync(process.env.CONTROL_CENTER_BROWSER_FIXTURE_FILE||'/tmp/control-browser-fixture.json','utf8'));
let index=0;const report=[];
for(const [engine,driver] of Object.entries({chromium,webkit})){
 const browser=await driver.launch();
 try { for(const width of [320,1440]){
  const context=await browser.newContext({baseURL:origin,viewport:{width,height:960}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/control/');
  await page.getByRole('button',{name:'Увійти',exact:true}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('button[type=submit]')?.disabled);
  assert.equal(await page.locator('input[name=code]').count(),0);
  const username='browser-'+index++;
  const login=async password=>{
   await page.getByLabel('Логін',{exact:true}).fill(username);
   await page.getByLabel('Пароль',{exact:true}).fill(password);
   await page.getByRole('button',{name:'Увійти',exact:true}).click();
  };
  await login(fixture.password);
  await page.getByRole('heading',{name:'Огляд клієнтів',exact:true}).waitFor();
  const denied=await page.evaluate(async()=>{
   const r=await fetch('/api/control/auth/logout',{method:'POST',headers:{'X-Control-CSRF':'bad','Content-Type':'application/json'}});return r.status;
  });assert.equal(denied,403);
  await page.evaluate(()=>location.hash='#/security');
  await page.getByRole('button',{name:'Змінити пароль',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Налаштувати новий ключ MFA',exact:true}).count(),0);
  assert.equal(await page.locator('input[name=mfa_code]').count(),0);
  const next=fixture.password+'-changed';
  await page.evaluate(()=>sessionStorage.removeItem('control.csrf'));
  await page.getByLabel('Поточний пароль',{exact:true}).fill(fixture.password);
  await page.getByLabel('Новий пароль (від 12 символів)',{exact:true}).fill(next);
  await page.getByRole('button',{name:'Змінити пароль',exact:true}).click();
  await page.getByLabel('Логін',{exact:true}).waitFor();
  await login(next);
  await page.getByRole('heading',{name:'Безпека та налаштування',exact:true}).waitFor();
  await page.evaluate(()=>sessionStorage.removeItem('control.csrf'));
  if(width<=1100)await page.getByRole('button',{name:'Відкрити меню',exact:true}).click();
  await page.getByRole('button',{name:'Вийти',exact:true}).click();
  await page.getByLabel('Логін',{exact:true}).waitFor();
  const status=await page.evaluate(async()=> (await fetch('/api/control/auth/me')).status);
  assert.equal(status,401);assert.deepEqual(errors,[]);
  report.push({engine,width,password_login:true,password_change:true,csrf_recovery:true,logout:true,unauthorized:true});
  await context.close();
 }} finally { await browser.close(); }
}
console.log(JSON.stringify({passed:report.length,report}));
