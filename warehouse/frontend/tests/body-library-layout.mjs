import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
await mkdir('test-results',{recursive:true});
const browser=await chromium.launch({args:['--no-sandbox']});
const types=['sedan','hatchback','wagon','suv','coupe','convertible','minivan','pickup','van','tractor','truck','bus','suv','suv','suv','tractor','truck'];
try{
 for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5173'))external.push(r.url());});
  await page.goto('http://127.0.0.1:5173/tests/body-library-layout.html');
  const cards=page.locator('.corporate-donor-card');await expect(cards).toHaveCount(18);
  for(const theme of ['light','onyx','gold','forest']){
   await page.evaluate(t=>{document.documentElement.dataset.theme=t==='light'?'light':'dark';document.documentElement.dataset.nightStyle=t;},theme);
   for(let i=0;i<types.length;i++){
    const card=cards.nth(i),image=card.locator('.vehicle-image');await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveAttribute('data-body-type',types[i]);await expect(image).toHaveAttribute('data-match','body');await expect(image).toHaveAttribute('data-image-state','loaded');
    assert(await image.locator('img').evaluate(el=>el.naturalWidth===960&&el.naturalHeight===640&&getComputedStyle(el).filter==='none'&&getComputedStyle(el).opacity==='1'&&getComputedStyle(el).objectFit==='contain'));
    assert(await card.evaluate(el=>el.scrollWidth<=el.clientWidth+1&&getComputedStyle(el).backgroundImage.includes('radial-gradient')));
    await expect(card.locator('.vehicle-image-attribution')).toHaveCount(0);
   }
   await expect(cards.last().locator('.vehicle-image')).toHaveAttribute('data-image-state','unavailable');
   await expect(cards.last().locator('.vehicle-image img')).toHaveCount(0);
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.evaluate(()=>scrollTo(0,0));
   await page.screenshot({path:'test-results/body-library-'+theme+'-'+width+'.png',fullPage:true,animations:'disabled'});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  await page.close();console.log('PASS all 12 bodies, 5 staging regression cases and unknown, four themes, viewport '+width);
 }
}finally{await browser.close();}
