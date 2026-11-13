import {useState} from 'react';
import {api,type Row} from './api';
export function oemOptions(row:Row):string[]{
 const raw=row.oem_options||row.oem_provenance?.alternatives?.map((a:Row)=>a.oem_number)||[];
 return Array.from(new Set<string>(raw.filter((n:unknown)=>typeof n==='string'&&n)));
}
export default function OemField({value,options,editable,onChange}:{value:string;options:string[];editable:boolean;onChange:(v:string)=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(false);
 const list=Array.from(new Set([value,...options].filter(Boolean)));
 if(!value)return <span>—</span>;
 if(!editable||list.length<2)return <span>{value}</span>;
 return <span className="oem-inline"><select aria-label="OEM" title="OEM" value={value} disabled={busy} onChange={async e=>{setBusy(true);setError(false);try{await onChange(e.target.value)}catch{setError(true)}finally{setBusy(false)}}}>{list.map(n=><option key={n} value={n}>{n}</option>)}</select>{error&&<small role="alert">Не вдалося зберегти</small>}</span>
}
export function StockOemField({part,editable,onSaved}:{part:Row;editable:boolean;onSaved:(p:Row)=>void}){
 return <OemField key={part.id} value={part.oem_number||''} options={oemOptions(part)} editable={editable} onChange={async n=>onSaved(await api('/parts/'+part.id+'/characteristics','PATCH',{expected:{oem_number:part.oem_number},values:{oem_number:n}}))}/>
}
