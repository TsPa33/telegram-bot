import type {BodyRule,BodyType,ImageAsset,ResolvedVehicleImage,VehicleImageIdentity,VehicleImageManifest} from './vehicleImageTypes';
import {BODY_TYPES} from './vehicleImageTypes';

export const normalizeVehicleName=(value:unknown)=>String(value??'').normalize('NFKC').trim().toLocaleLowerCase('en').replace(/\s+/g,' ');
const identityKey=(manufacturer:unknown,model:unknown)=>JSON.stringify([normalizeVehicleName(manufacturer),normalizeVehicleName(model)]);
const validYear=(year:unknown):year is number=>typeof year==='number'&&Number.isInteger(year)&&year>=1886&&year<=2100;
const boundedYear=(entry:{yearFrom?:number;yearTo?:number},year:unknown)=>validYear(entry.yearFrom)&&validYear(entry.yearTo)&&entry.yearFrom<=entry.yearTo&&validYear(year)&&year>=entry.yearFrom&&year<=entry.yearTo;
const safeFile=(value:string)=>/^[a-z0-9][a-z0-9._-]*\.(webp|png|svg)$/.test(value)&&!value.includes('..');
const safeURL=(value:unknown):value is string=>typeof value==='string'&&/^\/(?:assets|src\/assets\/vehicles)\/[a-zA-Z0-9_./-]+\.(?:webp|png|svg)$/.test(value)&&!value.includes('..');
const bodyType=(value:unknown):value is BodyType=>BODY_TYPES.includes(value as BodyType);
const rank=(a:ImageAsset,b:ImageAsset)=>(b.priority??0)-(a.priority??0)||a.id.localeCompare(b.id,'en');

/** Compile trusted local metadata once. Never fuzzy-match a model/generation or fetch a provider. */
export function createVehicleImageResolver(manifest:VehicleImageManifest,urls:Readonly<Record<string,string>>){
 const usable=manifest.assets.filter(a=>a.verified===true&&a.usage.status==='approved'&&a.usage.commercialUse===true&&a.usage.license.trim()&&a.source.description.trim()&&a.source.reference.trim()
  &&bodyType(a.bodyType)&&safeFile(a.file)&&safeURL(urls[a.file])&&Number.isInteger(a.width)&&a.width>0&&a.width<=1600&&Number.isInteger(a.height)&&a.height>0&&a.height<=1600
  &&(a.kind==='body'||a.kind==='unknown'||(normalizeVehicleName(a.manufacturer)&&normalizeVehicleName(a.model)&&validYear(a.yearFrom)&&validYear(a.yearTo)&&a.yearFrom<=a.yearTo&&(a.kind!=='generation'||normalizeVehicleName(a.generation)))));
 const byId=new Map<string,ImageAsset>(),models=new Map<string,ImageAsset[]>(),rules=new Map<string,BodyRule[]>();
 // Duplicated IDs are invalid rather than silently picking an unreviewed resource.
 const counts=new Map<string,number>();for(const a of manifest.assets)counts.set(a.id,(counts.get(a.id)||0)+1);
 for(const a of usable){if(counts.get(a.id)!==1)continue;byId.set(a.id,a);if(a.kind==='model'||a.kind==='generation'){const key=identityKey(a.manufacturer,a.model);models.set(key,[...(models.get(key)||[]),a]);}}
 for(const rule of manifest.bodyRules){if(!bodyType(rule.bodyType)||!rule.evidence.trim())continue;const key=identityKey(rule.manufacturer,rule.model);rules.set(key,[...(rules.get(key)||[]),rule]);}
 return function resolve(vehicle:VehicleImageIdentity):ResolvedVehicleImage[]{
  const key=identityKey(vehicle.manufacturer,vehicle.model),generation=normalizeVehicleName(vehicle.generation);
  const compatible=(models.get(key)||[]).filter(a=>boundedYear(a,vehicle.year)&&(!generation||!a.generation||normalizeVehicleName(a.generation)===generation));
  const exact=generation?compatible.filter(a=>a.generation&&normalizeVehicleName(a.generation)===generation).sort(rank):[];
  const generationOptions=new Set(compatible.map(a=>normalizeVehicleName(a.generation)));
  // A year at a generation boundary cannot disambiguate conflicting drawings.
  const yearImages=(!generation&&generationOptions.size>1)?[]:compatible.filter(a=>!exact.includes(a)).sort(rank);
  const matchingRules=(rules.get(key)||[]).filter(r=>(!r.generation||!!generation&&normalizeVehicleName(r.generation)===generation)
   &&(r.yearFrom===undefined&&r.yearTo===undefined||boundedYear(r,vehicle.year)));
  const knownBodies=new Set(matchingRules.map(r=>r.bodyType));
  let body:BodyType=bodyType(vehicle.bodyType)?vehicle.bodyType:knownBodies.size===1?matchingRules[0].bodyType:'unknown';
  // Verified year/model metadata can provide body type only when unambiguous.
  if(body==='unknown'){const inferred=new Set([...exact,...yearImages].map(a=>a.bodyType));if(inferred.size===1)body=[...inferred][0];}
  const result:ResolvedVehicleImage[]=[],seen=new Set<string>();
  function add(asset:ImageAsset|undefined,tier:ResolvedVehicleImage['tier']){
   if(!asset||seen.has(asset.file))return;seen.add(asset.file);
   const variants=(asset.variants||[]).filter(v=>safeFile(v.file)&&safeURL(urls[v.file])&&Number.isInteger(v.width)&&v.width>0&&v.width<=asset.width);
   const srcSet=variants.length?[...variants.map(v=>`${urls[v.file]} ${v.width}w`),`${urls[asset.file]} ${asset.width}w`].join(', '):undefined;
   result.push({asset,src:urls[asset.file],srcSet,tier,bodyType:body});
  }
  exact.slice(0,1).forEach(a=>add(a,'generation'));yearImages.slice(0,1).forEach(a=>add(a,'model-year'));
  const fallback=byId.get(manifest.fallbacks[body]||'');
  if(fallback&&fallback.kind==='body'&&fallback.bodyType===body)add(fallback,'body');
  const universal=byId.get(manifest.fallbacks.unknown||'');
  if(universal&&universal.kind==='unknown'&&universal.bodyType==='unknown')add(universal,'unknown');
  return result;
 };
}
