import {useState} from 'react';
import {CarFront} from 'lucide-react';
import {resolvePlaceholderBody} from './vehicleBodyClassification';
import type {Row} from './api';
import {createVehicleImageResolver,normalizeVehicleName} from './vehicleImageResolver';
import {vehicleImageManifest,vehicleImageURLs,bodyOnlyManifest,bodyLibraryReady} from './vehicleImageManifest';
import type {ResolvedVehicleImage} from './vehicleImageTypes';

const resolve=createVehicleImageResolver(vehicleImageManifest,vehicleImageURLs);
const resolveBody=createVehicleImageResolver(bodyOnlyManifest,vehicleImageURLs);
export default function VehicleImage({vehicle,referenceOnly=false}:{vehicle:Row;referenceOnly?:boolean}){
 const identity={manufacturer:vehicle.manufacturer,model:vehicle.model,generation:vehicle.generation,year:vehicle.year};
 const key=JSON.stringify([normalizeVehicleName(identity.manufacturer),normalizeVehicleName(identity.model),normalizeVehicleName(identity.generation),identity.year]);
 const candidates=resolve(identity).filter(c=>!c.asset.referencePhoto||c.asset.transparentCutout===true);
 if(bodyLibraryReady){
  const bodyType=resolvePlaceholderBody(vehicle)||'unknown';
  return <ImageContent key={key+bodyType} candidates={resolveBody({...identity,bodyType})} referenceOnly={false} bodyOnly/>;
 }
 const photo=vehicle.reference_image;
 const safePhoto=photo&&typeof photo.url==='string'&&/^\/api\/v1\/vehicle-photos\/reference\/[a-f0-9]{64}$/.test(photo.url)&&typeof photo.attribution==='string'&&typeof photo.license==='string'&&typeof photo.source_url==='string'&&photo.source_url.startsWith('https://')&&typeof photo.license_url==='string'&&photo.license_url.startsWith('https://')?photo:undefined;
 return <ImageContent key={key+String(referenceOnly)+(safePhoto?.url||'')} candidates={referenceOnly?candidates.filter(c=>c.asset.referencePhoto===true&&c.asset.source.type!=='generated'):candidates} referenceOnly={referenceOnly} photo={safePhoto}/>;
}
function PhotoCredit({attribution,source,license,licenseUrl,unknownYear=false}:{attribution:string;source:string;license:string;licenseUrl?:string;unknownYear?:boolean}){
 return <details className="vehicle-image-attribution">
  <summary title="Авторство та ліцензія фотографії">{unknownYear?'Фото моделі · рік невідомий':'Фото моделі'} <span aria-hidden="true">ⓘ</span></summary>
  <div className="vehicle-image-credit"><span>{attribution}</span><span>Довідкове фото, не фотографія донора.</span><span><a href={source} target="_blank" rel="noreferrer">Джерело</a> · {licenseUrl?<a href={licenseUrl} target="_blank" rel="noreferrer">{license}</a>:license}</span></div>
 </details>;
}
function ImageContent({candidates,referenceOnly,photo,bodyOnly=false}:{candidates:ResolvedVehicleImage[];referenceOnly:boolean;photo?:Row;bodyOnly?:boolean}){
 const [failed,setFailed]=useState<Set<string>>(()=>new Set()),[loaded,setLoaded]=useState('');
 const current=candidates.find(c=>!failed.has(c.asset.id));
 const dynamic=photo&&!failed.has(photo.url)?photo:undefined;
 const actual=!!dynamic||current?.asset.referencePhoto===true;
 const shell='vehicle-image-shell'+(actual?' vehicle-image-shell--reference':'')+(referenceOnly?' vehicle-image-shell--card':'')+(bodyOnly?' vehicle-image-shell--body':'');
 if(dynamic)return <div className={shell}><div className="vehicle-silhouette vehicle-image" data-match="model-reference" data-source="licensed" data-image-state={loaded===dynamic.url?'loaded':'loading'}><img src={dynamic.url} alt="" loading="lazy" decoding="async" draggable={false} onLoad={()=>setLoaded(dynamic.url)} onError={()=>setFailed(previous=>new Set([...previous,dynamic.url]))}/></div><PhotoCredit attribution={dynamic.attribution} source={dynamic.source_url} license={dynamic.license} licenseUrl={dynamic.license_url}/></div>;
 return <div className={shell}><div className="vehicle-silhouette vehicle-image" aria-hidden="true" data-profile={current?.asset.bodyType==='suv'?'suv':'neutral'} data-body-type={current?.bodyType||'unknown'} data-match={current?.tier||'none'} data-source={current?.asset.source.type||'none'} data-image-state={!current?'unavailable':loaded===current.asset.id?'loaded':'loading'}>
  {current?<img key={current.asset.id} alt="" draggable={false} src={current.src} srcSet={current.srcSet} sizes="(max-width: 600px) 140px, 240px" width={current.asset.width} height={current.asset.height} loading="lazy" decoding="async" onLoad={()=>setLoaded(current.asset.id)} onError={()=>setFailed(previous=>new Set([...previous,current.asset.id]))}/>:<span className="vehicle-image-unavailable">{bodyOnly?<CarFront size={64} strokeWidth={1} aria-label="Тип кузова не визначено"/>:referenceOnly?'Фото моделі недоступне':'Зображення недоступне'}</span>}
 </div>{current?.asset.referencePhoto&&current.asset.usage.attribution?<PhotoCredit attribution={current.asset.usage.attribution} source={current.asset.source.reference} license={current.asset.usage.license} licenseUrl={current.asset.usage.licenseUrl} unknownYear={current.tier==='model-reference'}/>:current?.asset.usage.attribution?<small className="vehicle-image-credit">{current.asset.usage.attribution}</small>:null}</div>;
}
