import {useEffect,useLayoutEffect,useId,useRef,useState,type ReactNode} from 'react';
export default function QuickPreviewFrame({onClose,children}:{onClose:()=>void;children:ReactNode}){
 const slot=useRef<HTMLDivElement>(null);
 const launcher=useRef(document.activeElement as HTMLElement|null);
 const dialog=useRef<HTMLDialogElement>(null),close=useRef(onClose),id=useId();close.current=onClose;
 const [mobile,setMobile]=useState(()=>matchMedia('(max-width:900px)').matches);
 useEffect(()=>{const m=matchMedia('(max-width:900px)'),change=()=>setMobile(m.matches);m.addEventListener('change',change);return()=>m.removeEventListener('change',change);},[]);
 useEffect(()=>{const d=dialog.current!,overflow=document.body.style.overflow;d.close();if(mobile){d.showModal();document.body.style.overflow='hidden';}else d.show();
 const dismiss=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!e.defaultPrevented&&!document.querySelector(':popover-open')&&!Array.from(document.querySelectorAll('dialog:modal')).some(other=>other!==d)){e.preventDefault();close.current();}};
 const outside=(e:PointerEvent)=>{const target=e.target as Element;if(!mobile&&!d.contains(target)&&!target.closest('.ui3-part,.wd-row,.stock-compact-table,.ui11-results-list,.wd-list,.stock-actions-menu,.part-row-menu,dialog'))close.current();};
 document.addEventListener('keydown',dismiss);document.addEventListener('pointerdown',outside);return()=>{document.removeEventListener('keydown',dismiss);document.removeEventListener('pointerdown',outside);d.close();if(mobile)document.body.style.overflow=overflow;if(launcher.current?.isConnected&&mobile)launcher.current.focus({preventScroll:true});};},[mobile]);
 useLayoutEffect(()=>{const measure=()=>{const available=mobile?innerHeight-24:innerHeight-Math.max(16,slot.current?.getBoundingClientRect().top||16)-16;slot.current?.style.setProperty('--preview-available-height',Math.max(160,available)+'px');};measure();window.addEventListener('scroll',measure,true);window.addEventListener('resize',measure);return()=>{window.removeEventListener('scroll',measure,true);window.removeEventListener('resize',measure);};});
 return <div ref={slot} className="part-preview-slot"><dialog id={id} ref={dialog} className={'part-preview-frame'+(mobile?' mobile':'')} aria-label="Швидкий перегляд запчастини" onCancel={e=>{e.preventDefault();close.current();}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close.current();}}}>{children}</dialog></div>;
}
