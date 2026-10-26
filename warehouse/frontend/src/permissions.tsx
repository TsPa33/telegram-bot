import {createContext,useContext} from 'react';
import type {Row} from './api';
import {allowed} from './access';
export {allowed,roleLabel,identityKey,ADVANCED_PERMISSIONS} from './access';
export const TeamIdentity=createContext<Row|null>(null);
export const useCan=()=>{const user=useContext(TeamIdentity);return (permission:string)=>allowed(user,permission);};
export function Permit({permission,children}:{permission:string;children:React.ReactNode}){
 const can=useCan();return can(permission)?children:null;
}
