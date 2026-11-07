import type { KeyboardEvent, MouseEvent } from 'react';
import './part-table-interaction.css';
const interactive='button,input,select,textarea,a,label,[role="menu"],[contenteditable="true"]';
export const partRowInteraction=(open:()=>void)=>({
 tabIndex:0,
 onClick:(e:MouseEvent<HTMLElement>)=>{if(!(e.target as Element).closest(interactive)){e.currentTarget.focus({preventScroll:true});open();}},
 onKeyDown:(e:KeyboardEvent<HTMLElement>)=>{if(e.target===e.currentTarget&&['Enter',' '].includes(e.key)){e.preventDefault();open();}},
});
