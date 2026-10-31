import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const settings=await readFile(new URL('../src/pages/Settings.tsx',import.meta.url),'utf8');
const app=await readFile(new URL('../src/App.tsx',import.meta.url),'utf8');

test('personal Settings never displays catalogue imports or platform admin links',()=>{
 assert.doesNotMatch(settings,/DismantlingCatalogImport|VehicleDirectoryImport|\/administration\/catalogue\/import|\/catalog-import|Імпорт каталогу|Керувати каталогом/);
 assert.doesNotMatch(settings,/catalog\.import|catalogue_platform_admin/);
});
test('Settings are routed to every authenticated employee independently of role permissions',()=>{
 assert.match(app,/path==='\/settings'\?'':/);
 assert.match(app,/path="\/settings" element=\{<Settings user=\{user\} \/>}/);
 assert.match(app,/user\.catalogue_platform_admin===true&&<NavLink to="\/administration\/catalogue\/import"/);
});
test('all user shortcuts are derived from real effective user permissions',()=>{
 assert.match(settings,/shortcuts\.filter\(item=>can\(item\.permission\)\)/);
 assert.match(settings,/sections\.map\(item=><Link key=\{item\.path\} to=\{item\.path\}/);
 assert.doesNotMatch(settings,/settings\.manage|require_director/);
});
test('password change is an authenticated API mutation with confirmation and forced relogin',()=>{
 assert.match(settings,/api\('\/auth\/password','POST',\{current_password:current,password:next\}\)/);
 assert.match(settings,/next===confirm&&next!==current/);
 assert.match(settings,/window\.dispatchEvent\(new Event\('warehouse:logout'\)\)/);
 assert.match(settings,/api\('\/auth\/logout','POST'\)/);
});
