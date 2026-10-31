// Prevent additive Alembic migrations from silently disabling live Team / Sales / Search.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readdir,readFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

const frontend=fileURLToPath(new URL('../',import.meta.url));
const buildMigrations=resolve(frontend,'backend/alembic/versions');
// Local checkout has /warehouse/backend; Docker build stages migrations under /build/backend.
const migrations=existsSync(buildMigrations)?buildMigrations:resolve(frontend,'../backend/alembic/versions');
const names=(await readdir(migrations)).filter(n=>n.endsWith('.py')&&!n.startsWith('__'));
const parsed=await Promise.all(names.map(async name=>{
  const body=await readFile(resolve(migrations,name),'utf8');
  const revision=body.match(/^revision\s*(?::[^=\n]+)?=\s*['"]([a-f0-9]{12})['"]/m)?.[1];
  if(!revision)throw Error('Could not identify Alembic revision in '+name);
  const deps=body.match(/^down_revision\s*(?::[^=\n]+)?=\s*(.*)$/m)?.[1]||'';
  return {revision,deps};
}));
const roots=new Set(parsed.map(v=>v.revision));
for(const v of parsed)for(const m of v.deps.matchAll(/['"]([a-f0-9]{12})['"]/g))roots.delete(m[1]);
const heads=[...roots];
test('exactly one packaged Warehouse Alembic head',()=>assert.equal(heads.length,1));
const head=heads[0];
const checks=[
  ['WorkshopDialogs.tsx',/allowedHeads=\[([^\]]+)\]/],
  ['teamReadiness.ts',/&&\s*\[TEAM_REVISION,([^\]]+)\]\.includes/],
  ['smartSearch.ts',/&&\s*\[SMART_REVISION,([^\]]+)\]\.includes/],
];
for(const [file,regex] of checks){
 test('frontend readiness includes current packaged DB head: '+file,async()=>{
  const source=await readFile(resolve(frontend,'src',file),'utf8');
  const match=source.match(regex);
  assert(match,'readiness whitelist not found in '+file);
  assert(match[1].includes("'"+head+"'"),file+' rejects deployed Alembic head '+head);
 });
}
