import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
if(process.env.WAREHOUSE_E2E!=='1')throw Error('Local disposable database required');
const origin='http://127.0.0.1:5173';
const browser=await chromium.launch({executablePath:process.env.WAREHOUSE_CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport,hasTouch:viewport.width<800}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const auth=await context.request.post(origin+'/api/v1/auth/register',{data:{name:'Design owner',email:`design-${Date.now()}@example.test`,password:'local-design-test-password'}});assert(auth.ok(),`Registration ${auth.status()}: ${await auth.text()}`);const headers={'X-CSRF-Token':(await auth.json()).csrf_token};
 async function post(path,data){const r=await context.request.post(origin+'/api/v1'+path,{headers,data});assert(r.ok(),await r.text());return r.json();}
 const vehicle=await post('/vehicles',{manufacturer:'Volvo',model:'XC90',year:2010,engine:'2.4 D5',transmission:'Автоматична'});
 await post('/categories/import',{source:'design-local',nodes:[{key:'body',name:'Кузов',kind:'category'},{key:'panels',parent_key:'body',name:'Панелі кузова',kind:'subcategory'}]});const categories=(await(await context.request.get(origin+'/api/v1/categories')).json()).items;
 const part=await post('/parts',{name:'Капот Volvo XC90',vehicle_id:vehicle.id,category_id:categories.find(c=>c.external_key==='body').id,subcategory_id:categories.find(c=>c.external_key==='panels').id,selling_price:'123.45',currency:'USD',location:'Полиця 1'});await post(`/parts/${part.id}/operations`,{type:'receipt',quantity:3,reason:'Local design verification'});
 const buyer=await post('/buyers',{name:'Тестовий покупець',phone:'0501234567'}),order=await post('/orders',{buyer_id:buyer.id,request_key:crypto.randomUUID(),lines:[{part_id:part.id,quantity:1,unit_price:'123.45',currency:'USD'}]});
 async function check(screen){
  if(!screen.startsWith('auth-'))await expect(page.locator('.main')).toBeVisible();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),screen+' horizontal overflow');
  const failures=await page.evaluate(()=>{
   const rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number),blend=(a,b)=>a.slice(0,3).map((c,i)=>c*(a[3]??1)+b[i]*(1-(a[3]??1)));
   const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
   function background(el){const chain=[];for(let p=el;p;p=p.parentElement)chain.unshift(p);return chain.reduce((bg,p)=>blend(rgb(getComputedStyle(p).backgroundColor),bg),[255,255,255]);}
   const failures=[];
   for(const el of document.querySelectorAll('p,small,span,strong,b,label,button,a,h1,h2,h3,dt,dd,th,td,summary,time,code')){
    const text=[...el.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent.trim()).join('');
    const r=el.getBoundingClientRect(),s=getComputedStyle(el);
    if(!text||r.width<=0||r.height<=0||s.visibility==='hidden'||el.closest(':disabled,[aria-disabled=true]')||!el.checkVisibility())continue;
    const bg=background(el),fg=blend(rgb(s.color),bg),a=luminance(fg),b=luminance(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05),size=parseFloat(s.fontSize),min=size>=24||(size>=18.66&&parseInt(s.fontWeight)>=700)?3:4.5;
    if(ratio+.02<min)failures.push({text:text.slice(0,55),ratio:+ratio.toFixed(2),min,color:s.color,background:bg});
   }return failures;
  });
  assert.deepEqual(failures,[],screen+' text contrast');await page.screenshot({path:`test-results/design-${screen}-${viewport.width}.png`,fullPage:true,animations:'disabled'});
 }
 for(const [path,name] of [['/','search'],['/vehicles','vehicles'],['/inventory','stock'],['/inventory/advanced','advanced-stock'],['/orders','orders'],['/orders/'+order.id,'order-detail'],['/analytics','audit'],['/operations','operations'],['/statistics','statistics'],['/settings','settings'],['/catalog','catalog'],['/archive','archive']]){
  await page.goto(origin+path);await expect(page.locator('.main')).toBeVisible();await expect(page.locator('.loading')).toHaveCount(0);await check(name);
 }
 await page.goto(origin+'/vehicles');const card=page.locator('.vehicle-summary-card');await expect(card).toContainText('2.4 D5');await expect(card).toContainText('Автоматична');const open=card.getByRole('button',{name:'Запчастини Volvo XC90',exact:true});
 assert(await open.evaluate(el=>{const rgb=getComputedStyle(el).backgroundColor.match(/\d+/g).map(Number);return rgb.slice(0,3).every(v=>v>=200);}),'Vehicle navigation remains light');await open.hover();await expect(open).toHaveCSS('background-color','rgb(232, 242, 239)');await page.mouse.move(0,0);await open.focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');assert.equal(await open.evaluate(el=>getComputedStyle(el).outlineStyle),'solid');assert.equal(await open.evaluate(el=>getComputedStyle(el).outlineWidth),'2px');
 await open.click();await expect(page.locator('dialog[open]')).toBeVisible();await check('vehicle-dialog');const cat=page.locator('.simple-category').first();await expect(cat).not.toHaveAttribute('open','');await cat.locator(':scope>summary').click();const sub=cat.locator('.simple-subcategory').first();await expect(sub).not.toHaveAttribute('open','');await sub.locator(':scope>summary').click();await expect(sub.locator('.simple-part').first()).toBeVisible();await check('catalog-tree');await page.getByRole('button',{name:'Закрити',exact:true}).click();
 await page.goto(origin+'/inventory');await page.getByRole('button',{name:'За автомобілями',exact:true}).click();await expect(page.locator('.donor-stock-card')).toContainText('2.4 D5');await expect(page.locator('.donor-stock-card')).toContainText('Автоматична');await check('donor-cards');await page.getByRole('button',{name:/Відкрити склад Volvo XC90/}).click();const tree=page.locator('.donor-stock-tree'),category=tree.locator(':scope>details');await category.locator(':scope>summary').click();const stockSub=category.locator('.donor-stock-subcategory');await expect(stockSub).not.toHaveAttribute('open','');await stockSub.locator(':scope>summary').click();await check('stock-tree');await tree.getByRole('button',{name:part.name,exact:true}).click();await check('part-dialog');
 await page.getByRole('dialog',{name:part.name,exact:true}).getByRole('button',{name:'Оформити замовлення',exact:true}).click();await expect(page.getByRole('dialog',{name:'Оформити замовлення',exact:true})).toBeVisible();await expect(page.locator('dialog[open]').last().locator('.loading')).toHaveCount(0);await check('order-form');const disabled=page.getByRole('dialog',{name:'Оформити замовлення',exact:true}).getByRole('button',{name:'Зберегти замовлення',exact:true});await expect(disabled).toBeDisabled();assert.equal(await disabled.evaluate(el=>getComputedStyle(el).cursor),'not-allowed');
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await disabled.evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
 await page.getByRole('dialog',{name:'Оформити замовлення',exact:true}).getByRole('button',{name:'Закрити',exact:true}).click();await page.getByRole('dialog',{name:part.name,exact:true}).getByRole('button',{name:'Закрити',exact:true}).click();await page.goto(origin+'/orders/'+order.id);await page.getByRole('button',{name:'Скасувати замовлення',exact:true}).click();const destructive=page.getByRole('dialog',{name:'Скасувати замовлення?',exact:true}).getByRole('button',{name:'Підтвердити',exact:true});await expect(destructive).toHaveClass(/destructive/);await check('destructive-dialog');
 await page.getByRole('dialog',{name:'Скасувати замовлення?',exact:true}).getByRole('button',{name:'Скасувати',exact:true}).click();await context.request.post(origin+'/api/v1/auth/logout',{headers});await page.goto(origin+'/');await expect(page.locator('.auth-card')).toBeVisible();await check('auth-login');await page.getByRole('button',{name:'Зареєструватися',exact:true}).click();await check('auth-register');assert.deepEqual(errors,[]);await context.close();console.log(`PASS design tokens, all screens, contrast, controls, focus, nested tree, dialogs, reduced motion ${viewport.width}x${viewport.height}`);
}}finally{await browser.close();}
