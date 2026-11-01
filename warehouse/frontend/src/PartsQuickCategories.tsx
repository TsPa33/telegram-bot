import {Boxes,CarFront,Lightbulb,Zap,Cog,Armchair,Layers3,ChevronDown,ShieldCheck,Disc3,LockKeyhole,Settings2,PlugZap,Fan,SlidersHorizontal,Wrench,Fuel,Gauge,CircleDot,Snowflake,Link2,CircleGauge,Droplets,Package,KeyRound,ClipboardList,Car,Truck,Wind} from 'lucide-react';
import type {Row} from './api';
import {catalogueLabelUk as categoryLabelUk,categoryOptionLabel} from './catalogueLabels';
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

export default function PartsQuickCategories({categories,selected,onSelect,smart}:{
 categories:Row[];selected:string;onSelect:(id:string)=>void;smart:boolean
}){
 const [expanded,setExpanded]=useState(false);
 const [openGroup,setOpenGroup]=useState<string|null>(null);
 const groups=groupQuickCategoryRoots(categories);
 const preferred=/кузов|оптик|освіт|електр|охолод|двигун|салон|інтер|підвіск/i;
 const ordered=[...groups.filter(g=>preferred.test(g.label)),...groups.filter(g=>!preferred.test(g.label))];
 const first=ordered.slice(0,7);
 const visible=expanded?ordered:[...first,...ordered.filter(g=>g.members.some(c=>c.id===selected)&&!first.includes(g))];
 const allRoots=groups.flatMap(g=>g.members);
 return <section className="ui11-categories" aria-label="Швидкий вибір категорії">
  <div className="ui11-category-heading"><span>Швидкий вибір категорії</span>
   {smart&&<small>Категорії доступні у звичайному пошуку</small>}
  </div>
  <div className={'ui11-category-grid'+(expanded?' expanded':'')}>
   <button type="button" aria-pressed={!selected} className={'ui11-category-tile'+(!selected?' selected':'')} onClick={()=>{setOpenGroup(null);onSelect('');}}>
    <Boxes size={22} strokeWidth={1.7} aria-hidden="true"/><span>Усі категорії</span>
   </button>
   {visible.map(g=>{const Icon=categoryIcon(g.label);const active=g.members.some(c=>c.id===selected);return <button type="button" key={normalizeLabel(g.label)} aria-pressed={active} aria-expanded={g.members.length>1?openGroup===normalizeLabel(g.label):undefined}
    title={g.members.length>1?g.label+' — '+g.members.length+' джерела':g.label}
    className={'ui11-category-tile'+(active?' selected':'')} onClick={()=>{
      if(g.members.length===1){setOpenGroup(null);onSelect(g.members[0].id);}
      else setOpenGroup(prev=>prev===normalizeLabel(g.label)?null:normalizeLabel(g.label));
    }}>
    <Icon size={22} strokeWidth={1.7} aria-hidden="true"/><span>{g.label}{g.members.length>1?' ('+g.members.length+')':''}</span>
   </button>;})}
   {ordered.length>7&&<button type="button" className="ui11-category-tile ui11-category-more" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>
    <ChevronDown size={22} className={expanded?'up':''} aria-hidden="true"/><span>{expanded?'Менше категорій':`Ще ${ordered.length-7}`}</span>
   </button>}
  </div>
  {openGroup&&(()=>{const group=groups.find(g=>normalizeLabel(g.label)===openGroup);
   return group?<div className="ui11-category-sources" aria-label={'Варіанти '+group.label}>
    <p>Оберіть джерело «{group.label}». Кожен варіант зберігає власні складські зв’язки.</p>
    {group.members.map(c=><button type="button" key={c.id} className={selected===c.id?'selected':'secondary'}
       aria-pressed={selected===c.id} onClick={()=>{onSelect(c.id);setOpenGroup(null);}}>
       {categoryOptionLabel(c,allRoots)}
    </button>)}
   </div>:null;
  })()}
  {selected&&<button type="button" className="ui11-clear-category" onClick={()=>{setOpenGroup(null);onSelect('');}}>Скинути категорію</button>}
 </section>;
}
