import {useState} from 'react';
import {Boxes,ChevronDown,ChevronRight,Layers3,Package} from 'lucide-react';
import {corporateCategoryGroups,catalogueLabelUk,categoryOptionLabel} from './catalogueLabels';
import type {Row} from './api';

type Facet={category_id:string|null;subcategory_id:string|null;count:number};
type Props={categories:Row[];facets:Facet[]|undefined;category:string;subcategory:string;onSelect:(category:string,subcategory:string)=>void;total:number;canBrowse:boolean};
export default function StockCategoryRail({categories,facets,category,subcategory,onSelect,total,canBrowse}:Props){
 const [expanded,setExpanded]=useState<string[]>([]);
 const groups=corporateCategoryGroups(categories);
 const known=new Set(groups.flatMap(g=>g.members.map(c=>c.id)));
 const count=(ids:Set<string|undefined>,sub?:string)=>facets?.filter(f=>ids.has(f.category_id||undefined)&&(sub===undefined||(sub==='__none__'?!f.subcategory_id:f.subcategory_id===sub))).reduce((sum,f)=>sum+f.count,0);
 const overall=facets?.reduce((sum,f)=>sum+f.count,0)??(!category&&!subcategory?total:undefined);
 const review=facets?.filter(f=>!known.has(f.category_id||undefined)).reduce((sum,f)=>sum+f.count,0);
 const pick=(id:string,sub='')=>onSelect(id,sub);
 const showCount=(n:number|undefined)=>n===undefined?null:<small className="stock-category-count">{n}</small>;
 const toggle=(key:string)=>setExpanded(v=>v.includes(key)?v.filter(k=>k!==key):[...v,key]);
 return <nav className="stock-category-rail" aria-label="Категорії складу">
  <h3>Категорії запчастин</h3>
  <button type="button" aria-pressed={!category&&!subcategory} onClick={()=>pick('')}><Boxes size={18}/><span>Усі категорії</span>{showCount(overall)}</button>
  {canBrowse&&groups.map(g=>{const ids=g.members.map(c=>c.id).filter(Boolean).join(',');const set=new Set(g.members.map(c=>c.id));const open=expanded.includes(ids);const selected=category===ids;
   const children=categories.filter(c=>set.has(c.parent_id)&&!c.archived&&c.kind==='subcategory').sort((a,b)=>String(a.name).localeCompare(String(b.name),'uk'));
   return <div key={g.label} className="stock-category-group">
    <div className="stock-category-root"><button type="button" aria-pressed={selected&&!subcategory} onClick={()=>{pick(ids);if(!open)setExpanded(v=>[...v,ids]);}}><Layers3 size={17}/><span>{g.label}</span>{showCount(count(set))}</button>{children.length>0&&<button type="button" className="stock-category-expand" aria-label={`${open?'Згорнути':'Розгорнути'} ${g.label}`} aria-expanded={open} onClick={()=>toggle(ids)}>{open?<ChevronDown size={15}/>:<ChevronRight size={15}/>}</button>}</div>
    {open&&<div className="stock-category-children">{children.map(c=><button key={c.id} type="button" aria-pressed={selected&&subcategory===c.id} onClick={()=>pick(ids,c.id)}><span>{categoryOptionLabel(c,categories)}</span>{showCount(count(set,c.id))}</button>)}<button type="button" aria-pressed={selected&&subcategory==='__none__'} onClick={()=>pick(ids,'__none__')}><span>Без підкатегорії</span>{showCount(count(set,'__none__'))}</button></div>}
   </div>;
  })}
  {canBrowse&&<button type="button" aria-pressed={category==='__review__'} onClick={()=>pick('__review__')}><Package size={18}/><span>Потребує уточнення</span>{showCount(review)}</button>}
 </nav>;
}
