/** Audit descriptions only: never changes the stock operation or creates revenue. */
export const decreaseReasons = [
 {value:'sold',label:'Продано'},
 {value:'defect',label:'Дефект або несправність'},
 {value:'other',label:'Інша причина'},
 {value:'skip',label:'Пропустити'},
] as const;
export function decreaseReason(choice:string, custom:string):string {
 if(choice==='other') { const value=custom.trim(); if(value.length<3) throw new Error('Уточніть причину (від 3 символів)'); return value; }
 if(choice==='sold') throw new Error('Продаж потребує оформлення замовлення');
 if(choice==='defect') return 'Дефект або несправність';
 if(choice==='skip') return 'Без додаткового пояснення (користувач пропустив)';
 throw new Error('Виберіть причину зменшення');
}
