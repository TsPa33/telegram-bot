import type {Row} from './api';

export type VehicleBodyProfile='suv'|'neutral';
const normalize=(value:unknown)=>String(value||'').normalize('NFKC').trim().toLocaleLowerCase('en').replace(/[\s._-]+/g,' ');
// These identify an unambiguous body profile, not generation, fitment or a
// verified model drawing. Ambiguous names (e.g. Lacetti) stay neutral.
const bodyProfiles:Record<string,VehicleBodyProfile>={
 'volvo:xc60':'suv','volvo:xc90':'suv','bmw:x3':'suv',
};
export function vehicleBodyProfile(vehicle:Row):VehicleBodyProfile {
 return bodyProfiles[normalize(vehicle.manufacturer)+':'+normalize(vehicle.model)]||'neutral';
}
// Independently drawn generic SVGs. No third-party art, requests, trademarks or
// model-accurate claims. Future licensed exact-model assets can use a separate
// verified registry without changing the vehicle record or stock data.
export default function VehicleSilhouette({vehicle}:{vehicle:Row}) {
 const profile=vehicleBodyProfile(vehicle);
 return <div className="vehicle-silhouette" aria-hidden="true" data-profile={profile} data-source="carpot-generic">
  <svg viewBox="0 0 560 170" fill="none" focusable="false" preserveAspectRatio="xMidYMid meet">
   {profile==='suv'?<>
    <path d="M40 113 47 85Q49 77 66 75L111 70 153 32Q163 22 183 22H352Q371 22 384 39L413 72 482 79Q507 83 516 100L524 122 508 132H476Q475 97 445 97T413 132H162Q159 97 129 97T96 132H53Q37 131 40 113Z" fill="currentColor"/>
    <path d="m127 70 39-35q7-5 20-5h51v40Zm124 0V30h78l16 40Zm107 0-15-40h10q14 0 23 14l22 26Z" fill="var(--color-surface)"/>
    <path d="M175 79v43m77-43v43m105-43v43M59 105h31m391-12h26" stroke="var(--color-surface)" strokeWidth="3"/>
   </>:<>
    <path d="m37 112 9-23q5-11 28-13l53-8 49-34q12-9 33-9h104q24 0 39 12l45 34 80 10q30 4 39 27l5 17-15 9h-33q-2-36-33-36t-32 36H157q-2-36-33-36t-33 36H51q-18-1-14-22Z" fill="currentColor"/>
    <path d="m146 68 38-27q9-7 25-7h30v34Zm106 0V34h59q20 0 31 10l33 24Z" fill="var(--color-surface)"/>
    <path d="M166 78v44m85-44v44m108-42v42M50 102h38m396-8h25" stroke="var(--color-surface)" strokeWidth="3"/>
   </>}
   <g fill="currentColor"><circle cx={profile==='suv'?129:124} cy="132" r="29"/><circle cx={profile==='suv'?445:440} cy="132" r="29"/></g>
   <g fill="var(--color-surface)"><circle cx={profile==='suv'?129:124} cy="132" r="15"/><circle cx={profile==='suv'?445:440} cy="132" r="15"/></g>
   <path d="M37 164h486" stroke="currentColor" strokeWidth="2" opacity=".35"/>
  </svg>
 </div>;
}
