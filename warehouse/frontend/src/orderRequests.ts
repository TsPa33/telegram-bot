import {useEffect,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';

type Pending={path:string;method:string;body:Row};
const running=new Set<string>();
// Keep an uncertain command unchanged across navigation/reload. No automatic retry.
export function useOrderRequests(accountId:string){
 const key='warehouse-order-pending:'+accountId;
 const [pending,setPending]=useState<Pending|null>(null),[busy,setBusy]=useState(false),[storageError,setStorageError]=useState('');
 const guard=useRef(false);
 useEffect(()=>{function read(){try{setPending(JSON.parse(sessionStorage.getItem(key)||'null'));}catch{setStorageError('Не вдалося прочитати непідтверджений запит.');}}read();window.addEventListener('warehouse:order-pending',read);return()=>window.removeEventListener('warehouse:order-pending',read);},[key]);
 async function send(command:Pending){
  if(guard.current||running.has(key))throw Error('Зачекайте завершення поточного запиту.');
  guard.current=true;running.add(key);setBusy(true);
  try{
   sessionStorage.setItem(key,JSON.stringify(command));setPending(command);window.dispatchEvent(new Event('warehouse:order-pending'));
   const result=await api(command.path,command.method,command.body);
   sessionStorage.removeItem(key);setPending(null);window.dispatchEvent(new Event('warehouse:order-pending'));
   window.dispatchEvent(new Event('warehouse:inventory-changed'));window.dispatchEvent(new Event('warehouse:orders-changed'));return result;
  }catch(e){
   if(e instanceof ApiError&&[400,403,404,409,422].includes(e.status)){sessionStorage.removeItem(key);setPending(null);window.dispatchEvent(new Event('warehouse:order-pending'));}
   throw e;
  }finally{guard.current=false;running.delete(key);setBusy(false);}
 }
 return {pending,busy,storageError,run:async(path:string,method:string,body:Row)=>{
  if(sessionStorage.getItem(key))throw Error('Спочатку перевірте результат попереднього запиту в розділі «Замовлення».');
  return send({path,method,body:{...body,request_key:crypto.randomUUID()}});
 },retry:async()=>{const value=sessionStorage.getItem(key);if(!value)throw Error('Немає запиту для перевірки.');return send(JSON.parse(value));}};
}
