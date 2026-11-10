// Built UI + guarded local PostgreSQL, synthetic 552-placement donor.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local harness only');
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
const out=process.env.WAREHOUSE_SCREENSHOTS||'/tmp/carpot-assembly-qa';fs.mkdirSync(out,{recursive:true});
try{for(const width of [1440,390]){
 const context=await browser.newContext({baseURL:'http://127.0.0.1:5231',viewport:{width,height:900}});
 const signup=await context.request.post('/api/v1/auth/register',{data:{name:'Assembly QA',email:`assembly-${crypto.randomUUID()}@example.test`,password:'assembly-synthetic-test-password'}});
 assert.equal(signup.status(),201);const auth=await signup.json();
 const seed=await context.request.post('http://127.0.0.1:8031/__assembly_fixture',{headers:{'X-CSRF-Token':auth.csrf_token,Cookie:context.cookies?`warehouse_session=${(await context.cookies()).find(c=>c.name==='warehouse_session').value}`:''}});
 assert.equal(seed.status(),200,await seed.text());const fixture=await seed.json();
 const page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/assemblies'))requests.push(r.url())});
 await page.goto('/vehicles?donor='+fixture.vehicle_id);
 const tree=page.getByRole('region',{name:'Фізичний склад вузлів',exact:true});
 await expect(tree).toContainText('Потенційні: 552');
 assert.equal(await tree.locator('.assembly-roots > li').count(),50);
 await tree.getByRole('button',{name:'Розгорнути Двері передні ліві в зборі',exact:true}).click();
 await expect(tree.locator('.assembly-roots')).toContainText('Компонент дверей 12');
 await page.screenshot({path:`${out}/assembly-expanded-${width}.png`,fullPage:false});
 await tree.getByRole('button',{name:'Двері передні ліві в зборі',exact:true}).click();
 await expect(tree.getByRole('heading',{name:'Фактичний склад'})).toBeVisible();
 assert.equal(await tree.locator('.assembly-inspector > ul > li').count(),13);
 await page.screenshot({path:`${out}/assembly-preview-${width}.png`,fullPage:false});
 await tree.getByRole('button',{name:'Закрити склад вузла'}).click();
 await tree.getByLabel('Пошук у дереві').fill('Потенційна позиція 551');
 assert.equal(await tree.locator('.assembly-roots > li').count(),1);
 await tree.getByLabel('Пошук у дереві').fill('');
 // Only one readiness + one bounded tree read; expanding/search makes no calls.
 assert.equal(requests.filter(u=>u.endsWith('/assemblies')).length,1);
 await tree.getByRole('button',{name:'Двері передні ліві в зборі',exact:true}).click();
 await tree.getByLabel('Фактична ціна').fill('750');await tree.getByLabel('Підтверджую передачу всього наведеного складу за одну ціну').check();
 await tree.getByRole('button',{name:'Продати вузол у зборі',exact:true}).click();
 await expect(tree).toContainText('Передано у вузлах: 12');
 await page.reload();await expect(page.getByRole('region',{name:'Фізичний склад вузлів',exact:true})).toContainText('Передано у вузлах: 12');
 assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:`${out}/assembly-${width}.png`,fullPage:true});
 await page.getByRole('button',{name:'Ніч',exact:true}).click();
 await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:`${out}/assembly-night-${width}.png`,fullPage:false});
 console.log(`${width}: PASS (552 nodes, collapse/search, real local sale+reload, no N+1/JS errors/overflow)`);
 await context.close();
}}finally{await browser.close()}
