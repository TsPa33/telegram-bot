import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Disposable local PostgreSQL required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport}),page=await context.newPage();
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Майстерня 5.8.1',email:`ux581-${viewport.width}-${Date.now()}@example.test`,password:'local-director-password'}});assert(auth.ok());const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 const post=async(path,data)=>{const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();};
 await page.goto(origin+'/statistics');await expect(page.getByText('Поки немає даних для діаграми.').first()).toBeVisible();
 const v=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010});
 for(const currency of ['UAH','USD']){const p=await post('/parts',{name:'Генератор '+currency,vehicle_id:v.id,selling_price:'120.25',currency,condition:'used'});await post('/parts/'+p.id+'/operations',{type:'receipt',quantity:3,reason:'Local isolated chart test'});}
 await page.reload();await expect(page.getByRole('region',{name:'Запчастини за категоріями'})).toContainText('6');
 const chart=page.getByRole('region',{name:'Оціночна вартість за автомобілями · USD'});await expect(chart).toContainText('360,75');
 const bar=chart.getByRole('button');await bar.focus();await page.keyboard.press('Enter');await expect(bar).toHaveAttribute('aria-pressed','true');
 await fs.mkdir('test-results',{recursive:true});await page.screenshot({path:`test-results/ux581-statistics-${viewport.width}.png`,fullPage:true});
 await page.goto(origin+'/team');await expect(page.getByRole('region',{name:'Підсумки команди'})).toContainText('Директори');
 if(viewport.width<=800)await page.getByRole('button',{name:'Відкрити меню',exact:true}).click();
 const link=page.locator('nav').getByRole('link',{name:'Команда',exact:true});await expect(link).toBeVisible();await expect(link).toHaveAttribute('aria-current','page');
 if(viewport.width<=800)await page.getByRole('button',{name:'Закрити меню',exact:true}).click();
 await page.screenshot({path:`test-results/ux581-team-${viewport.width}.png`,fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await context.close();console.log('PASS UX581 real charts/empty/currencies/keyboard/team/nav',viewport.width);
}}finally{await browser.close();}
