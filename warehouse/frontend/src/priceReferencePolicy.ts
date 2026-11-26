import type {Row} from './api';
export type Rule={mode:'average'|'minimum'|'maximum';percent:string;similar:boolean};
export const defaultRule:Rule={mode:'average',percent:'0',similar:false};
export function cents(value:unknown):bigint|null{
 const m=/^(\d{1,12})(?:\.(\d{1,2}))?$/.exec(String(value??''));
 return m?BigInt(m[1])*100n+BigInt((m[2]||'').padEnd(2,'0')):null;
}
export function formatCents(n:bigint){return (n/100n).toString()+'.'+(n%100n).toString().padStart(2,'0');}
export function adjusted(value:unknown,percent:string){
 const n=cents(value),m=/^(-?)(\d{1,3})(?:\.(\d{1,2}))?$/.exec(percent);
 if(n===null||!m)return null;
 const p=(BigInt(m[2])*100n+BigInt((m[3]||'').padEnd(2,'0')))*(m[1]? -1n:1n);
 if(p< -9900n||p>10000n)return null;
 const result=(n*(10000n+p)+5000n)/10000n;
 return result>0n&&result<=99999999999999n?formatCents(result):null;
}
export function chooseReference(data:Row,context:Row,rule:Rule){
 if(data.truncated||!context.eligible||!['used','new','damaged','refurbished'].includes(context.condition))return null;
 const groups=(data.references||[]).filter((g:Row)=>g.currency===context.currency&&g.condition===context.condition&&
  g.offer_count>=3&&cents(g.average)!==null&&cents(g.minimum)!==null&&cents(g.maximum)!==null&&
  (g.match==='exact'||(rule.similar&&g.match==='similar')));
 const exact=groups.filter((g:Row)=>g.match==='exact'),eligible=exact.length?exact:groups;
 if(eligible.length!==1)return null;
 const g=eligible[0],value=adjusted(g[rule.mode],rule.percent);
 return value?{value,group:g}:null;
}
export function summary(rows:Row[]){
 const count=(...states:string[])=>rows.filter(r=>states.includes(r.state)).length;
 return {total:rows.length,checked:count('ready','attention','skipped','applied','error'),ready:count('ready'),applied:count('applied'),attention:count('attention','error'),skipped:count('skipped'),pending:count('pending'),uncertain:count('uncertain')};
}
