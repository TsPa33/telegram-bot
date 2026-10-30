import type {Row} from './api';
export function inventoryStockKind(p:Row){
 if(p.archived)return 'archived';
 if(p.assortment_enabled===false)return 'excluded';
 if(p.quantity===0)return 'empty'; // Zero is not proof of a sale.
 return p.available_quantity<=0&&p.reserved_quantity>0?'reserved':'available';
}
export function inventoryMatches(p:Row,{sub,price,state}:{sub:string;price:string;state:string}){
 const hasPrice=p.selling_price!==null&&p.selling_price!==undefined;
 return (!sub||p.subcategory_id===sub)&&(!price||(price==='priced'?hasPrice:!hasPrice))&&(state==='stock'||state==='all'||(state==='reserved'?p.reserved_quantity>0&&p.assortment_enabled!==false:inventoryStockKind(p)===state));
}
export const activeInventoryIds=(rows:Row[])=>rows.filter(p=>!p.archived&&p.assortment_enabled!==false&&p.quantity>0).map(p=>p.id);
