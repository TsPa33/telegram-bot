/** Read-only display normalization of already established UA terminology.
 * Pending R13 translations/hierarchy proposals are deliberately NOT applied here.
 * IDs, source names, API search values, hierarchy and fitment are unchanged.
 */
export const establishedCategoryLabels:Readonly<Record<string,string>>=Object.freeze({
 'кузов':'Кузов','кузовные детали':'Кузовні деталі',
 'освещение':'Освітлення','электрика':'Електрика',
 'электрооборудование':'Електрообладнання',
 'охлаждение':'Охолодження','подвеска':'Підвіска',
 'интерьер':'Інтер’єр','внутренняя отделка':'Оздоблення салону',
 'двигатель':'Двигун','трансмиссия':'Трансмісія',
 'система безопасности':'Система безпеки','безопасность':'Безпека',
 'дополнительные удобства':'Додаткове обладнання'
});
const key=(s:string)=>s.trim().normalize('NFKC').toLocaleLowerCase('uk').replace(/\s+/g,' ');
export function catalogueLabelUk(name:string):string{
 const original=String(name||'');
 return establishedCategoryLabels[key(original)]||original;
}
export type CategoryDisplayRow={id?:string;name?:string;kind?:string;parent_id?:string|null;source?:string};
/** Ambiguous identical labels must remain distinguishable in selectors:
 * never deduplicate by text, since different IDs can have inventory references.
 */
export function categoryOptionLabel(row:CategoryDisplayRow,rows:CategoryDisplayRow[]):string{
 const displayed=catalogueLabelUk(row.name||'');
 const dup=rows.some(other=>other.id!==row.id&&other.kind===row.kind
  &&(other.parent_id||'')===(row.parent_id||'')
  &&key(catalogueLabelUk(other.name||''))===key(displayed));
 return dup?displayed+' · '+(row.source||'джерело не вказано')+' · #'+String(row.id).slice(0,8):displayed;
}
