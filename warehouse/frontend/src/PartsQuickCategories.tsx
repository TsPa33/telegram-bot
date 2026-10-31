import {useState} from 'react';
import {Boxes,CarFront,Lightbulb,Zap,Wind,Cog,Armchair,Layers3,ChevronDown} from 'lucide-react';
import type {Row} from './api';

export function categoryLabelUk(name:string):string {
 const dictionary:Record<string,string>={
  'кузов':'Кузов','кузовные детали':'Кузовні деталі','освещение':'Освітлення',
  'электрика':'Електрика','электрооборудование':'Електрообладнання',
  'охлаждение':'Охолодження','подвеска':'Підвіска',
  'интерьер':'Інтер’єр','внутренняя отделка':'Оздоблення салону',
  'двигатель':'Двигун','трансмиссия':'Трансмісія',
  'система безопасности':'Система безпеки','безопасность':'Безпека',
  'дополнительные удобства':'Додаткове обладнання'
 };
 return dictionary[name.trim().toLocaleLowerCase('uk')]||name;
}

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

export default function PartsQuickCategories({categories,selected,onSelect,smart}:{
 categories:Row[];selected:string;onSelect:(id:string)=>void;smart:boolean
}){
 const [expanded,setExpanded]=useState(false);
 const roots=categories.filter(c=>c.kind!=='part'&&!c.parent_id);
 const unique=[...new Map(roots.map(c=>[c.id,c])).values()].sort((a,b)=>String(a.name).localeCompare(String(b.name),'uk'));
 const preferred=/кузов|оптик|освіт|свет|електр|электр|охолод|охлаж|двигун|двигател|салон|інтер|интер|підвіск|подвес/i;
 const ordered=[...unique.filter(c=>preferred.test(c.name)),...unique.filter(c=>!preferred.test(c.name))];
 const first=ordered.slice(0,7);
 const visible=expanded?ordered:[...first,...ordered.filter(c=>c.id===selected&&!first.some(f=>f.id===c.id))];
 return <section className="ui11-categories" aria-label="Швидкий вибір категорії">
  <div className="ui11-category-heading"><span>Швидкий вибір категорії</span>
   {smart&&<small>Категорії доступні у звичайному пошуку</small>}
  </div>
  <div className="ui11-category-grid">
   <button type="button" aria-pressed={!selected} className={'ui11-category-tile'+(!selected?' selected':'')} onClick={()=>onSelect('')}>
    <Boxes size={22} strokeWidth={1.7} aria-hidden="true"/><span>Усі категорії</span>
   </button>
   {visible.map(c=>{const Icon=categoryIcon(c.name);return <button type="button" key={c.id} aria-pressed={selected===c.id} title={categoryLabelUk(c.name)}
    className={'ui11-category-tile'+(selected===c.id?' selected':'')} onClick={()=>onSelect(c.id)}>
    <Icon size={22} strokeWidth={1.7} aria-hidden="true"/><span>{categoryLabelUk(c.name)}</span>
   </button>;})}
   {ordered.length>7&&<button type="button" className="ui11-category-tile ui11-category-more" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>
    <ChevronDown size={22} className={expanded?'up':''} aria-hidden="true"/><span>{expanded?'Менше категорій':`Ще ${ordered.length-7}`}</span>
   </button>}
  </div>
  {selected&&<button type="button" className="ui11-clear-category" onClick={()=>onSelect('')}>Скинути категорію</button>}
 </section>;
}
