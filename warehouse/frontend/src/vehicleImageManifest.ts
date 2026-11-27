/// <reference types="vite/client" />
import type {VehicleImageManifest} from './vehicleImageTypes';
import {modelReferenceAssets} from './vehicleModelReferenceAssets';
import {vehicleBodyAssets} from './vehicleBodyAssets';
import {BODY_TYPES} from './vehicleImageTypes';

// Import URL metadata, not image bytes. Vite emits content-hashed /assets/ files;
// <img loading="lazy"> decides when to fetch them. No hotlinks or runtime API.
const files=import.meta.glob('./assets/vehicles/*.{webp,png,svg}',{eager:true,query:'?url',import:'default'}) as Record<string,string>;
export const vehicleImageURLs=Object.fromEntries(Object.entries(files).map(([path,url])=>[path.split('/').pop()!,url]));
const source={type:'generated' as const,description:'Original generic vehicle cutout generated with OpenAI image generation on 2026-10-24; no reference brand/model image supplied.',reference:'src/assets/vehicles/PROVENANCE.md'};
const usage={status:'approved' as const,license:'OpenAI-generated output: use subject to applicable OpenAI terms; no third-party source image imported. Not a model identification or exclusivity claim.',commercialUse:true};
export const vehicleImageManifest:VehicleImageManifest={
 version:'carpot.vehicle-images.v1',
 assets:[
  ...modelReferenceAssets,
  {id:'generic-suv-v1',kind:'body',bodyType:'suv',file:'generic-suv.webp',width:960,height:386,variants:[{file:'generic-suv-480.webp',width:480}],verified:true,source,usage},
  {id:'generic-unknown-v1',kind:'unknown',bodyType:'unknown',file:'generic-unknown.webp',width:960,height:431,variants:[{file:'generic-unknown-480.webp',width:480}],verified:true,source,usage},
 ],
 // Body-only fallback classification, not trim/generation/compatibility inference.
 bodyRules:[
  {manufacturer:'Volvo',model:'XC60',bodyType:'suv',evidence:'Unambiguous generic SUV/crossover body classification; no generation claim.'},
  {manufacturer:'Volvo',model:'XC90',bodyType:'suv',evidence:'Unambiguous generic SUV/crossover body classification; no generation claim.'},
  {manufacturer:'BMW',model:'X3',bodyType:'suv',evidence:'Unambiguous generic SUV/crossover body classification; no generation claim.'},
 ],
 // Supported schema != supplied artwork. Missing body art uses quality unknown.
 fallbacks:{sedan:null,hatchback:null,wagon:null,suv:'generic-suv-v1',coupe:null,convertible:null,minivan:null,pickup:null,van:null,tractor:null,truck:null,bus:null,unknown:'generic-unknown-v1'},
};

 // Enable only when every unique type is present and all files are bundled.
 // Partial import must never alter the deployed card artwork.
 const required=BODY_TYPES.filter(t=>t!=='unknown');
 export const bodyLibraryReady=vehicleBodyAssets.length===required.length&&
  new Set(vehicleBodyAssets.map(a=>a.id)).size===required.length&&
  new Set(vehicleBodyAssets.map(a=>a.file)).size===required.length&&
  required.every(type=>vehicleBodyAssets.filter(a=>a.kind==='body'&&a.bodyType===type&&a.transparentCutout===true&&a.verified===true&&a.usage.status==='approved'&&a.usage.commercialUse===true&&!!vehicleImageURLs[a.file]).length===1);
 export const bodyOnlyManifest:VehicleImageManifest={
  version:'carpot.vehicle-body-library.v2',
  assets:vehicleBodyAssets,
  bodyRules:[],
  fallbacks:Object.fromEntries(BODY_TYPES.map(type=>[type,type==='unknown'?null:vehicleBodyAssets.find(a=>a.bodyType===type)?.id||null])) as VehicleImageManifest['fallbacks'],
 };
