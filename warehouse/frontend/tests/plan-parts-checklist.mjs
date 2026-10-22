// Production assets, mocked backend only; no provider/database connections.
import { chromium, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
const origin='http://127.0.0.1:18765';
const server=spawn(process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','18765','--strictPort'],{stdio:'pipe'});
let browser;
try {
  for(let i=0;i<50;i++){try{if((await fetch(origin)).ok)break;}catch{}if(i===49)throw Error('Preview timeout');await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
    const context=await browser.newContext({viewport}),page=await context.newPage();
    const vehicle={id:'donor',manufacturer:'Volvo',model:'XC90',year:2005,donor_id:'TEST',ktype:9743,status:'dismantling',archived:false};
    let posts=0,patches=0,items=[];const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/api/v1/**',async route=>{
      const req=route.request(),p=new URL(req.url()).pathname,reply=data=>route.fulfill({json:data});
      if(p.endsWith('/auth/me'))return reply({id:'account',name:'Тест',email:'test@example.test'});
      if(p.endsWith('/vehicle-catalog'))return reply({complete:false,brands:[]});
      if(p.endsWith('/vehicles'))return reply({items:[vehicle],total:1});
      if(p.endsWith('/analytics'))return reply({positions:0,stock_units:0});
      if(p.endsWith('/plan-parts-checklist')&&req.method()==='GET')return reply({items,total:items.length,historical_total:0,ktype:9743,synced:!!items.length});
      if(p.endsWith('/plan-parts-checklist')&&req.method()==='POST'){
        posts++;if(!items.length)items=[{id:'one',name_en:'Oil filter',name_uk:'',status:'unchecked',notes:'',ktype:9743,pt_id:1,article_count:12}];
        return reply({created:posts===1?1:0,updated:0,provider_requested:true});
      }
      if(p.endsWith('/plan-parts-checklist/one')&&req.method()==='PATCH'){patches++;Object.assign(items[0],req.postDataJSON());return reply(items[0]);}
      throw Error('Unexpected request '+p);
    });
    await page.goto(origin+'/vehicles');
    await page.getByRole('button',{name:'Volvo XC90',exact:true}).filter({visible:true}).click();
    await expect(page.getByText('Пунктів: 0. Попередніх: 0.')).toBeVisible();assert.equal(posts,0);
    await page.getByRole('button',{name:'Завантажити чекліст за K-Type',exact:true}).click();
    await expect(page.getByText('Oil filter',{exact:true})).toBeVisible();assert.equal(posts,1);
    await page.getByRole('button',{name:'Перевірити / перекласти',exact:true}).click();
    await page.getByLabel('Українська назва',{exact:true}).fill('Масляний фільтр');
    await page.getByRole('combobox',{name:/Результат перевірки/}).selectOption('present');
    await page.getByRole('button',{name:'Зберегти',exact:true}).click();
    await expect(page.getByText('Масляний фільтр',{exact:true})).toBeVisible();assert.equal(patches,1);assert.equal(posts,1);
    page.on('dialog',d=>d.accept());
    await page.getByRole('button',{name:'Оновити з Plan.Parts',exact:true}).click();
    await expect(page.getByText('Додано: 0. Оновлено: 0. Отримано з Plan.Parts.',{exact:true})).toBeVisible();
    await expect(page.getByText('Масляний фільтр',{exact:true})).toBeVisible();assert.equal(posts,2);assert.deepEqual(errors,[]);
    await context.close();
  }
  console.log('Checklist desktop + iPhone viewport: passed (offline).');
}finally{await browser?.close();server.kill('SIGTERM');}
