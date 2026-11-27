import React from 'react';
import {createRoot} from 'react-dom/client';
import VehicleImage from '../src/VehicleImage';
import '../src/tokens.css';
import '../src/style.css';
import '../src/design-system.css';
import '../src/vehicle-cards.css';
import '../src/vehicles-r1146.css';
import '../src/premium-emerald-r10.css';
import '../src/theme-surfaces.css';
import '../src/themes.css';
import '../src/corporate-ux-v2.css';
import '../src/integrated-ux-polish.css';
import '../src/mobile-search-checkout.css';
const types=['sedan','hatchback','wagon','suv','coupe','convertible','minivan','pickup','van','tractor','truck','bus'];
const items=[...types.map(body_type=>({manufacturer:'CarPot',model:body_type,year:2020,body_type})),
 {manufacturer:'AUDI',model:'Q5',year:null,vin_details:{conflicts:{body_class:['SUV','MPV']}}},
 {manufacturer:'VOLVO',model:'XC90',year:2016,vin_details:{consistency_issues:{body_class:'ambiguous'}}},
 {manufacturer:'VOLVO',model:'XC90 II',year:2016},
 {manufacturer:'DAF',model:'XF 105',year:2007,dismantling_v3:{global_selection:{modification_description:'FTS 105.460, FTR 105.460'}}},
 {manufacturer:'DAF',model:'XF 105',year:2007,dismantling_v3:{global_selection:{modification_description:'FA 105.460'}}},
 {manufacturer:'Unknown',model:'Unmapped',year:2022,body_type:'unknown'}];
createRoot(document.getElementById('root')!).render(<div className="corporate-donor-grid" style={{display:'grid',gap:16,padding:12}}>{items.map((v,i)=><article key={i} className="vehicle-card vehicle-summary-card r1141-card r1146-card corporate-donor-card"><div className="r1146-card-intro"><div className="corporate-donor-top"><div className="r1146-card-heading"><div><strong>{v.manufacturer} {v.model}</strong><p>{v.year??'Рік не визначено'}</p></div><span className="r1141-status">Заплановано</span></div><div className="r1146-card-photo"><VehicleImage vehicle={v} referenceOnly/></div></div></div></article>)}</div>);
