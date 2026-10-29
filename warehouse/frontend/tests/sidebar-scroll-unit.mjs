import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const source=await readFile(new URL('../src/sidebarScroll.ts',import.meta.url),'utf8');const {revealDelta}=await import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
test('already visible item leaves scroll position unchanged',()=>assert.equal(revealDelta(100,300,120,164),0));
test('reveal item above without scrolling the document',()=>assert.equal(revealDelta(100,300,70,114),-30));
test('reveal item below with minimal movement',()=>assert.equal(revealDelta(100,300,280,324),24));
test('oversized labels align their beginning instead of oscillating',()=>{assert.equal(revealDelta(100,140,120,180),20);assert.equal(revealDelta(100,140,100,160),0);});
test('fractional geometry does not round away clipped text',()=>assert.equal(revealDelta(100.25,300.25,280.5,324.5),24.25));
