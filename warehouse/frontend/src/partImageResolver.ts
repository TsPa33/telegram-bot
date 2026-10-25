// Resource stage is separate: no unlicensed images or model-fitment guesses.
export const PART_IMAGE_TYPES=['engine','transmission','door','headlight','bumper','wheel','suspension','electronics','unknown'] as const;
export type PartImageType=typeof PART_IMAGE_TYPES[number];
export const partImageAssets:Readonly<Partial<Record<PartImageType,{src:string;provenance:string;commercialRights:true}>>> = Object.freeze({});
const names:Record<string,PartImageType>={'двигун':'engine','коробка передач':'transmission','двері':'door','фара':'headlight','бампер':'bumper','колесо':'wheel','підвіска':'suspension','електронний блок':'electronics'};
export function resolvePartImage(input:{name?:string;categoryName?:string;type?:PartImageType}){
 const normalize=(s?:string)=>s?.normalize('NFKC').trim().toLocaleLowerCase('uk')||'';
 const type=input.type||names[normalize(input.name)]||names[normalize(input.categoryName)]||'unknown';
 return {type,asset:partImageAssets[type]??null};
}
