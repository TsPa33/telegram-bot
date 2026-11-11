import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
test('free generation is outside collapsed modification controls',()=>{const s=readFileSync(new URL('../src/GlobalCatalogueFlow.tsx',import.meta.url),'utf8');assert.ok(s.indexOf('<UniversalPlanGenerator vehicle=')<s.indexOf('<details className="uf-catalogue-disclosure">'));});
