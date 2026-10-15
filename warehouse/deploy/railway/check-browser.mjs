// Local test CA is pinned to its exact public key. No blanket TLS bypass.
import { chromium } from '../../frontend/node_modules/playwright/index.mjs';
import { expect } from '../../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import { X509Certificate, createHash } from 'node:crypto';
const dir = new URL('./.check/', import.meta.url);
const credentials = JSON.parse(await fs.readFile(new URL('browser.json',dir),'utf8'));
if(credentials.origin !== 'https://localhost:18443') throw new Error('Local test origin only');
const cert = new X509Certificate(await fs.readFile(new URL('cert.pem',dir)));
const pin = createHash('sha256').update(cert.publicKey.export({type:'spki',format:'der'})).digest('base64');
const browser = await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH || undefined, headless:true, args:['--no-sandbox',`--ignore-certificate-errors-spki-list=${pin}`]});
try {
 for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'iphone',width:390,height:844}]){
  const context=await browser.newContext({viewport});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error' && /Content Security Policy|Refused to/.test(m.text()))errors.push(m.text())});
  await page.goto(credentials.origin+'/inventory');
  await expect(page.getByRole('heading',{name:'З поверненням'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Зареєструватися',exact:true})).toHaveCount(0);
  await page.getByLabel('Електронна пошта').fill(credentials.email);
  await page.getByLabel('Пароль').fill(credentials.password);
  await page.getByRole('button',{name:'Увійти',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Огляд складу',exact:true})).toBeVisible();
  const cookies=await context.cookies();
  const session=cookies.find(c=>c.name==='warehouse_session');
  const csrf=cookies.find(c=>c.name==='warehouse_csrf');
  expect(session.secure && session.httpOnly && session.sameSite==='Strict' && session.path==='/api/v1').toBe(true);
  expect(csrf.secure && !csrf.httpOnly && csrf.path==='/').toBe(true);
  await page.goto(credentials.origin+'/vehicles');
  await expect(page.getByRole('heading',{name:'Автомобілі-донори'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Local test fixture Transport check',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:new URL(`${viewport.name}-https.png`,dir).pathname,fullPage:true});
  await page.getByRole('button',{name:'Вийти',exact:true}).click();
  await expect(page.getByRole('heading',{name:'З поверненням'})).toBeVisible();
  expect(errors).toEqual([]);
  console.log(`PASS: production HTTPS browser workflow · ${viewport.name}, secure cookies, deep links, CSP, logout`);
  await context.close();
 }
}finally{await browser.close()}
