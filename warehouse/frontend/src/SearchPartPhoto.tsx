import {useEffect,useRef,useState} from 'react';
import {Package} from 'lucide-react';
import {api,type Row} from './api';
// The list API has no photos. Read the existing photo endpoint only near visible rows.
export default function SearchPartPhoto({id,name}:{id:string;name:string}){
 const ref=useRef<HTMLSpanElement>(null),[url,setUrl]=useState(''),[failed,setFailed]=useState(false);
 useEffect(()=>{let active=true,started=false;const observer=new IntersectionObserver(entries=>{if(started||!entries.some(e=>e.isIntersecting))return;started=true;observer.disconnect();api<Row[]>('/parts/'+id+'/photos').then(rows=>{if(active)setUrl(rows[0]?.url||'');}).catch(()=>{/* A missing/disabled photo never prevents search. */});},{rootMargin:'150px'});if(ref.current)observer.observe(ref.current);return()=>{active=false;observer.disconnect();};},[id]);
 return <span ref={ref} className="ui3-photo">{url&&!failed?<img src={url} alt={name} loading="lazy" onError={()=>setFailed(true)}/>:<Package size={22} strokeWidth={1.3} aria-label="Фото відсутнє"/>}</span>;
}
