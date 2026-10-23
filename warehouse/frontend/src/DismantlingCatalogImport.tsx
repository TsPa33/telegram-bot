import { useState } from "react";
import { api, type Row } from "./api";
export default function DismantlingCatalogImport({onImported}: {onImported: () => void}) {
  const [payload,setPayload]=useState<Row|null>(null),[rights,setRights]=useState(false),[preview,setPreview]=useState<Row|null>(null);
  const [error,setError]=useState(""),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  async function submit(dry: boolean) {
    if(!payload||!rights)return;setBusy(true);setError("");
    try {const result=await api(`/dismantling/catalog/import?dry_run=${dry}`,"POST",{...payload,rights_confirmed:rights});
      if(dry)setPreview(result);else {setMessage(`Імпортовано: нових ${result.created}, оновлено ${result.updated}. Нові типи автоматично з’являться у списку цього автомобіля.`);setPreview(null);onImported();}
    } catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <details className="dismantling-import"><summary>Розширити власний каталог</summary>
    <p>Базовий список містить 33 потенційні типи, не повну комплектацію XC90. Власний JSON може містити до 10 000 типів із категоріями. Імпорт не створює залишків.</p>
    <label>JSON власного каталогу<input type="file" accept="application/json,.json" disabled={busy} onChange={async e=>{
      setPreview(null);setPayload(null);setError("");setMessage("");setRights(false);
      try {const file=e.target.files?.[0];if(!file)return;if(file.size>5*1024*1024)throw Error("Файл завеликий (до 5 МБ)");const parsed=JSON.parse(await file.text());if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw Error('JSON object required');setPayload(parsed);}catch{setError("Не вдалося прочитати JSON каталогу (до 5 МБ).");}
    }}/></label>
    <label className="dismantling-select"><input type="checkbox" checked={rights} disabled={busy} onChange={e=>{setRights(e.target.checked);setPreview(null);}}/> Маю права на збереження й використання цих даних; джерело та ліцензію вказано у файлі.</label>
    <div className="modal-actions"><button disabled={busy||!payload||!rights} onClick={()=>submit(true)}>Перевірити каталог</button>
      {preview&&<button disabled={busy} onClick={()=>submit(false)}>Імпортувати до власного довідника</button>}</div>
    {preview&&<p>Нових: {preview.created}. Оновлено: {preview.updated}. Усього в джерелі: {preview.total}.</p>}
    {message&&<p role="status">{message}</p>}{error&&<p role="alert" className="error">{error}</p>}
  </details>;
}
