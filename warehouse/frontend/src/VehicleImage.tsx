import {useState} from 'react';
import type {Row} from './api';
import {createVehicleImageResolver,normalizeVehicleName} from './vehicleImageResolver';
import {vehicleImageManifest,vehicleImageURLs} from './vehicleImageManifest';
import type {ResolvedVehicleImage} from './vehicleImageTypes';

const resolve=createVehicleImageResolver(vehicleImageManifest,vehicleImageURLs);
export default function VehicleImage({vehicle}:{vehicle:Row}){
 // Only actual current backend fields. It has no body type; no new backend field.
 const identity={manufacturer:vehicle.manufacturer,model:vehicle.model,generation:vehicle.generation,year:vehicle.year};
 const key=JSON.stringify([normalizeVehicleName(identity.manufacturer),normalizeVehicleName(identity.model),normalizeVehicleName(identity.generation),identity.year]);
 return <ImageContent key={key} candidates={resolve(identity)}/>;
}
function ImageContent({candidates}:{candidates:ResolvedVehicleImage[]}){
 const [failed,setFailed]=useState<Set<string>>(()=>new Set()),[loaded,setLoaded]=useState('');
 const current=candidates.find(c=>!failed.has(c.asset.id));
 return <div className="vehicle-image-shell"><div className="vehicle-silhouette vehicle-image" aria-hidden="true" data-profile={current?.asset.bodyType==='suv'?'suv':'neutral'} data-body-type={current?.bodyType||'unknown'} data-match={current?.tier||'none'} data-source={current?.asset.source.type||'none'} data-image-state={!current?'unavailable':loaded===current.asset.id?'loaded':'loading'}>
  {current?<img key={current.asset.id} alt="" draggable={false} src={current.src} srcSet={current.srcSet} sizes="(max-width: 600px) calc(100vw - 60px), (max-width: 900px) 650px, 500px" width={current.asset.width} height={current.asset.height} loading="lazy" decoding="async" onLoad={()=>setLoaded(current.asset.id)} onError={()=>setFailed(previous=>new Set([...previous,current.asset.id]))}/>:<span className="vehicle-image-unavailable">Зображення недоступне</span>}
 </div>{current?.asset.usage.attribution&&<small className="vehicle-image-credit">{current.asset.usage.attribution}</small>}</div>;
}
