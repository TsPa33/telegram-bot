import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
import {createHash} from 'node:crypto';
// Pure resolver tests: no browser, API, database or provider requests.
const encode=s=>'data:text/javascript;base64,'+Buffer.from(s).toString('base64');
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const types=encode(compile(await readFile(new URL('../src/vehicleImageTypes.ts',import.meta.url),'utf8')));
const code=compile(await readFile(new URL('../src/vehicleImageResolver.ts',import.meta.url),'utf8')).replaceAll("'./vehicleImageTypes'",JSON.stringify(types));
const {createVehicleImageResolver,normalizeVehicleName}=await import(encode(code));
const source={type:'owned',description:'Synthetic test metadata only',reference:'local-fixture'},usage={status:'approved',commercialUse:true,license:'Test fixture'};
const body=(id,type='unknown')=>({id,kind:type==='unknown'?'unknown':'body',file:id+'.webp',width:960,height:400,bodyType:type,verified:true,source,usage});
const model=(id,generation,from,to)=>({...body(id,'suv'),kind:generation?'generation':'model',manufacturer:'Example Motors',model:'Sample',generation,yearFrom:from,yearTo:to});
const fallback={sedan:null,hatchback:null,wagon:null,suv:'suv',coupe:null,convertible:null,minivan:null,pickup:null,van:null,unknown:'unknown'};
const base=[body('suv','suv'),body('unknown')],input={manufacturer:'Example Motors',model:'Sample',year:2018};
const resolver=(assets=[],rules=[],fallbacks=fallback,extraURLs={})=>createVehicleImageResolver({version:'test',assets:[...base,...assets],bodyRules:rules,fallbacks},{...Object.fromEntries([...base,...assets].map(a=>[a.file,'/assets/'+a.file])),...extraURLs});
const ids=rows=>rows.map(r=>r.asset.id);

