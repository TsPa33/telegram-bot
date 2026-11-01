import {useState} from 'react';
import {Boxes,CarFront,Lightbulb,Zap,Cog,Armchair,Layers3,ShieldCheck,Disc3,LockKeyhole,Settings2,PlugZap,Fan,SlidersHorizontal,Wrench,Fuel,Gauge,CircleDot,Snowflake,Link2,CircleGauge,Droplets,Package,KeyRound,ClipboardList,Car,Truck,Wind} from 'lucide-react';
import type {Row} from './api';
import {catalogueLabelUk as categoryLabelUk} from './catalogueLabels';
export {categoryLabelUk};

function categoryIcon(name:string) {
 const label=name.toLocaleLowerCase('uk');
 // Prioritize precise terms; generic icon only for genuinely unknown categories.
 if(/очищення фар|очистки фар/.test(label))return Droplets;
 if(/очищення скла|очистки окон|очистки скла|склоочис/.test(label))return Wind;
 if(/подач[іи] палива|топлив|паливн/.test(label))return Fuel;
 if(/підготовка .*суміш|подготовка .*смес/.test(label))return Fuel;
 if(/гальм|тормозн/.test(label))return Disc3;
 if(/зчеплен|сцеплен/.test(label))return CircleDot;
 if(/головна передача|главная передача/.test(label))return CircleGauge;
 if(/коробка передач/.test(label))return Settings2;
 if(/кермов.*керуван|рулевое управл/.test(label))return Gauge;
 if(/кермов|рулев/.test(label))return CircleGauge;
 if(/підвіска та колеса/.test(label))return Car;
 if(/підвіск|амортиз|подвес/.test(label))return SlidersHorizontal;
 if(/ремінн|ремен/.test(label))return Settings2;
 if(/привід кол|привод кол/.test(label))return Link2;
 if(/колеса|шини|колёс/.test(label))return CircleDot;
 if(/причіп|прицеп/.test(label))return Link2;
 if(/запалюван|зажиган|свічк|свеч/.test(label))return PlugZap;
 if(/електр|электр/.test(label))return Zap;
 if(/опалення|отопление|вентиляц/.test(label))return Fan;
 if(/кондиціон|кондиционер/.test(label))return Snowflake;
 if(/система охолодж|система охлажд/.test(label))return Droplets;
 if(/охолод|охлаж/.test(label))return Fan;
 if(/випускн|выхлоп|выпуск/.test(label))return Wind;
 if(/освіт|свет|фар|оптик/.test(label))return Lightbulb;
 if(/безпек|безопас/.test(label))return ShieldCheck;
 if(/замки/.test(label))return LockKeyhole;
 if(/замок/.test(label))return KeyRound;
 if(/комплектуюч/.test(label))return Cog;
 if(/додаткове обладнан/.test(label))return Package;
 if(/перевезенн|перевозк/.test(label))return Truck;
 if(/обладнан|оборудован/.test(label))return Wrench;
 if(/техобслугов|догляд|уход/.test(label))return ClipboardList;
 if(/сервіс|ремонт|деталі для/.test(label))return Wrench;
 if(/силовий агрегат/.test(label))return Settings2;
 if(/двигун|двигател|мотор/.test(label))return Cog;
 if(/кузов|капот/.test(label))return CarFront;
 if(/салон|інтер|интер|оздоблен|отделк/.test(label))return Armchair;
 if(/ходов/.test(label))return Car;
 if(/запалюван/.test(label))return PlugZap;
 return Layers3;
}

