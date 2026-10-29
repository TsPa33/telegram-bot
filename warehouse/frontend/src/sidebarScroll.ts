// Geometry only; never scroll the document to reveal a fixed navigation item.
export function revealDelta(top:number,bottom:number,itemTop:number,itemBottom:number){
 if(itemBottom-itemTop>=bottom-top)return itemTop-top;
 if(itemTop<top)return itemTop-top;
 if(itemBottom>bottom)return itemBottom-bottom;
 return 0;
}
