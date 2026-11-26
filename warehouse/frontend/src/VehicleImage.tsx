import {useState} from 'react';
import type {Row} from './api';
import {createVehicleImageResolver,normalizeVehicleName} from './vehicleImageResolver';
import {vehicleImageManifest,vehicleImageURLs} from './vehicleImageManifest';
import type {ResolvedVehicleImage} from './vehicleImageTypes';

const resolve=createVehicleImageResolver(vehicleImageManifest,vehicleImageURLs);
export default function VehicleImage({vehicle,referenceOnly=false}:{vehicle:Row;referenceOnly?:boolean}){
 // Only actual current backend fields. It has no body type; no new backend field.
 const identity={manufacturer:vehicle.manufacturer,model:vehicle.model,generation:vehicle.generation,year:vehicle.year};
 const key=JSON.stringify([normalizeVehicleName(identity.manufacturer),normalizeVehicleName(identity.model),normalizeVehicleName(identity.generation),identity.year]);
 const candidates=resolve(identity).filter(c=>!c.asset.referencePhoto||c.asset.transparentCutout===true);
 const photo=vehicle.reference_image;
 const safePhoto=photo&&typeof photo.url==='string'&&/^\/api\/v1\/vehicle-photos\/reference\/[a-f0-9]{64}$/.test(photo.url)&&typeof photo.attribution==='string'&&typeof photo.license==='string'&&typeof photo.source_url==='string'&&photo.source_url.startsWith('https://')&&typeof photo.license_url==='string'&&photo.license_url.startsWith('https://')?photo:undefined;
 return <ImageContent key={key+String(referenceOnly)+(safePhoto?.url||'')} candidates={referenceOnly?candidates.filter(c=>c.asset.referencePhoto===true&&c.asset.source.type!=='generated'):candidates} referenceOnly={referenceOnly} photo={safePhoto}/>;
}
function ImageContent({candidates,referenceOnly,photo}:{candidates:ResolvedVehicleImage[];referenceOnly:boolean;photo?:Row}){
 const [failed,setFailed]=useState<Set<string>>(()=>new Set()),[loaded,setLoaded]=useState('');
 const current=candidates.find(c=>!failed.has(c.asset.id));
 const dynamic=photo&&!failed.has(photo.url)?photo:undefined;
 if(dynamic)return <div className="vehicle-image-shell"><div className="vehicle-silhouette vehicle-image" data-match="model-reference" data-source="licensed" data-image-state={loaded===dynamic.url?'loaded':'loading'}><img src={dynamic.url} alt="" loading="lazy" decoding="async" draggable={false} style={{objectFit:'contain',background:'transparent'}} onLoad={()=>setLoaded(dynamic.url)} onError={()=>setFailed(previous=>new Set([...previous,dynamic.url]))}/></div>{referenceOnly&&<small className="donor-image-caption">Фото моделі · не донор</small>}<small className="vehicle-image-credit"><a href={dynamic.source_url} target="_blank" rel="noreferrer">{dynamic.attribution}</a> · <a href={dynamic.license_url} target="_blank" rel="noreferrer">{dynamic.license}</a></small></div>;
 return <div className="vehicle-image-shell"><div className="vehicle-silhouette vehicle-image" aria-hidden="true" data-profile={current?.asset.bodyType==='suv'?'suv':'neutral'} data-body-type={current?.bodyType||'unknown'} data-match={current?.tier||'none'} data-source={current?.asset.source.type||'none'} data-image-state={!current?'unavailable':loaded===current.asset.id?'loaded':'loading'}>
  {current?<img key={current.asset.id} alt="" draggable={false} src={current.src} srcSet={current.srcSet} sizes="(max-width: 600px) calc(100vw - 60px), (max-width: 900px) 650px, 500px" width={current.asset.width} height={current.asset.height} loading="lazy" decoding="async" onLoad={()=>setLoaded(current.asset.id)} onError={()=>setFailed(previous=>new Set([...previous,current.asset.id]))}/>:<span className="vehicle-image-unavailable">{referenceOnly?'Фото моделі недоступне':'Зображення недоступне'}</span>}
 </div>{referenceOnly&&current&&<small className="donor-image-caption">{current.tier==='model-reference'?'Фото моделі · рік не визначено':'Фото моделі · не донор'}</small>}{current?.asset.usage.attribution&&<small className="vehicle-image-credit">{current.asset.usage.attribution}{current.asset.referencePhoto&&<> · <a href={current.asset.source.reference} target="_blank" rel="noreferrer">Джерело</a>{current.asset.usage.licenseUrl&&<> · <a href={current.asset.usage.licenseUrl} target="_blank" rel="noreferrer">{current.asset.usage.license}</a></>}</>}</small>}</div>;
}
