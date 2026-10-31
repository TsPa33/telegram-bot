// Existing paginated API contracts: smart search does not accept condition or price filters.
export function partsSearchQuery(input:{smart:boolean;q:string;vehicle:string;brand:string;model:string;condition:string;category?:string;stock:boolean;page:number}){
 const query=new URLSearchParams({q:input.q,in_stock:String(input.stock),limit:'50',offset:String(input.page*50)});
 if(input.vehicle)query.set('vehicle_id',input.vehicle);
 if(input.brand)query.set('manufacturer',input.brand);
 if(input.model)query.set('model',input.model);
 if(!input.smart&&input.condition)query.set('condition',input.condition);
 if(!input.smart&&input.category)query.set('category_id',input.category);
 return query;
}
