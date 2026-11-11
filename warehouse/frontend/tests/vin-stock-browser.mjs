// Real local UI/API, synthetic VIN and source adapters. Never staging/live fitment proof.
import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Explicit localhost test only');
fs.mkdirSync('/tmp/vin-stock-qa',{recursive:true});
const b=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
try{
 const c=await b.newContext({baseURL:'http://127.0.0.1:5235',viewport:{width:1440,height:1000}});
 const r=await c.request.post('/api/v1/auth/register',{data:{name:'Synthetic VIN Stock QA',email:`vin-stock-${crypto.randomUUID()}@example.test`,password:'local-synthetic-test-password'}});assert.equal(r.status(),201);
 const auth=await r.json(),page=await c.newPage(),errors=[],paid=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/\/plan-parts\/|market-refresh|parser-jobs/.test(r.url()))paid.push(r.url())});
 await page.goto('/vehicles');await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.getByLabel('VIN',{exact:true}).fill('YV4A22PK2G1092943');
 await dialog.getByRole('button',{name:'Визначити автомобіль',exact:true}).click();await expect(dialog).toContainText('Локальні синтетичні дані');
 await dialog.getByLabel('Характеристики перевірено, підтверджую додавання').check();await dialog.getByRole('button',{name:'Додати автомобіль',exact:true}).click();await expect(dialog).not.toBeVisible();
 await page.getByRole('button',{name:'Розбір і запчастини',exact:true}).click();
 await page.getByRole('button',{name:'Вибрати точну модифікацію',exact:true}).click();
 const form=page.getByRole('form',{name:'Модифікація наявного автомобіля'});
 await form.getByLabel('Марка',{exact:true}).selectOption('Volvo');await form.getByLabel('Модель',{exact:true}).selectOption('13084');await form.getByLabel('Покоління',{exact:true}).selectOption('II (fixture)');await form.getByLabel('Модифікація',{exact:true}).selectOption('107555');
 await form.getByRole('checkbox').check();await form.getByRole('button',{name:'Підтвердити модифікацію'}).click();await expect(form).not.toBeVisible();
 const generator=page.getByRole('region',{name:'Універсальний каталог запчастин'});
 await generator.getByRole('button',{name:'Розібрати на запчастини',exact:true}).click();await expect(generator).toContainText('Доступних типів: 2');await generator.getByRole('button',{name:'Зберегти перелік',exact:true}).click();
 const tree=page.getByRole('region',{name:'Фізичний склад вузлів'});
 await expect(tree.getByLabel('Вибрати: Тестовий стартер',{exact:true})).toBeVisible();
 // Category selection must not receive the other category.
 await tree.getByRole('navigation',{name:'Категорії запчастин'}).getByRole('button',{name:/Електрика та електроніка/}).click();
 const all=tree.getByLabel('Вибрати всі за поточними фільтрами',{exact:true});await all.check();
 let bar=tree.getByRole('region',{name:'Масові дії'});if(await bar.count()===0)bar=tree.getByLabel('Масові дії',{exact:true});
 await bar.getByRole('button',{name:'Є в авто (1)',exact:true}).click();await expect(tree.getByRole('status').filter({hasText:'Оновлено: 1'}).first()).toBeVisible();
 // The explicit receipt also confirms actual dismantling: no separate mass action.
 await all.check();await tree.getByRole('button',{name:'Додати вибрані на склад',exact:true}).click();
 const receipt=tree.getByRole('region',{name:'Підтвердження надходження'});await expect(receipt).toContainText('До надходження: 1');await expect(receipt).toContainText('Підтвердимо демонтаж: 1');
 await receipt.getByLabel(/Підтверджую фактичний демонтаж і надходження 1 деталей/).check();await receipt.getByRole('button',{name:'Оприбуткувати 1 деталей'}).click();await expect(receipt).not.toBeVisible();
 const cookie=(await c.cookies()).find(r=>r.name==='warehouse_session').value;
 const vehicles=await (await c.request.get('/api/v1/vehicles')).json();assert.equal(vehicles.items.length,1);const v=vehicles.items[0];
 const parts=await (await c.request.get('/api/v1/parts?vehicle_id='+v.id)).json();assert.equal(parts.items.length,1);assert.equal(parts.items[0].quantity,1);assert.match(parts.items[0].name,/Тестовий стартер/);
 const nodes=await (await c.request.get(`/api/v1/vehicles/${v.id}/assemblies`)).json();assert.equal(nodes.items.find(n=>n.name==='Тестова фара').part_id,null);
 const managed=await (await c.request.get(`/api/v1/vehicles/${v.id}/dismantling-v3`)).json();assert.equal(managed.items.find(n=>n.name==='Тестовий стартер').operational_state,'received');
 await page.reload();await page.getByRole('button',{name:'Розбір і запчастини',exact:true}).click();await expect(tree).toContainText('На складі');
 await page.screenshot({path:'/tmp/vin-stock-qa/desktop-1440.png',fullPage:false});await page.setViewportSize({width:390,height:844});await tree.scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:'/tmp/vin-stock-qa/mobile-390.png',fullPage:false});
 assert.deepEqual(errors,[]);assert.deepEqual(paid,[]);
 console.log('LOCAL SYNTHETIC UI PASS: VIN→same donor→explicit exact IDs→2-type plan→category selection→presence→explicit dismantle+receipt→1 stock receipt; other category untouched; reload; 1440/390 no overflow/JS errors/paid calls.');
 await c.close();
}finally{await b.close()}
