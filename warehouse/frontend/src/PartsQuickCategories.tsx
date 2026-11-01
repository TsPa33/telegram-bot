import {useState} from 'react';
import {Boxes,CarFront,Lightbulb,Zap,Wind,Cog,Armchair,Layers3,ChevronDown} from 'lucide-react';
import type {Row} from './api';
import {catalogueLabelUk as categoryLabelUk,categoryOptionLabel} from './catalogueLabels';
export {categoryLabelUk};

function categoryIcon(name:string) {
 const label=name.toLocaleLowerCase('uk');
 if(/кузов|двер|body|капот|кузовн/.test(label))return CarFront;
 if(/оптик|освіт|свет|фар|ліхтар/.test(label))return Lightbulb;
 if(/електр|электр|датчик|електрон/.test(label))return Zap;
 if(/охолод|охлаж|кондиц|вентиляц/.test(label))return Wind;
 if(/двиг|двигун|трансм|трансмі|мотор|короб|кпп/.test(label))return Cog;
 if(/інтер|интер|салон|сидін|сиден|обшив/.test(label))return Armchair;
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
