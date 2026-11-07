import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {Sun,Moon} from 'lucide-react';
export const themeKey='warehouse.theme';
export function savedTheme(): 'light'|'dark'|null{try{const t=localStorage.getItem(themeKey);return t==='light'||t==='dark'?t:null;}catch{return null;}}
export function systemTheme(){return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
const Theme=createContext({theme:'light',setTheme:(_t:'light'|'dark')=>{}});
export function ThemeProvider({children}:{children:ReactNode}){
 const [theme,set]=useState(()=>savedTheme()||systemTheme());
 const apply=(t:string)=>{document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;};
 useEffect(()=>{apply(theme);},[theme]);
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)'),system=()=>{if(!savedTheme())set(systemTheme());},storage=(e:StorageEvent)=>{if(e.key===themeKey||e.key===null)set(savedTheme()||systemTheme());};media.addEventListener('change',system);window.addEventListener('storage',storage);return()=>{media.removeEventListener('change',system);window.removeEventListener('storage',storage);};},[]);
 return <Theme.Provider value={{theme,setTheme:t=>{apply(t);set(t);try{localStorage.setItem(themeKey,t);}catch{}}}}>{children}</Theme.Provider>;
}
export function ThemeSwitch(){const {theme,setTheme}=useContext(Theme);return <div className="theme-switch" role="group" aria-label="Тема оформлення">{([{value:'light',label:'День',Icon:Sun},{value:'dark',label:'Ніч',Icon:Moon}] as const).map(({value,label,Icon})=><button key={value} type="button" aria-label={label} title={label} aria-pressed={theme===value} onClick={()=>setTheme(value)}><Icon size={18}/></button>)}</div>;}
