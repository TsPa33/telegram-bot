import {useEffect,useRef,useState} from 'react';
import {revealDelta} from './sidebarScroll';
const MOBILE='(max-width: 800px)';
const focusables='a[href],button:not(:disabled),[tabindex]:not([tabindex="-1"])';
export function useSidebarScroll(open:boolean,setOpen:(value:boolean)=>void,path:string,enabled:boolean){
 const sidebar=useRef<HTMLElement>(null),scroll=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const [mobile,setMobile]=useState(()=>matchMedia(MOBILE).matches);
 const mobileOpen=enabled&&mobile&&open;
 useEffect(()=>{if(!enabled)setOpen(false);},[enabled,setOpen]);
 useEffect(()=>{const query=matchMedia(MOBILE);const update=()=>{setMobile(query.matches);if(!query.matches)setOpen(false);};query.addEventListener('change',update);return()=>query.removeEventListener('change',update);},[setOpen]);
 useEffect(()=>{
  if(!enabled)return;
  const menu=scroll.current;if(!menu)return;
  const reveal=(item:Element|null)=>{if(!item)return;const fallback=getComputedStyle(menu).overflowY==='visible';const viewport=menu.contains(item)?(fallback?sidebar.current||menu:menu):(fallback?sidebar.current:null);if(!viewport)return;const box=viewport.getBoundingClientRect(),target=item.getBoundingClientRect();viewport.scrollTop+=revealDelta(box.top+2,box.bottom-2,target.top,target.bottom);};
  const frame=requestAnimationFrame(()=>reveal(menu.querySelector('[aria-current="page"]')));
  const focus=(e:FocusEvent)=>reveal(e.target as Element);sidebar.current?.addEventListener('focusin',focus);
  const observer=new ResizeObserver(()=>reveal(menu.querySelector('[aria-current="page"]')));observer.observe(menu);if(sidebar.current)observer.observe(sidebar.current);
  return()=>{cancelAnimationFrame(frame);observer.disconnect();sidebar.current?.removeEventListener('focusin',focus);};
 },[path,mobileOpen,mobile,enabled]);
 useEffect(()=>{
  if(!mobileOpen)return;
  const body=document.body,root=document.documentElement,position={x:window.scrollX,y:window.scrollY};
  const old={position:body.style.position,top:body.style.top,left:body.style.left,right:body.style.right,width:body.style.width,paddingRight:body.style.paddingRight,overflow:root.style.overflow};
  const gutter=window.innerWidth-root.clientWidth;
  body.style.position='fixed';body.style.top=`-${position.y}px`;body.style.left=`-${position.x}px`;body.style.right='0';body.style.width='100%';
  if(gutter)body.style.paddingRight=`${parseFloat(getComputedStyle(body).paddingRight)+gutter}px`;
  root.style.overflow='hidden';
  const previous=document.activeElement as HTMLElement|null;
  const frame=requestAnimationFrame(()=>{const active=sidebar.current?.querySelector<HTMLElement>('[aria-current="page"]')||sidebar.current?.querySelector<HTMLElement>('a[href]');active?.focus({preventScroll:true});});
  function key(e:KeyboardEvent){
   if(e.key==='Escape'){e.preventDefault();setOpen(false);return;}
   if(e.key!=='Tab')return;
   const nodes=[...(sidebar.current?.querySelectorAll<HTMLElement>(focusables)||[])].filter((n):n is HTMLElement=>!!n&&n.getClientRects().length>0);
   const index=nodes.indexOf(document.activeElement as HTMLElement),next=e.shiftKey?(index<=0?nodes.length-1:index-1):(index<0||index===nodes.length-1?0:index+1);
   if(nodes.length){e.preventDefault();nodes[next].focus({preventScroll:true});}
  }
  document.addEventListener('keydown',key);
  return()=>{
   cancelAnimationFrame(frame);document.removeEventListener('keydown',key);
   body.style.position=old.position;body.style.top=old.top;body.style.left=old.left;body.style.right=old.right;body.style.width=old.width;body.style.paddingRight=old.paddingRight;root.style.overflow=old.overflow;
   window.scrollTo(position.x,position.y);
   const target=trigger.current?.getClientRects().length?trigger.current:previous;
   if(target?.isConnected)target.focus({preventScroll:true});
  };
 },[mobileOpen,setOpen]);
 return {sidebar,scroll,trigger,mobileOpen,mobile};
}
