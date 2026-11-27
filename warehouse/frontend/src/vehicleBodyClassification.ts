import type {BodyType} from './vehicleImageTypes';
import {normalizeVehicleName} from './vehicleImageResolver';
const aliases:Readonly<Record<string,BodyType>>={
 sedan:'sedan',saloon:'sedan','sedan/saloon':'sedan','седан':'sedan',
 hatchback:'hatchback','хетчбек':'hatchback','хечбек':'hatchback','hatchback/liftback/notchback':'hatchback','liftback':'hatchback','ліфтбек':'hatchback',
 wagon:'wagon','station wagon':'wagon',estate:'wagon','універсал':'wagon',
 suv:'suv',crossover:'suv','sport utility vehicle':'suv','sport utility vehicle (suv)':'suv','позашляховик (suv)':'suv','кросовер':'suv','позашляховик':'suv',
 coupe:'coupe','купе':'coupe',convertible:'convertible',cabriolet:'convertible','кабріолет':'convertible',
 minivan:'minivan',mpv:'minivan','мінівен':'minivan',pickup:'pickup','pick-up':'pickup','пікап':'pickup',
 van:'van','cargo van':'van','panel van':'van','фургон':'van',
 tractor:'tractor','truck tractor':'tractor','tractor unit':'tractor','тягач':'tractor',
 truck:'truck','box truck':'truck','rigid truck':'truck','вантажівка':'truck',
 bus:'bus',coach:'bus','автобус':'bus'
};
export function normalizeBodyType(value:unknown):BodyType|undefined{
 const key=normalizeVehicleName(value);
 return Object.prototype.hasOwnProperty.call(aliases,key)?aliases[key]:undefined;
}
// Explicit reviewed body-only rules; never derive a type from brand alone.
const known:Readonly<Record<string,BodyType>>={
 'alfa romeo|147':'hatchback','alfa romeo|147 (937_)':'hatchback','alfa romeo|147 937_':'hatchback',
 'audi|q5':'suv','volvo|xc60':'suv','volvo|xc90':'suv','bmw|x3':'suv'
};
export function resolvePlaceholderBody(vehicle:Record<string,any>):BodyType|undefined{
 // Some legacy records have no explicit body field; missing or contradictory evidence stays unknown.
 const details=vehicle.vin_details;
 // Actual persisted VIN details contain characteristics and decoded, not a new DB column.
 if(details?.conflicts?.body_class||details?.consistency_issues?.body_class)return 'unknown';
 const raw=[vehicle.body_type,vehicle.bodyType,vehicle.body_class,details?.characteristics?.body_class,details?.decoded?.body_class,vehicle.dismantling_v3?.global_selection?.body_type,vehicle.dismantling_v3?.oracle_vehicle_identity?.body_type];
 const explicit=raw.map(normalizeBodyType).filter((v):v is BodyType=>!!v);
 const unique=new Set(explicit);
 if(unique.size>1)return 'unknown';
 if(unique.size===1)return explicit[0];
 return known[normalizeVehicleName(vehicle.manufacturer)+'|'+normalizeVehicleName(vehicle.model)];
}
