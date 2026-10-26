export function calendarToday(now=new Date(),timeZone='Europe/Kyiv'){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const get=(type:string)=>parts.find(p=>p.type===type)?.value;
 return `${get('year')}-${get('month')}-${get('day')}`;
}
export function recentPeriod(days:number,today=calendarToday()){
 const end=new Date(today+'T00:00:00Z'),start=new Date(end);
 start.setUTCDate(start.getUTCDate()-days+1);
 return {from:start.toISOString().slice(0,10),to:today};
}
export function validPeriod(from:string,to:string){
 const realDate=(s:string)=>/^\d{4}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
 if(!realDate(from)||!realDate(to))return false;
 const days=(Date.parse(to+'T00:00:00Z')-Date.parse(from+'T00:00:00Z'))/86400000;
 return Number.isFinite(days)&&days>=0&&days<366&&from.slice(0,4)>='1900'&&to.slice(0,4)<='2100';
}
export function periodLabel(value:string,interval:string){
 const d=new Date(value+'T00:00:00Z');
 return new Intl.DateTimeFormat('uk-UA',{timeZone:'UTC',...(interval==='month'?{month:'long' as const,year:'numeric' as const}:{day:'2-digit' as const,month:'short' as const,year:'numeric' as const})}).format(d)+(interval==='week'?' · тиждень':'');
}
