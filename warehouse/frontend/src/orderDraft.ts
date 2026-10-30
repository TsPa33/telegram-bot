export type LineDraft={part_id:string;name:string;donor:string;quantity:string;unit_price:string;currency:string;oem:string;available?:number};
export function linePayload(lines:LineDraft[]){return lines.map(line=>{const price=line.unit_price.replace(',','.');if(!/^\d{1,12}(\.\d{1,2})?$/.test(price))throw Error('Вкажіть погоджену ціну кожної деталі з точністю до двох знаків.');if(!/^\d+$/.test(line.quantity)||+line.quantity<1||+line.quantity>1000000)throw Error('Кількість має бути цілим числом від 1 до 1 000 000.');return {part_id:line.part_id,quantity:Number(line.quantity),unit_price:price,currency:line.currency};});}
export function draftAmounts(lines:LineDraft[]){
 const values:Record<string,bigint>={};for(const line of lines){const match=/^(\d{1,12})(?:[.,](\d{1,2}))?$/.exec(line.unit_price);if(match&&/^\d+$/.test(line.quantity)&&+line.quantity>=1&&+line.quantity<=1000000)values[line.currency]=(values[line.currency]||0n)+(BigInt(match[1])*100n+BigInt((match[2]||'').padEnd(2,'0')))*BigInt(line.quantity);}
 return Object.fromEntries(Object.entries(values).map(([currency,cents])=>[currency,`${cents/100n}.${String(cents%100n).padStart(2,'0')}`]));
}
