// Production assets; all backend responses are intercepted. No provider requests.
import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const load = async name => JSON.parse(await readFile(new URL('../../backend/tests/fixtures/'+name, import.meta.url),'utf8')).data.results;
const brands = await load('plan_parts_brands_708.json');
const year = value => value === null ? null : Number(value.slice(0,4));
const models = (await load('plan_parts_models_vw_121_292.json')).map(m => ({...m,year_from:year(m.year_from),year_to:year(m.year_to)}));
const mods = (await load('plan_parts_modifications_golf4_1994_35.json')).map(m => ({...m,year_from:year(m.year_from),year_to:year(m.year_to)}));

const origin = 'http://127.0.0.1:18764';
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '18764', '--strictPort'], {stdio:'pipe'});
let browser;
try {
  for (let i=0; i<50; i++) {
    try { if ((await fetch(origin)).ok) break; } catch {}
    if (i === 49) throw new Error('Preview startup timeout');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH || '/usr/bin/chromium',args:['--no-sandbox']});
  for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const context = await browser.newContext({viewport});
    const page = await context.newPage();
    const requests=[], errors=[];
    let saved;
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const path=url.pathname;
      requests.push(path);
      const reply = data => route.fulfill({json:data});
      if (path.endsWith('/auth/me')) return reply({id:'test-account',name:'Тест',email:'test@example.test'});
      if (path.endsWith('/brands/lookup')) return reply(brands);
      if (path.endsWith('/models/lookup')) {
        assert.equal(url.searchParams.get('mfa_id'),'121');
        return reply(models);
      }
      if (path.endsWith('/modifications/lookup')) {
        assert.equal(url.searchParams.get('ms_id'),'1994');
        return reply(mods);
      }
      if (path.endsWith('/vehicles') && request.method()==='POST') {
        saved=request.postDataJSON(); return reply({id:'new',...saved});
      }
      if (path.endsWith('/vehicles')) return reply({items:[],total:0});
      throw new Error('Unexpected backend request: '+path);
    });
    await page.goto(origin+'/vehicles');
    await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
    assert.equal(requests.filter(p=>p.includes('/plan-parts/')).length,0);
    await page.getByRole('button',{name:'Завантажити марки / повторити',exact:true}).click();
    await page.getByRole('combobox',{name:'Марка',exact:true}).selectOption('121');
    await page.getByRole('button',{name:'Завантажити моделі / повторити',exact:true}).click();
    await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption('1994');
    await expect(page.getByRole('spinbutton',{name:'Рік',exact:true})).toHaveAttribute('min','1997');
    await expect(page.getByRole('spinbutton',{name:'Рік',exact:true})).toHaveAttribute('max','2008');
    await page.getByRole('spinbutton',{name:'Рік',exact:true}).fill('2001');
    await page.getByRole('button',{name:'Завантажити модифікації / повторити',exact:true}).click();
    const modification=page.getByRole('combobox',{name:'Модифікація / двигун',exact:true});
    const count = mods.filter(m => m.year_from <= 2001 && (m.year_to === null || m.year_to >= 2001)).length;
    assert(count > 1);
    await expect(modification.locator('option')).toHaveCount(count+1);
    await expect(modification).toHaveValue(''); // Never auto-pick an ambiguous result.
    await page.getByRole('spinbutton',{name:'Рік',exact:true}).fill('1999');
    await expect(modification.locator('option[value="16063"]')).toHaveCount(0);
    await page.getByRole('spinbutton',{name:'Рік',exact:true}).fill('2001');
    await modification.selectOption('16063');
    await page.getByLabel('Внутрішній ID донора',{exact:false}).fill('OFFLINE-TEST');
    await page.getByLabel('Дата придбання',{exact:false}).fill('2026-01-01');
    await page.getByRole('button',{name:'Зберегти',exact:true}).click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
    assert.equal(saved.ktype,16063);
    assert.equal(saved.manufacturer,'VW');
    assert.equal(saved.model,'GOLF IV (1J1)');
    assert.equal(saved.year,2001);
    assert.equal(requests.filter(p=>p.includes('/plan-parts/')).length,3);
    assert(!requests.some(p=>p.includes('/parts')||p.includes('/categories')));
    await page.getByRole('button',{name:'Додати автомобіль',exact:true}).click();
    await page.getByRole('button',{name:'Додати вручну',exact:true}).click();
    await expect(page.getByLabel('Виробник',{exact:false})).toBeVisible();
    assert.equal(requests.filter(p=>p.includes('/plan-parts/')).length,3);
    assert.deepEqual(errors,[]);
    await context.close();
    console.log(`PASS vehicle selection and manual fallback ${viewport.width}x${viewport.height}`);
  }
} finally {
  await browser?.close();
  server.kill('SIGTERM');
}
