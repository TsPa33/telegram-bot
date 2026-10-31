import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const file=new URL('../src/SearchSelect.tsx',import.meta.url);
const source=await readFile(file,'utf8');

test('vehicle brand dropdown is not truncated at first 60 options',()=>{
 assert.match(source,/const filtered = options\.filter\(/);
 assert.doesNotMatch(source,/\.slice\(0,\s*60\)/);
 assert.doesNotMatch(source,/filtered\s*=.+?\.slice\(/s);
});
test('large dropdown tells user how many options exist',()=>{
 assert.match(source,/filtered\.length\s*>\s*60/);
 assert.match(source,/Усього \{filtered\.length\} варіантів/);
});
test('keyboard focus scrolls to selected entry',()=>{
 assert.match(source,/scrollIntoView\(\{block:'nearest'\}\)/);
});
