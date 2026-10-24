/// <reference types="vite/client" />
import type {VehicleImageManifest} from './vehicleImageTypes';

// Import URL metadata, not image bytes. Vite emits content-hashed /assets/ files;
// <img loading="lazy"> decides when to fetch them. No hotlinks or runtime API.
const files=import.meta.glob('./assets/vehicles/*.{webp,png,svg}',{eager:true,query:'?url',import:'default'}) as Record<string,string>;
export const vehicleImageURLs=Object.fromEntries(Object.entries(files).map(([path,url])=>[path.split('/').pop()!,url]));
const source={type:'generated' as const,description:'Original generic vehicle cutout generated with OpenAI image generation on 2026-10-24; no reference brand/model image supplied.',reference:'src/assets/vehicles/PROVENANCE.md'};
const usage={status:'approved' as const,license:'OpenAI-generated output: use subject to applicable OpenAI terms; no third-party source image imported. Not a model identification or exclusivity claim.',commercialUse:true};
export const vehicleImageManifest:VehicleImageManifest={
 version:'carpot.vehicle-images.v1',
 assets:[
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
 fallbacks:{sedan:null,hatchback:null,wagon:null,suv:'generic-suv-v1',coupe:null,convertible:null,minivan:null,pickup:null,van:null,unknown:'generic-unknown-v1'},
};
