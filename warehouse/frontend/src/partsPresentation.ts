import type {Row} from './api';
// Presentation only: authority, cohort classification and money stay on the server.
export function priceKind(g?:Row){return !g?'loading':g.level==='A'?'recommended':g.level==='B'||g.level==='C'?'similar':'none';}
export function priceCounts(items:Row[],guidance:Record<string,Row>){
 const counts={total:items.length,market:0,recommended:0,none:0,loading:0};
 for(const item of items){const k=item.part_id?priceKind(guidance[item.part_id]):'none';if(k==='loading')counts.loading++;else if(k==='none')counts.none++;else{counts.market++;if(k==='recommended')counts.recommended++;}}
 return counts;
}
export function matchesPart(item:Row,filters:{q:string;category:string;sub:string;state:string;price:string},g?:Row){
 const text=[item.name,item.position,item.stock?.oem_number,item.stock?.article_number].join(' ').toLocaleLowerCase('uk-UA');
 const state=!item.included?'excluded':item.stock?.archived?'archived':item.stock?.state||'empty';
 const kind=item.part_id?priceKind(g):'none';
 const priceMatches=!filters.price||(filters.price==='market'?(kind==='recommended'||kind==='similar'):filters.price==='recommended'?kind==='recommended':kind==='none');
 return (!filters.q||text.includes(filters.q.trim().toLocaleLowerCase('uk-UA')))&&(!filters.category||item.category===filters.category)&&(!filters.sub||item.subcategory===filters.sub)&&(!filters.state||state===filters.state)&&priceMatches;
}
