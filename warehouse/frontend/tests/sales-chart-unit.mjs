import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../src/salesChart.ts',import.meta.url),'utf8');
const {calendarToday,recentPeriod,validPeriod,periodLabel}=await import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
test('calendar uses selected timezone rather than browser timezone',()=>{assert.equal(calendarToday(new Date('2026-06-15T22:30:00Z')),'2026-06-16');assert.equal(calendarToday(new Date('2026-06-15T22:30:00Z'),'UTC'),'2026-06-15');});
test('presets use calendar arithmetic across DST and leap day',()=>{
 assert.deepEqual(recentPeriod(7,'2026-03-30'),{from:'2026-03-24',to:'2026-03-30'});
 assert.deepEqual(recentPeriod(2,'2024-03-01'),{from:'2024-02-29',to:'2024-03-01'});
});
test('bounded inclusive 366 days',()=>{
 assert(validPeriod('2024-01-01','2024-12-31'));
 for(const [a,b] of [['2024-01-01','2025-01-01'],['2026-02-02','2026-02-01'],['',''],['2026-02-30','2026-03-05'],['0001-01-01','0001-01-02'],['9999-01-01','9999-01-01']])assert.equal(validPeriod(a,b),false);
});
test('date labels explicitly use UTC calendar date',()=>{
 assert.match(periodLabel('2026-03-29','day'),/29/);
 assert.match(periodLabel('2026-03-23','week'),/тиждень/);
 assert.match(periodLabel('2026-03-01','month'),/березень.*2026/);
});
