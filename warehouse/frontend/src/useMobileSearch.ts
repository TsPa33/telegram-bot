import {useEffect,useState} from 'react';
export function useMobileSearch(){const [mobile,setMobile]=useState(()=>matchMedia('(max-width: 600px)').matches);useEffect(()=>{const media=matchMedia('(max-width: 600px)'),change=()=>setMobile(media.matches);media.addEventListener('change',change);change();return()=>media.removeEventListener('change',change);},[]);return mobile;}
