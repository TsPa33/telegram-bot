import {chromium,expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
await mkdir('test-results',{recursive:true});
const browser=await chromium.launch({args:['--no-sandbox']});
try{
 for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:5173/tests/photo-card-layout.html');
  const cards=page.locator('.corporate-donor-card');await expect(cards).toHaveCount(5);
  for(const card of (await cards.all()).slice(0,4)){
   const image=card.locator('.vehicle-image');await image.scrollIntoViewIfNeeded();await expect(image).toHaveAttribute('data-image-state','loaded');
   const b=await image.boundingBox();assert(b.height>= (width===390?89:110));
   const img=image.locator('img');assert(await img.evaluate(el=>el.naturalWidth>0&&getComputedStyle(el).filter==='none'&&getComputedStyle(el).opacity==='1'&&getComputedStyle(el).objectFit==='contain'));
   const info=card.locator('.vehicle-image-attribution');await expect(info).not.toHaveAttribute('open','');
   await expect(info.locator('.vehicle-image-credit')).not.toBeVisible();
   await info.locator('summary').click();await expect(info.locator('.vehicle-image-credit')).toBeVisible();
   assert(await info.locator('.vehicle-image-credit').evaluate(el=>getComputedStyle(el).position==='static'&&getComputedStyle(el).overflow==='visible'&&el.scrollWidth<=el.clientWidth+1));
   assert.equal(await info.locator('a').count(),2);await info.locator('summary').click();
  }
  await expect(cards.last().locator('.vehicle-image')).toHaveAttribute('data-image-state','unavailable');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'test-results/photo-cards-'+width+'.png',fullPage:true,animations:'disabled'});
  await page.close();console.log('PASS photo card layout '+width);
 }
}finally{await browser.close();}
