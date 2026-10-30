import {useCan} from './permissions';
import {Modal,RecordForm} from './components';
import {api} from './api';
// Existing advanced-inventory contract; no stock calculation or implicit batching.
export default function StockBulkDialog({ids,onClose,onSaved}:{ids:string[];onClose:()=>void;onSaved:()=>void}){
 const can=useCan(),options=[...(can('inventory.transfer')?[{value:'transfer',label:'Перемістити'}]:[]),...(can('inventory.archive')?[{value:'archive',label:'Архівувати'}]:[])];
 return <Modal title={`Масова операція · ${ids.length} позицій`} onClose={onClose}>{!options.length?<p role="alert">Недостатньо прав.</p>:ids.length>100?<p role="alert">До 100 деталей в одній складській операції. Звузьте вибір.</p>:<RecordForm fields={[{key:'action',label:'Операція',options},{key:'location',label:'Нове місце зберігання',hint:'Обов’язково для переміщення'},{key:'reason',label:'Причина',required:true,wide:true}]} onSave={async data=>{await api('/parts/bulk-actions','POST',{...data,ids});onSaved();}}/>}</Modal>;
}
