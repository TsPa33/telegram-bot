import type {Row} from './api';
export type PendingRunnerCommand={path:string;body:Row};
const uuid=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
export function validRunnerCommand(p:any):p is PendingRunnerCommand{
 if(!p||typeof p.path!=='string'||!p.body||typeof p.body!=='object'||!uuid(p.body.request_key))return false;
 if(p.path==='/admin/import-jobs'&&p.body.job_type==='aleto_offline')return p.body.manufacturer==='Volvo'&&['XC40','XC60','XC90'].includes(p.body.model)&&Object.keys(p.body).every(k=>['request_key','job_type','manufacturer','model'].includes(k));
 if(p.path==='/admin/import-jobs')return uuid(p.body.catalogue_job_id)&&['file_validation','catalogue_preview'].includes(p.body.job_type)&&Object.keys(p.body).every(k=>['request_key','catalogue_job_id','job_type'].includes(k));
 const match=/^\/admin\/import-jobs\/([^/]+)\/(cancel|retry|result\/import)$/.exec(p.path);
 return !!match&&uuid(match[1])&&Object.keys(p.body).length===1;
}
export function runnerRejectionIsFinal(status:number,replay:boolean){return [400,404,422,...(replay?[]:[409,429])].includes(status);}
