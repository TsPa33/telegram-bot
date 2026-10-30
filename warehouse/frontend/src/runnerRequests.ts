import {useEffect,useRef,useState} from 'react';
import {api,ApiError,type Row} from './api';
import {validRunnerCommand,runnerRejectionIsFinal,type PendingRunnerCommand} from './runnerCommand';
type Pending=PendingRunnerCommand;
export function useRunnerRequests(actorKey:string){
 const key='warehouse-runner-command:'+actorKey,guard=useRef(false);
 const [pending,setPending]=useState<Pending|null>(null),[busy,setBusy]=useState(false),[storageError,setStorageError]=useState('');
 useEffect(()=>{try{const p=JSON.parse(sessionStorage.getItem(key)||'null');if(p&&!validRunnerCommand(p))throw Error();setPending(p);}catch{setStorageError('Збережена команда недоступна. Не створюйте повторну задачу; перевірте історію.');}},[key]);
 async function send(p:Pending,replay=false){if(guard.current)throw Error('Зачекайте завершення команди');guard.current=true;setBusy(true);try{sessionStorage.setItem(key,JSON.stringify(p));setPending(p);const r=await api(p.path,'POST',p.body);sessionStorage.removeItem(key);setPending(null);return r;}catch(e){if(e instanceof ApiError&&runnerRejectionIsFinal(e.status,replay)){sessionStorage.removeItem(key);setPending(null);}throw e;}finally{guard.current=false;setBusy(false);}}
 return {pending,busy,storageError,run:(path:string,body:Row)=>{if(sessionStorage.getItem(key))throw Error('Спочатку перевірте результат збереженої команди');return send({path,body:{...body,request_key:crypto.randomUUID()}});},recover:()=>{if(!pending)throw Error('Немає збереженої команди');return send(pending,true);}};
}
