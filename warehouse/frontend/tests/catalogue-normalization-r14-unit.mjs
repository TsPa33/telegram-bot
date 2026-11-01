import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const read=(name)=>readFile(new URL(name,import.meta.url),'utf8');
const admin=await read('../src/pages/CatalogueImport.tsx');
const review=await read('../src/CatalogueNormalizationReview.tsx');
const labels=await read('../src/catalogueLabels.ts');
const quick=await read('../src/PartsQuickCategories.tsx');
const filters=await read('../src/InventoryFilters.tsx');
const catalog=await read('../src/pages/Catalog.tsx');
test('normalization review appears only inside existing platform-admin gated page',()=>{
 assert.match(admin,/if\(!enabled\)return/);
 assert.match(admin,/tab==='normalization'&&/);
 assert.match(admin,/<CatalogueNormalizationReview key=/);
 // Reject explicit write operations, not ordinary HTML <input> tags.
 assert.doesNotMatch(review,/api\([^\n]*,\s*['"](POST|PATCH|PUT|DELETE)['"]/i);
});
test('duplicate group browsing is paginated and retains individual category IDs',()=>{
 assert.match(review,/duplicate-groups\?offset=/);
 assert.match(review,/risk=\x27\+risk/);
 assert.match(review,/group\.members\.map\(m=>/);
 assert.match(review,/m\.id/);
 assert.match(review,/setPage\(p=>p\+1\)/);
});
test('unapproved Ukrainian terms are never silently displayed as approved categories',()=>{
 assert.doesNotMatch(labels,/catalogue_ua_proposals_v1|catalogue_mapping|approve/i);
 assert.match(labels,/establishedCategoryLabels/);
 assert.match(labels,/dup\?displayed/);
 assert.match(quick,/groupQuickCategoryRoots\(categories\)/);
 assert.match(quick,/group\.members\.map\(c=>/);
 assert.match(quick,/categoryOptionLabel\(c,allRoots\)/);
 assert.match(filters,/categoryOptionLabel\(c,categories\)/);
 assert.match(catalog,/categoryOptionLabel\(c,rows\|\|\[\]\)/);
});
test('review offers data-only CSV export, not any stock modification',()=>{
 assert.match(review,/name-proposals/);
 assert.match(review,/duplicate-review\.csv/);
 assert.match(review,/На перевірці/);
 assert.doesNotMatch(review,/api\([^)]*,\s*['"]POST['"]/);
});