type Group={label:string;members:Row[]};
function normalizeLabel(s:string){return s.trim().normalize('NFKC').toLocaleLowerCase('uk').replace(/\s+/g,' ');}
export function groupQuickCategoryRoots(categories:Row[]):Group[]{
 const grouped=new Map<string,Group>();
 for(const row of categories.filter(c=>c.kind!=='part'&&!c.parent_id)){
  const label=categoryLabelUk(String(row.name||''));
  const key=normalizeLabel(label);
  const group=grouped.get(key);
  if(group)group.members.push(row);else grouped.set(key,{label,members:[row]});
 }
 return [...grouped.values()].sort((a,b)=>a.label.localeCompare(b.label,'uk'));
}
const sections=[
 {name:'Двигун та його системи',icon:Cog,terms:/двиг|мотор|силовий агрегат|запал|зажиган|палив|топлив|подачі палива|суміш|смес|охолод|охлаж|ремінн|ремен|випуск|выпуск|впуск/},
 {name:'Трансмісія та привід',icon:Settings2,terms:/трансміс|трансмис|коробка|передач|зчеплен|сцеплен|привід|привод/},
 {name:'Підвіска та ходова частина',icon:Car,terms:/підвіск|подвес|ходов|амортиз|колеса|колёс|шин/},
 {name:'Кермове управління',icon:Gauge,terms:/кермов|рулев/},
 {name:'Гальмівна система',icon:Disc3,terms:/гальм|тормозн/},
 {name:'Кузов та зовнішні деталі',icon:CarFront,terms:/кузов|двер|капот|крыл|крил|замк|замок|дзеркал|зеркал/},
 {name:'Салон та інтер’єр',icon:Armchair,terms:/салон|інтер|интер|оздоблен|отделк|сидін|сиден/},
 {name:'Електрика та електроніка',icon:Zap,terms:/електр|электр|провод|датчик|електрон|стартер|генератор/},
 {name:'Освітлення',icon:Lightbulb,terms:/освіт|освещ|свет|фар|оптик/},
 {name:'Кліматична система',icon:Fan,terms:/кондиціон|кондиционер|опален|отоплен|вентиляц|клімат/},
 {name:'Системи безпеки',icon:ShieldCheck,terms:/безпек|безопас|подушк/},
 {name:'Обладнання та витратні матеріали',icon:Wrench,terms:/обладнан|оборудован|комплект|сервіс|уход|догляд|обслугов|замін|деталі для|причіп|прицеп|замк|замок/}
] as const;
function sectionFor(label:string){
 const n=normalizeLabel(label);
 // These require a specific section instead of a broad match (e.g. cooling).
 if(/система очищення фар|очистки фар/.test(n))return 8;
 if(/замк|замок/.test(n))return 5;
 if(/кондиціон|кондиционер|опален|отоплен|вентиляц/.test(n))return 9;
 if(/кермов|рулев/.test(n))return 3;
 if(/підвіск.*кермов|подвес.*рулев/.test(n))return 2;
 const i=sections.findIndex(s=>s.terms.test(n));
 return i<0?11:i;
}
export default function PartsQuickCategories({categories,selected,onSelect,smart}:{
 categories:Row[];selected:string;onSelect:(id:string)=>void;smart:boolean
}){
 const [activeSection,setActiveSection]=useState<number|null>(null);
 const groups=groupQuickCategoryRoots(categories);
 const sectionGroups=activeSection===null?[]:groups.filter(g=>sectionFor(g.label)===activeSection);
 return <section className="ui11-categories" aria-label="Швидкий вибір категорії">
  <div className="ui11-category-heading"><span>Швидкий вибір категорії</span>
   {smart&&<small>Оберіть систему автомобіля, а потім потрібну групу деталей</small>}
  </div>
  <div className="ui11-category-grid expanded">
   <button type="button" aria-pressed={!selected&&activeSection===null} className={'ui11-category-tile'+(!selected&&activeSection===null?' selected':'')} onClick={()=>{setActiveSection(null);onSelect('');}}>
    <Boxes size={22} strokeWidth={1.7} aria-hidden="true"/><span>Усі категорії</span>
   </button>
   {sections.map((section,i)=>{const Icon=section.icon;
    return <button type="button" key={section.name} className={'ui11-category-tile'+(activeSection===i?' selected':'')} aria-pressed={activeSection===i} aria-expanded={activeSection===i}
    onClick={()=>{setActiveSection(i===activeSection?null:i);}}>
      <Icon size={22} strokeWidth={1.7} aria-hidden="true"/><span>{section.name}</span>
    </button>;
   })}
  </div>
  {activeSection!==null&&<div className="ui11-section-children" aria-label={'Підгрупи: '+sections[activeSection].name}>
   <div className="ui11-category-heading"><span>{sections[activeSection].name} — підгрупи</span>
    <button type="button" className="secondary" onClick={()=>{setActiveSection(null);}}>До основних розділів</button>
   </div>
   <div className="ui11-category-grid expanded">
    {sectionGroups.map(g=>{const Icon=categoryIcon(g.label);const ids=g.members.map(c=>c.id);const active=selected.split(',').some(id=>ids.includes(id));return <button type="button" key={normalizeLabel(g.label)} aria-pressed={active}
      className={'ui11-category-tile'+(active?' selected':'')} onClick={()=>onSelect(ids.join(','))}>
      <Icon size={22} strokeWidth={1.7} aria-hidden="true"/><span>{g.label}</span></button>})}
   </div>
   {sectionGroups.length===0&&<p>Підгрупи цього розділу поки відсутні в каталозі.</p>}
  </div>}
  {selected&&<button type="button" className="ui11-clear-category" onClick={()=>{onSelect('');}}>Скинути категорію</button>}
 </section>;
}
