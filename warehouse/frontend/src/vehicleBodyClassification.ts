import type {BodyType} from './vehicleImageTypes';
import {normalizeVehicleName} from './vehicleImageResolver';
const aliases:Readonly<Record<string,BodyType>>={
 sedan:'sedan',saloon:'sedan','sedan/saloon':'sedan','седан':'sedan',
 hatchback:'hatchback','хетчбек':'hatchback','хечбек':'hatchback','хэтчбек':'hatchback','hatchback/liftback/notchback':'hatchback','liftback':'hatchback','ліфтбек':'hatchback',
 wagon:'wagon','station wagon':'wagon',estate:'wagon','універсал':'wagon','комби':'wagon','универсал':'wagon',
 suv:'suv',crossover:'suv','sport utility vehicle':'suv','sport utility vehicle (suv)':'suv','позашляховик (suv)':'suv','кросовер':'suv','позашляховик':'suv',
 coupe:'coupe','купе':'coupe',convertible:'convertible',cabriolet:'convertible','кабріолет':'convertible',
 minivan:'minivan',mpv:'minivan','мінівен':'minivan',pickup:'pickup','pick-up':'pickup','пікап':'pickup',
 van:'van','cargo van':'van','panel van':'van','фургон':'van','грузовой фургон':'van',
 tractor:'tractor','truck tractor':'tractor','tractor unit':'tractor','тягач':'tractor','сідельний тягач':'tractor','седельный тягач':'tractor','semitrailer tractor':'tractor',
 truck:'truck','box truck':'truck','rigid truck':'truck','вантажівка':'truck','грузовик c бортовой платформой/шасси':'truck','грузовик с бортовой платформой/шасси':'truck','вантажівка з бортовою платформою/шасі':'truck',
 bus:'bus',coach:'bus','автобус':'bus'
};
export function normalizeBodyType(value:unknown):BodyType|undefined{
 const key=normalizeVehicleName(value);
 return Object.prototype.hasOwnProperty.call(aliases,key)?aliases[key]:undefined;
}
// Explicit reviewed body-only rules; never derive a type from brand alone.
const known:Readonly<Record<string,BodyType>>={
 'alfa romeo|147':'hatchback','alfa romeo|147 (937_)':'hatchback','alfa romeo|147 937_':'hatchback',
 'audi|q5':'suv','volvo|xc60':'suv','volvo|xc90':'suv','volvo|xc90 i':'suv','volvo|xc90 ii':'suv','volvo|xc90 1':'suv','volvo|xc90 2':'suv','volvo|xc60 i':'suv','volvo|xc60 ii':'suv','audi|q5 (8r)':'suv','audi|q5 (fy)':'suv','audi|q5 8r':'suv','audi|q5 fy':'suv','bmw|x3':'suv'
};

// Exact catalogue names confirmed by read-only Oracle: 9649 and 8387 are
// saddle tractors, 8391 is a platform/chassis truck. Do not guess by XF alone.
const dafXF105:Readonly<Record<string,BodyType>>={
 'fts 105.460, ftr 105.460':'tractor','ft 105.460':'tractor','fa 105.460':'truck'
};
function onlyBody(values:unknown[]):BodyType|undefined{
 const unique=new Set(values.map(normalizeBodyType).filter((v):v is BodyType=>!!v));
 return unique.size>1?'unknown':unique.values().next().value;
}
export function resolvePlaceholderBody(vehicle:Record<string,any>):BodyType|undefined{
 // Classification is display-only: never writes VIN evidence or vehicle identity.
 const details=vehicle.vin_details;
 const catalogue=vehicle.dismantling_v3?.global_selection;
 const oracle=vehicle.dismantling_v3?.oracle_vehicle_identity;
 const declared=onlyBody([vehicle.body_type,vehicle.bodyType,vehicle.body_class,catalogue?.body_type,catalogue?.body_class,catalogue?.platform_type,oracle?.body_type,oracle?.body_class,oracle?.platform_type]);
 const key=normalizeVehicleName(vehicle.manufacturer)+'|'+normalizeVehicleName(vehicle.model);
 const family=known[key];
 const modification=key==='daf|xf 105'||key==='daf|xf105'
  ? onlyBody([catalogue?.modification_description,oracle?.modification,oracle?.modification_description].map(v=>dafXF105[normalizeVehicleName(v)]))
  : undefined;
 // Explicit selected catalogue/vehicle body is stronger than noisy decoded VIN.
 // An unambiguous family can still supply a generic illustration when VIN has
 // competing values (e.g. SUV/MPV) or conflicts; no fitment inference.
 if(declared==='unknown'||modification==='unknown')return 'unknown';
 if(declared&&family&&declared!==family)return 'unknown';
 if(declared&&modification&&declared!==modification)return 'unknown';
 if(declared)return declared;
 if(modification)return modification;
 if(family)return family;
 if(details?.conflicts?.body_class||details?.consistency_issues?.body_class)return 'unknown';
 return onlyBody([details?.characteristics?.body_class,details?.decoded?.body_class]);
}
