import type { KeyboardEvent, MouseEvent } from 'react';
import './part-table-interaction.css';
const interactive='button,input,select,textarea,a,label,[role="menu"],[contenteditable="true"]';
function open(row:HTMLElement){row.querySelector<HTMLButtonElement>('[data-part-actions]')?.click();}
export const partRowInteraction={
 tabIndex:0,
 onClick:(e:MouseEvent<HTMLElement>)=>{if(!(e.target as Element).closest(interactive))open(e.currentTarget);},
 onKeyDown:(e:KeyboardEvent<HTMLElement>)=>{if(e.target===e.currentTarget&&['Enter',' '].includes(e.key)){e.preventDefault();open(e.currentTarget);}},
};
