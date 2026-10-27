// Real local test backend + imported fixture package; never target production.
import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Set WAREHOUSE_E2E=1 and use a dedicated imported Warehouse test DB');
const origin='http://127.0.0.1:18765';
const email=process.env.ALETO_TEST_EMAIL,password=process.env.ALETO_TEST_PASSWORD;
if(!email||!password)throw Error('Set ALETO_TEST_EMAIL and ALETO_TEST_PASSWORD for a test workspace containing the imported catalogue');
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try {
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
  const context=await browser.newContext({baseURL:origin,viewport});
  const login=await context.request.post('/api/v1/auth/login',{data:{email,password}});
  assert.equal(login.status(),200);
  const all=await (await context.request.get('/api/v1/vehicles?limit=100')).json();
  const vehicle=all.items.find(v=>v.manufacturer==='Volvo'&&v.model==='XC40');
  assert.ok(vehicle,'Create a Volvo XC40 test donor before running');
  const reference=await (await context.request.get(`/api/v1/vehicles/${vehicle.id}/aleto-catalog`)).json();
  assert.equal(reference.total,1472);
  const item=reference.items[0];
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`/vehicles?donor=${vehicle.id}`);
  await page.getByText('Aleto — довідник пропозицій',{exact:true}).click();
  await expect(page.getByText(/Пропозицій: 1472\./)).toBeVisible();
  await expect(page.getByText(/Сумісність за роком, VIN і комплектацією не перевірена/)).toBeVisible();
  await page.getByLabel('Пошук назви, артикулу або OEM').fill(item.article);
  await expect(page.getByText(/Пропозицій: 1\./)).toBeVisible();
  await expect(page.getByRole('link',{name:item.title,exact:true})).toHaveAttribute('href',item.source_url);
  const rows=await page.locator('table tbody tr').count();
  assert.equal(rows,1);
  await page.getByLabel('Пошук назви, артикулу або OEM').fill('');
  await expect(page.getByText(/Пропозицій: 1472\./)).toBeVisible();
  const category=reference.categories.find(n=>n.subcategory_id);
  await page.getByLabel('Категорія Aleto',{exact:true}).selectOption(category.category_id);
  await page.getByLabel('Підкатегорія Aleto',{exact:true}).selectOption(category.subcategory_id);
  await expect(page.locator('table tbody tr').first()).toBeVisible();
  assert.deepEqual(errors,[]);
  await context.close();
  console.log(`PASS Aleto real test catalogue, search, filters and source link ${viewport.width}px`);
 }
} finally {await browser.close();}
