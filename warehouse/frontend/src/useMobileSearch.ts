import {useEffect,useState} from 'react';
export function useMobileSearch(){const [mobile,setMobile]=useState(()=>matchMedia('(max-width: 600px)').matches);useEffect(()=>{const media=matchMedia('(max-width: 600px)'),change=()=>setMobile(media.matches);media.addEventListener('change',change);change();return()=>media.removeEventListener('change',change);},[]);return mobile;}

/** Track the usable viewport rather than assuming the keyboard is part of 100vh. */
export function useKeyboardViewport(enabled:boolean){
 useEffect(()=>{
  if(!enabled)return;
  const viewport=window.visualViewport;let timer:ReturnType<typeof setTimeout>;
  const update=()=>{document.documentElement.style.setProperty('--mobile-visible-height',(viewport?.height||innerHeight)+'px');clearTimeout(timer);timer=setTimeout(()=>{const field=document.activeElement;if(field instanceof HTMLElement&&field.matches('input,textarea,select')){const r=field.getBoundingClientRect(),top=viewport?.offsetTop||0,bottom=top+(viewport?.height||innerHeight);if(r.bottom>bottom-12||r.top<top+12)field.scrollIntoView({block:'center',behavior:'instant'});}},80);};
  update();viewport?.addEventListener('resize',update);window.addEventListener('resize',update);document.addEventListener('focusin',update);
  return()=>{clearTimeout(timer);viewport?.removeEventListener('resize',update);window.removeEventListener('resize',update);document.removeEventListener('focusin',update);document.documentElement.style.removeProperty('--mobile-visible-height');};
 },[enabled]);
}
