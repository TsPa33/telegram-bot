import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
const css=await readFile(new URL('../src/tokens.css',import.meta.url),'utf8'),values=Object.fromEntries([...css.matchAll(/(--[\w-]+):\s*(#[\da-f]{6});/gi)].map(m=>[m[1],m[2]]));
function luminance(hex){return hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((n,x,i)=>n+x*[.2126,.7152,.0722][i],0);}
function contrast(a,b){const x=luminance(values[a]),y=luminance(values[b]);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
for(const [fg,bg] of [['--color-text','--color-surface'],['--color-secondary','--color-surface'],['--color-surface','--color-accent-strong'],['--color-success','--color-success-surface'],['--color-sidebar-text','--color-sidebar'],['--color-sidebar-secondary','--color-sidebar']])test(`readable shared role ${fg}/${bg}`,()=>assert(contrast(fg,bg)>=4.5,contrast(fg,bg)));
test('success remains distinct from primary navigation/actions',()=>assert.notEqual(values['--color-success'],values['--color-accent-strong']));
test('UX-1 consumes shared palette without a private color theme',async()=>{const geometry=await readFile(new URL('../src/warehouse-ux1.css',import.meta.url),'utf8');assert(!/--color-[\w-]+\s*:/.test(geometry));assert(!/:has\(\.ux1-workspace\)\s+\.sidebar/.test(geometry));});
