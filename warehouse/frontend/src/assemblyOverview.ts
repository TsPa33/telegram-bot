/** Display-only projection. Never changes physical presence or stock. */
type Item = {category?:string|null;presence?:string;completeness?:string;part_id?:string|null;parent_id?:string|null;consumed_operation_id?:string|null;archived?:boolean;quantity?:number};
export function categoryKey(item:Item):string {
 return item.category?.trim() && item.category.trim()!=='Потребує уточнення' ? item.category.trim() : 'Потребує уточнення';
}
export function assemblyOverview(items:Item[]) {
 return {
  checked:items.filter(n=>['present','damaged'].includes(n.presence||'')).length,
  uncategorized:items.filter(n=>categoryKey(n)==='Потребує уточнення').length,
  attention:items.filter(n=>['unchecked','damaged','absent'].includes(n.presence||'')||n.completeness==='incomplete'||categoryKey(n)==='Потребує уточнення').length,
  stocked:items.filter(n=>n.part_id&&!n.parent_id&&!n.consumed_operation_id&&!n.archived&&(n.quantity||0)>0).length,
 };
}
