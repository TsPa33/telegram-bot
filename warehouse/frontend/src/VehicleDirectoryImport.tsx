import {useState} from 'react';
import {api,type Row} from './api';
import {Upload,CheckCircle2,AlertCircle} from 'lucide-react';
export default function VehicleDirectoryImport({onImported}:{onImported?:()=>void}){
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState<Row|null>(null),[result,setResult]=useState<Row|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function submit(apply:boolean){
  if(!file||busy)return;setBusy(true);setError('');
  try{
   const form=new FormData();form.append('file',file);
   const report=await api<Row>('/vehicle-directory/import?dry_run='+(!apply?'true':'false'),'POST',form);
   if(apply){setResult(report);setPreview(null);onImported?.();}
   else{setPreview(report);setResult(null);}
  }catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 return <details className="r12-import">
  <summary><Upload size={16}/> Імпорт довідника автомобілів</summary>
  <p>Завантажте файл FileDbBMG.txt (Windows-1251) або підготовлений CarPot_vehicle_catalog.jsonl.gz. Спершу виконується перевірка без запису в БД.</p>
  <label>Файл каталогу <input type="file" accept=".txt,.gz,.jsonl.gz" onChange={e=>{setFile(e.target.files?.[0]||null);setPreview(null);setResult(null);setError('')}}/></label>
  <div className="modal-actions"><button type="button" disabled={!file||busy} onClick={()=>void submit(false)}>Перевірити імпорт</button>
   {preview&&<button type="button" className="primary" disabled={busy} onClick={()=>void submit(true)}>Підтвердити та додати в довідник</button>}</div>
  {preview&&<p role="status"><CheckCircle2 size={16}/> Знайдено: {preview.source_rows} модифікацій; нових: {preview.new}; уже є: {preview.existing}. Донори й склад не змінюються.</p>}
  {result&&<p role="status"><CheckCircle2 size={16}/> Імпорт завершено: нових {result.new}; наявних {result.existing}.</p>}
  {error&&<p role="alert" className="error"><AlertCircle size={15}/>{error}</p>}
 </details>;
}
