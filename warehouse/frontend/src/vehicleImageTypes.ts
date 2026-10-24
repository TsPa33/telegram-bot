export const BODY_TYPES=['sedan','hatchback','wagon','suv','coupe','convertible','minivan','pickup','van','unknown'] as const;
export type BodyType=typeof BODY_TYPES[number];
export type VehicleImageIdentity={manufacturer?:string;model?:string;generation?:string;year?:number;bodyType?:BodyType};
export type ImageAsset={
 id:string;kind:'generation'|'model'|'body'|'unknown';file:string;width:number;height:number;
 manufacturer?:string;model?:string;generation?:string;yearFrom?:number;yearTo?:number;
 bodyType:BodyType;verified:boolean;priority?:number;
 variants?:{file:string;width:number}[];
 source:{type:'generated'|'owned'|'licensed';description:string;reference:string};
 usage:{status:'approved'|'pending';license:string;commercialUse:boolean;attribution?:string};
};
export type BodyRule={manufacturer:string;model:string;generation?:string;yearFrom?:number;yearTo?:number;bodyType:BodyType;evidence:string};
export type VehicleImageManifest={version:string;assets:readonly ImageAsset[];bodyRules:readonly BodyRule[];fallbacks:Record<BodyType,string|null>};
export type ImageTier='generation'|'model-year'|'body'|'unknown';
export type ResolvedVehicleImage={asset:ImageAsset;src:string;srcSet?:string;tier:ImageTier;bodyType:BodyType};
