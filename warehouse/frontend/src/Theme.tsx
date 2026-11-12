import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {Sun,Moon,Palette} from 'lucide-react';
export const themeKey='warehouse.theme';
export const nightStyleKey='warehouse.nightStyle';
export type NightStyle='emerald'|'onyx'|'gold';
export const nightStyles=[{value:'emerald',label:'Emerald',description:'Графіт і смарагд'},{value:'onyx',label:'Onyx',description:'Чорний і зелений'},{value:'gold',label:'Midnight Gold',description:'Темно-синій і золотий'}] as const;
export function savedTheme(): 'light'|'dark'|null{try{const t=localStorage.getItem(themeKey);return t==='light'||t==='dark'?t:null;}catch{return null;}}
export function savedNightStyle():NightStyle{try{const v=localStorage.getItem(nightStyleKey);return v==='onyx'||v==='gold'?v:'emerald';}catch{return 'emerald';}}
export function systemTheme(){return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
const Theme=createContext({theme:'light',setTheme:(_t:'light'|'dark')=>{},nightStyle:'emerald' as NightStyle,setNightStyle:(_s:NightStyle)=>{}});
export function ThemeProvider({children}:{children:ReactNode}){
 const [theme,set]=useState(()=>savedTheme()||systemTheme());
 const [nightStyle,setStyle]=useState(savedNightStyle);
 const apply=(t:string)=>{document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;};
 useEffect(()=>{apply(theme);document.documentElement.dataset.nightStyle=nightStyle;},[theme,nightStyle]);
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)'),system=()=>{if(!savedTheme())set(systemTheme());},storage=(e:StorageEvent)=>{if(e.key===themeKey||e.key===null)set(savedTheme()||systemTheme());if(e.key===nightStyleKey||e.key===null)setStyle(savedNightStyle());};media.addEventListener('change',system);window.addEventListener('storage',storage);return()=>{media.removeEventListener('change',system);window.removeEventListener('storage',storage);};},[]);
 return <Theme.Provider value={{theme,nightStyle,setNightStyle:v=>{document.documentElement.dataset.nightStyle=v;setStyle(v);apply('dark');set('dark');try{localStorage.setItem(nightStyleKey,v);localStorage.setItem(themeKey,'dark');}catch{}},setTheme:t=>{apply(t);set(t);try{localStorage.setItem(themeKey,t);}catch{}}}}>{children}</Theme.Provider>;
}
export function ThemeSwitch(){const {theme,setTheme,nightStyle,setNightStyle}=useContext(Theme);return <div className="theme-switch" role="group" aria-label="Тема оформлення">{([{value:'light',label:'День',Icon:Sun},{value:'dark',label:'Ніч',Icon:Moon}] as const).map(({value,label,Icon})=><button key={value} type="button" aria-label={label} title={label} aria-pressed={theme===value} onClick={()=>setTheme(value)}><Icon size={18}/></button>)}<label className="night-style-select" title="Стиль нічного режиму"><Palette size={16}/><select aria-label="Стиль нічного режиму" value={nightStyle} onChange={e=>setNightStyle(e.target.value as NightStyle)}>{nightStyles.map(p=><option key={p.value} value={p.value}>{p.label}</option>)}</select></label></div>;}
export function ThemeStylePicker(){const {theme,setTheme,nightStyle,setNightStyle}=useContext(Theme);return <section className="theme-options" aria-label="Оформлення"><h2>Оформлення</h2><div className="theme-option-grid"><button type="button" aria-pressed={theme==='light'} onClick={()=>setTheme('light')}><span className="theme-swatch light"/><strong>Світла</strong><small>Корпоративний стиль</small></button>{nightStyles.map(p=><button type="button" key={p.value} aria-pressed={theme==='dark'&&nightStyle===p.value} onClick={()=>setNightStyle(p.value)}><span className={'theme-swatch '+p.value}/><strong>{p.label}</strong><small>{p.description}</small></button>)}</div></section>;}
