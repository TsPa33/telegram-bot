import {chromium,webkit,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
const origin=process.env.WAREHOUSE_BROWSER_URL||'http://127.0.0.1:5226';
const out=process.env.WAREHOUSE_BILLING_SCREENSHOTS||'../docs/billing-phase2/screenshots';fs.mkdirSync(out,{recursive:true});
const reports=[];
for(const [name,engine] of Object.entries({chromium,webkit})){
 const browser=await engine.launch({headless:true});
 try{for(const width of [320,390,430,1440]){
  const c=await browser.newContext({viewport:{width,height:900},baseURL:origin});
  const response=await c.request.post('/api/v1/auth/register',{data:{name:'Billing Phase2 fixture',email:'phase2-'+crypto.randomUUID()+'@example.test',password:'phase2-browser-only-password'}});
  assert.equal(response.status(),201,await response.text());const auth=await response.json();
  const headers={'X-CSRF-Token':auth.csrf_token};const p=await c.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto('/settings?section=payments');const panel=p.getByRole('region',{name:'Підписка та оплата',exact:true});
  await expect(panel).toBeVisible();await panel.getByRole('button',{name:'Активувати CarPot безкоштовно на 10 днів',exact:true}).click();
  await expect(panel.getByRole('heading',{name:/Standard · Тестовий період/})).toBeVisible();await expect(panel).toContainText('Автомобілі 0/10');
  // Trusted disposable test driver; there is no product endpoint for enrollment.
  assert(process.env.WAREHOUSE_DATABASE_URL?.includes('127.0.0.1')&&process.env.WAREHOUSE_DATABASE_URL?.endsWith('_test'));
  execFileSync(process.env.WAREHOUSE_TEST_PYTHON||'python',['-c',`import os,sys,psycopg
with psycopg.connect(os.environ['WAREHOUSE_DATABASE_URL'].replace('postgresql+psycopg:','postgresql:')) as c:
 c.execute("UPDATE warehouse_entitlement_workspaces SET mode='enforce' WHERE workspace_id=%s",(sys.argv[1],))`,auth.user.id]);
  const vehicle=n=>({manufacturer:'Test',model:'Billing donor',year:2020,donor_id:'Browser-'+n});
  for(let i=0;i<10;i++){const r=await c.request.post('/api/v1/vehicles',{headers,data:vehicle(i)});assert.equal(r.status(),201,await r.text());}
  assert.equal((await c.request.post('/api/v1/vehicles',{headers,data:vehicle(11)})).status(),409);
  await p.reload();await expect(panel).toContainText('Автомобілі 10/10');
  await panel.getByRole('button',{name:'Розрахувати за залишок періоду',exact:true}).click();await expect(panel.getByText(/До сплати/)).toBeVisible();
  for(const theme of ['gold','forest']){
   await p.goto('/settings?section=general');
   await p.getByRole('region',{name:'Оформлення',exact:true}).getByRole('button',{name:theme==='gold'?/Midnight Gold/:/Forest Slate/}).click();
   await p.goto('/settings?section=payments');await expect(panel).toContainText('Автомобілі 10/10');
   assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow '+width);
   await p.screenshot({path:`${out}/${name}-${width}-${theme}.png`,fullPage:true,animations:'disabled'});
  }
  await expect(panel.getByRole('button',{name:'Оплата LiqPay недоступна',exact:true})).toBeDisabled();
  const deadline=(await(await c.request.get('/api/v1/billing/entitlements')).json()).period_end;
  await panel.getByRole('combobox',{name:'Тариф тестового періоду',exact:true}).selectOption('premium');await panel.getByRole('button',{name:'Змінити тариф trial без зміни строку',exact:true}).click();
  await expect(panel.getByRole('heading',{name:/Premium · Тестовий період/})).toBeVisible();
  assert.equal((await(await c.request.get('/api/v1/billing/entitlements')).json()).period_end,deadline);
  assert.deepEqual(errors,[]);reports.push({engine:name,width,themes:['gold','forest'],authenticated:true,lastSlot:true,quote:true,trialDeadlinePreserved:true,jsErrors:errors});await c.close();console.log('PASS',name,width);
 }}finally{await browser.close();}
}
fs.writeFileSync(out+'/report.json',JSON.stringify(reports,null,2));
