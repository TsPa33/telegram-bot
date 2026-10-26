// This suite requires the REAL local backend flag to be false; no readiness/auth mocks.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Dedicated local PostgreSQL required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Майстерня Stage3',email:`disabled-${viewport.width}-${Date.now()}@example.test`,password:'local-director-password'}});assert.equal(auth.status(),201);
 const profile=await auth.json(),headers={'X-CSRF-Token':profile.csrf_token};
 const readiness=await context.request.get(origin+'/api/v1/team/readiness');assert.equal(readiness.status(),200);assert.equal((await readiness.json()).employee_creation_enabled,false);
 await page.goto(origin+'/settings');await page.locator('main').getByRole('link',{name:'Команда',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Команда',exact:true})).toBeVisible();
 await expect(page.getByRole('status').filter({hasText:'Створення співробітників ще не ввімкнено'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Додати працівника',exact:true})).toHaveCount(0);
 await expect(page.locator('.team-list')).toContainText('Директор');await expect(page.locator('.team-list')).toContainText('Дозволів: 31');
 const denied=await context.request.post(origin+'/api/v1/team',{headers,data:{name:'Must not exist',email:'blocked-create@example.test',password:'local-temporary-password'}});assert.equal(denied.status(),403);
 assert.equal((await (await context.request.get(origin+'/api/v1/team')).json()).total,1);
 await page.getByRole('searchbox',{name:'Пошук працівників на сторінці'}).fill('Невідомий');await expect(page.getByRole('heading',{name:'Працівників не знайдено'})).toBeVisible();
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 await fs.mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/team-disabled-${viewport.width}.png`,fullPage:true});
 await context.close();console.log('PASS real creation-disabled API/UI',viewport.width);
}}finally{await browser.close();}
