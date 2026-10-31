import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../src/',import.meta.url));
const read=(p)=>readFile(new URL(p,'file://'+root+'/'),'utf8');

test('vehicle import is not exposed on customer donor listing',async()=>{
 const vehicles=await read('pages/Vehicles.tsx');
 assert.doesNotMatch(vehicles, /<VehicleDirectoryImport/);
 assert.doesNotMatch(vehicles, /import VehicleDirectoryImport from/);
});
test('vehicle directory import is platform-admin catalogue tab',async()=>{
 const admin=await read('pages/CatalogueImport.tsx');
 const app=await read('App.tsx');
 assert.match(admin,/id:'vehicles',label:'Довідник автомобілів'/);
 assert.match(admin,/tab==='vehicles'&&<section/);
 assert.match(admin,/<VehicleDirectoryImport\s*\/>/);
 assert.match(app,/CatalogueImport enabled=\{user\.catalogue_platform_admin===true\}/);
});
test('server uses platform allowlist admin authorization on actual upload',async()=>{
 const rootApi=fileURLToPath(new URL('../../backend/app/api/routes.py',import.meta.url));
 const api=await readFile(rootApi,'utf8');
 const idx=api.indexOf('async def directory_import(');
 assert.ok(idx>=0);
 const section=api.slice(idx,idx+420);
 assert.match(section,/require_admin\(db,who\)/);
 assert.doesNotMatch(section,/require_director\(who\)/);
});