test('normalizes Unicode, case and whitespace, never fuzzy-matches generation',()=>{assert.equal(normalizeVehicleName(' ＢＭＷ  X3 '),'bmw x3');const resolve=resolver([model('ii','II',2018,2024)]);assert.equal(resolve({...input,generation:' ii '})[0].tier,'generation');assert.equal(resolve({...input,generation:'2'})[0].tier,'unknown');assert.equal(resolve({...input,model:'Sample Sport',generation:'II'})[0].tier,'unknown');});
test('exact generation is first, body and universal remain safe error fallbacks',()=>{const r=resolver([model('i','I',2009,2017),model('ii','II',2018,2024)])({...input,generation:'II'});assert.deepEqual(ids(r),['ii','suv','unknown']);assert.equal(r[0].tier,'generation');});
test('different generations and production years cannot get a wrong exact asset',()=>{const resolve=resolver([model('i','I',2009,2017),model('ii','II',2018,2024)]);assert.equal(resolve({...input,year:2016,generation:'I'})[0].asset.id,'i');assert.equal(resolve({...input,year:2018,generation:'I'})[0].asset.id,'unknown');assert.equal(resolve({...input,year:2016,generation:'II'})[0].asset.id,'unknown');});
test('missing generation uses only verified year coverage, without inferring a stored generation',()=>{const original={...input};const result=resolver([model('ii','II',2018,2024)])(original);assert.equal(result[0].asset.id,'ii');assert.equal(result[0].tier,'model-year');assert.deepEqual(original,input);});
test('model image needs known valid year and bounded coverage',()=>{const resolve=resolver([model('m',undefined,2016,2019)]);for(const year of [undefined,null,'2018',NaN,2015,2020,Infinity])assert.equal(resolve({...input,year})[0].tier,'unknown');assert.equal(resolve(input)[0].tier,'model-year');});
test('ambiguous generation boundary falls back rather than guessing',()=>{const r=resolver([model('i','I',2009,2018),model('ii','II',2018,2024)])(input);assert.equal(r[0].tier,'unknown');});
test('unrelated brands/models never match',()=>{const resolve=resolver([model('ii','II',2018,2024)]);assert.equal(resolve({...input,manufacturer:'Other Motors',generation:'II'})[0].tier,'unknown');});
test('all ten body types work via registry without React conditions',()=>{for(const type of Object.keys(fallback)){if(type==='unknown')continue;const asset=body('body-'+type,type);const resolve=resolver([asset],[],{...fallback,[type]:asset.id});assert.equal(resolve({...input,bodyType:type})[0].asset.id,asset.id);assert.equal(resolve({...input,bodyType:type})[0].tier,'body');}});
test('missing body artwork and unknown body use the universal resource',()=>{const resolve=resolver();for(const type of ['sedan','hatchback','wagon','coupe','convertible','minivan','pickup','van','unknown',undefined,'spaceship'])assert.deepEqual(ids(resolve({...input,bodyType:type})),['unknown']);});
test('body rules are explicit, bounded and never use substring model names',()=>{const rule={manufacturer:'Example Motors',model:'Sample',generation:'II',yearFrom:2018,yearTo:2024,bodyType:'suv',evidence:'Local reviewed classification'};const resolve=resolver([], [rule]);assert.equal(resolve({...input,generation:'II'})[0].asset.id,'suv');assert.equal(resolve({...input,generation:'I'})[0].asset.id,'unknown');assert.equal(resolve({...input})[0].asset.id,'unknown');assert.equal(resolve({...input,generation:'II',year:2016})[0].asset.id,'unknown');});
test('conflicting body rules do not guess',()=>{const a={manufacturer:'Example Motors',model:'Sample',bodyType:'suv',evidence:'test'},b={...a,bodyType:'sedan'};assert.equal(resolver([], [a,b])(input)[0].asset.id,'unknown');});
test('unapproved, unlicensed and unverified model images are excluded',()=>{for(const changes of [{verified:false},{usage:{...usage,status:'pending'}},{usage:{...usage,commercialUse:false}},{usage:{...usage,license:''}},{source:{...source,reference:''}}])assert.equal(resolver([{...model('ii','II',2018,2024),...changes}])({...input,generation:'II'})[0].tier,'unknown');});
test('missing local resources and malformed paths never generate an img URL',()=>{for(const file of ['../secret.webp','https://example.test/car.webp','data:image/png;base64,x','car.webp?token=secret','car%2ewebp','car..webp'])assert.equal(resolver([{...model('ii','II',2018,2024),file}])({...input,generation:'II'})[0].tier,'unknown');const assets=[...base,model('ii','II',2018,2024)];const resolve=createVehicleImageResolver({version:'test',assets,bodyRules:[],fallbacks:fallback},{'unknown.webp':'/assets/unknown.webp','suv.webp':'/assets/suv.webp'});assert.equal(resolve({...input,generation:'II'})[0].tier,'unknown');});
test('external URLs and data URLs are never used even with a safe file key',()=>{for(const url of ['https://example.test/car.webp','//example.test/car.webp','data:image/webp;base64,test','/assets/../private.webp'])assert.equal(resolver([model('ii','II',2018,2024)],[],fallback,{'ii.webp':url})({...input,generation:'II'})[0].tier,'unknown');});
test('duplicate ids are rejected and broken duplicate file candidates are not retried',()=>{assert.equal(resolver([model('ii','II',2018,2024),model('ii','II',2018,2024)])({...input,generation:'II'})[0].tier,'unknown');const a=model('ii','II',2018,2024),b={...a,id:'other'};assert.equal(resolver([a,b])({...input,generation:'II'}).filter(r=>r.src==='/assets/ii.webp').length,1);});
test('srcset contains local reviewed variants only',()=>{const a={...model('ii','II',2018,2024),variants:[{file:'small.webp',width:480},{file:'../private.webp',width:480}]};const r=resolver([a],[],fallback,{'small.webp':'/assets/small.webp'})({...input,generation:'II'})[0];assert.equal(r.srcSet,'/assets/small.webp 480w, /assets/ii.webp 960w');});
test('empty registry returns an empty chain for a bounded terminal placeholder',()=>{assert.deepEqual(createVehicleImageResolver({version:'empty',assets:[],bodyRules:[],fallbacks:{...fallback,unknown:null}},{})(input),[]);});

test('large registries cannot create an unbounded error request chain',()=>{const assets=Array.from({length:1000},(_,i)=>model('gen-'+i,'II',2018,2024));const result=resolver(assets)({...input,generation:'II'});assert(result.length<=4);assert.equal(result.filter(r=>r.tier==='generation').length,1);});

test('shipped WebP resources match provenance hashes/dimensions, alpha and size limits',async()=>{
 const metadata=JSON.parse(await readFile(new URL('../src/assets/vehicles/metadata.json',import.meta.url),'utf8'));
 let count=0;for(const variants of Object.values(metadata))for(const asset of variants){
  const bytes=await readFile(new URL('../src/assets/vehicles/'+asset.file,import.meta.url));count++;
  assert.equal(createHash('sha256').update(bytes).digest('hex'),asset.sha256);assert.equal(bytes.length,asset.bytes);assert(bytes.length<=100000);
  assert.equal(bytes.toString('ascii',8,12),'WEBP');assert.equal(bytes.toString('ascii',12,16),'VP8X');assert(bytes[20]&16,'Alpha channel required');
  assert.equal(bytes.readUIntLE(24,3)+1,asset.width);assert.equal(bytes.readUIntLE(27,3)+1,asset.height);
 }assert.equal(count,4);
});
