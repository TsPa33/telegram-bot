import {useEffect,useMemo,useRef,useState} from 'react';
import {api} from './api';
import {CheckCircle2,AlertCircle,Layers3,ChevronDown,ChevronUp,RefreshCw} from 'lucide-react';
import './article-manager.css';

type Category={pt_id:number;name:string;article_count:number};
type StoredPart={id:string;pt_id:number|null;name:string;quantity:number;archived:boolean;article_number?:string};
type Article={art_id:number;article_nr:string;brand:string;part_name:string};
type StockIndex={byType:Map<number,StoredPart>;byName:Map<string,StoredPart>};
type Props={vehicleId:string;ktype:number;categories:Category[];stockIndex:StockIndex;
 localizedName:(name:string)=>string;onSaved:()=>Promise<void>;disabled:boolean};
const normalize=(s:string)=>s.trim().toLocaleLowerCase('uk-UA').replace(/\s+/g,' ');
const tokenRate=2;
const pageSize=12;

export default function ArticleManager({vehicleId,ktype,categories,stockIndex,localizedName,onSaved,disabled}:Props){
 const [opened,setOpened]=useState(false);
 const [missingOnly,setMissingOnly]=useState(false);
 const [query,setQuery]=useState('');
 const [page,setPage]=useState(0);
 const [selected,setSelected]=useState<number[]>([]);
 const [offers,setOffers]=useState<Record<number,Article[]>>({});
 const [active,setActive]=useState<number|null>(null);
 const [chargeConfirm,setChargeConfirm]=useState<number|null>(null);
 const [saving,setSaving]=useState(false);
 const [loading,setLoading]=useState<number|null>(null);
 const [notice,setNotice]=useState('');
 const [proposed,setProposed]=useState<{ptId:number;offer:Article;partId:string}|null>(null);
 const [autoQueue,setAutoQueue]=useState<{ptId:number;offer:Article;partId:string}[]|null>(null);
 const [processed,setProcessed]=useState(0);
 const lock=useRef(false);
 const stockRows=useMemo(()=>categories.map(c=>({category:c,stock:stockIndex.byType.get(c.pt_id)||stockIndex.byName.get(normalize(localizedName(c.name))),label:localizedName(c.name)})).filter(r=>r.stock&&!r.stock.archived),[categories,stockIndex,localizedName]);
 const countWith=stockRows.filter(r=>Boolean(r.stock?.article_number?.trim())).length;
 const missing=stockRows.length-countWith;
 const selectedSet=useMemo(()=>new Set(selected),[selected]);
 const rows=stockRows.filter(r=>(!missingOnly||!r.stock?.article_number?.trim())&&(!query||normalize(r.label).includes(normalize(query))||String(r.stock?.article_number||'').toLowerCase().includes(query.toLowerCase())));
 const visible=rows.slice(page*pageSize,(page+1)*pageSize);
 const remaining=selected.filter(id=>stockRows.some(r=>r.category.pt_id===id&&!r.stock?.article_number?.trim()));
 const estimate=remaining.length*tokenRate;
 useEffect(()=>{setPage(0)},[missingOnly,query]);
 useEffect(()=>{setOffers({});setSelected([]);setActive(null);setChargeConfirm(null);setProposed(null);setAutoQueue(null);setNotice('')},[vehicleId,ktype]);

 async function openOffers(ptId:number){
  setActive(ptId);setNotice('');setChargeConfirm(null);setProposed(null);
  if(offers[ptId])return;
  setLoading(ptId);
  try{
   const result=await api<{articles:Article[]}>('/plan-parts/articles/recover?vehicle_id='+encodeURIComponent(vehicleId)+'&ktype='+ktype+'&pt_id='+ptId,'POST');
   setOffers(prev=>({...prev,[ptId]:result.articles}));
   setNotice('Варіанти відкрито із кешу. 0 токенів.');
  }catch{
   setNotice('Оплачений список артикулів відсутній у доступному кеші. Для нового запиту потрібно підтвердження.');
   setChargeConfirm(ptId);
  }finally{setLoading(null)}
 }
 async function purchase(ptId:number){
  if(disabled||lock.current)return;
  lock.current=true;setLoading(ptId);setChargeConfirm(null);setNotice('Запит до Plan.Parts…');
  try{
   const result=await api<{articles:Article[]}>('/plan-parts/articles/lookup?vehicle_id='+encodeURIComponent(vehicleId)+'&ktype='+ktype+'&pt_id='+ptId,'POST');
   setOffers(prev=>({...prev,[ptId]:result.articles}));setActive(ptId);
   setNotice('Отримано '+result.articles.length+' варіантів. Виберіть номер для картки товару.');
  }catch(e){setNotice('Не вдалося отримати артикули: '+(e as Error).message+'. Після невизначеної помилки спочатку перевірте кеш — не запускайте платний повтор автоматично.');}
  finally{lock.current=false;setLoading(null)}
 }
 async function saveOne(ptId:number,art:Article,partId:string){
  const response=await api<{article_number:string}>('/plan-parts/donor-parts/article/select?vehicle_id='+encodeURIComponent(vehicleId),'POST',{
   ktype,pt_id:ptId,art_id:art.art_id,part_id:partId
  });
  return response.article_number;
 }
 async function confirmOne(){
  if(!proposed||lock.current)return;
  lock.current=true;setSaving(true);
  try{const nr=await saveOne(proposed.ptId,proposed.offer,proposed.partId);await onSaved();setNotice('Артикул '+nr+' записано до картки товару.');setProposed(null)}
  catch(e){setNotice('Не вдалося записати артикул: '+(e as Error).message)}
  finally{lock.current=false;setSaving(false)}
 }
 function planAuto(){
  const queue=stockRows.filter(r=>selectedSet.has(r.category.pt_id)&&!r.stock?.article_number?.trim()).flatMap(r=>{
   const candidates=offers[r.category.pt_id];
   const item=candidates?.find(a=>Boolean(a.article_nr.trim()));
   return item&&r.stock?[{ptId:r.category.pt_id,offer:item,partId:r.stock.id}]:[];
  });
  if(!queue.length){setNotice('Спочатку відкрийте варіанти для вибраних запчастин. Нові платні запити автоматично не виконуються.');return}
  setAutoQueue(queue);setProcessed(0);
 }
 async function confirmAuto(){
  if(!autoQueue||lock.current)return;
  lock.current=true;setSaving(true);let done=0;
  try{
   for(const item of autoQueue){
    await saveOne(item.ptId,item.offer,item.partId);
    done++;setProcessed(done);
   }
   await onSaved();setNotice('Артикули записано для '+done+' запчастин; підбір орієнтовний, перевірте відповідність фізичним деталям.');
  }catch(e){
   await onSaved().catch(()=>{});
   setNotice('Записано '+done+' із '+autoQueue.length+'. Операцію зупинено: '+(e as Error).message+'. Перевірте картки перед повтором.');
  }finally{setAutoQueue(null);setSaving(false);lock.current=false}
 }
 const selectedMissing=remaining.length;
 return <section className="cp-am" aria-label="Менеджер артикулів">
  <button type="button" className="cp-am-toggle" aria-expanded={opened} onClick={()=>setOpened(v=>!v)}>
   <Layers3 size={20}/><strong>Менеджер артикулів</strong><span>Статуси та запис номерів у картки запчастин</span>{opened?<ChevronUp size={19}/>:<ChevronDown size={19}/>}
  </button>
  {opened&&<div className="cp-am-content">
   <div className="cp-am-stats"><div><small>Запчастин на складі</small><strong>{stockRows.length}</strong></div><div><small>З артикулом</small><strong>{countWith}</strong></div><div><small>Без артикула</small><strong>{missing}</strong></div><div><small>Оцінка для всіх відсутніх</small><strong>до {missing*tokenRate} токенів</strong></div></div>
   <p className="cp-am-note">Збережений номер одразу відображається у картці товару. Автоматичний вибір використовує лише вже отримані варіанти; він не підтверджує відповідність OEM або VIN.</p>
   <div className="cp-am-toolbar">
    <button type="button" className="secondary" onClick={()=>setMissingOnly(v=>!v)}>{missingOnly?'Показати всі':'Лише без артикула'}</button>
    <button type="button" className="secondary" disabled={!remaining.length||saving} onClick={planAuto}>Призначити по 1 з отриманих</button>
    <button type="button" className="secondary" disabled={!selectedMissing||saving} onClick={()=>setNotice('Для '+selectedMissing+' вибраних типів можливі нові платні запити — до '+estimate+' токенів. Для пакетного завантаження використовуйте блок «Отримання артикулів Plan.Parts», який має окреме підтвердження та ліміт токенів.')}>Розрахувати токени: до {estimate}</button>
    <input aria-label="Пошук у менеджері артикулів" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Назва або артикул…"/>
   </div>
   <div className="cp-am-select"><button type="button" className="secondary" onClick={()=>setSelected(rows.filter(r=>!r.stock?.article_number?.trim()).map(r=>r.category.pt_id))}>Вибрати всі без артикула</button><button type="button" className="secondary" onClick={()=>setSelected([])}>Зняти вибір</button><small>Вибрано: {selected.length}</small></div>
   {notice&&<p className="cp-am-message" role="status">{notice}</p>}
   {chargeConfirm!==null&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження витрати токенів"><strong>Отримати варіанти — до 2 токенів?</strong><p>Платний запит Plan.Parts для «{localizedName(categories.find(c=>c.pt_id===chargeConfirm)?.name||'Запчастина')}». Отримання не гарантує сумісність з VIN і не присвоює артикул автоматично.</p><button type="button" disabled={disabled||saving} onClick={()=>void purchase(chargeConfirm)}>Підтвердити запит</button><button className="secondary" type="button" onClick={()=>setChargeConfirm(null)}>Скасувати</button></div>}
   {proposed&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження артикула"><strong>Записати {proposed.offer.article_nr} у картку?</strong><p>Виробник: {proposed.offer.brand}. Це aftermarket-пропозиція; сумісність із конкретною деталлю потрібно перевірити.</p><button type="button" disabled={saving} onClick={()=>void confirmOne()}>Записати у картку</button><button type="button" className="secondary" disabled={saving} onClick={()=>setProposed(null)}>Скасувати</button></div>}
   {autoQueue&&<div className="cp-am-dialog" role="alertdialog" aria-label="Підтвердження автоматичного вибору"><strong>Призначити по 1 артикулу для {autoQueue.length} запчастин?</strong><p>Використовуємо перший доступний варіант з уже отриманого кешу, без нових платних запитів. Це довідковий aftermarket-номер, не гарантія сумісності. Перевірте картки після операції.</p>{saving&&<progress value={processed} max={autoQueue.length}/>}<button type="button" disabled={saving} onClick={()=>void confirmAuto()}>Підтвердити запис</button><button type="button" className="secondary" disabled={saving} onClick={()=>setAutoQueue(null)}>Скасувати</button></div>}
   <div className="cp-am-table-wrap"><table className="cp-am-table"><thead><tr><th>Вибір</th><th>Запчастина</th><th>Статус</th><th>Артикул</th><th>Дії</th></tr></thead><tbody>
   {visible.map(({category:c,stock,label})=><tr key={c.pt_id}>
    <td><input type="checkbox" aria-label={'Вибрати '+label} checked={selectedSet.has(c.pt_id)} onChange={e=>setSelected(old=>e.target.checked?[...new Set([...old,c.pt_id])]:old.filter(id=>id!==c.pt_id))}/></td>
    <td><strong>{label}</strong><small>{c.name!==label?c.name:'Тип '+c.pt_id}</small></td>
    <td>{stock?.article_number?.trim()?<span className="cp-am-status yes"><CheckCircle2 size={14}/> Артикул додано</span>:<span className="cp-am-status no"><AlertCircle size={14}/> Не вибрано</span>}</td>
    <td><strong>{stock?.article_number||'—'}</strong></td>
    <td><button type="button" className="secondary" disabled={loading!==null||saving||disabled} onClick={()=>void openOffers(c.pt_id)}>{loading===c.pt_id?'Перевірка…':offers[c.pt_id]?'Варіанти ('+offers[c.pt_id].length+')':'Відкрити варіанти'}</button></td>
   </tr>)}
   {!visible.length&&<tr><td colSpan={5}>За заданими фільтрами запчастин немає.</td></tr>}
   </tbody></table></div>
   {active!==null&&offers[active]&&<section className="cp-am-offers"><h4>{localizedName(categories.find(c=>c.pt_id===active)?.name||'Запчастина')} — {offers[active].length} варіантів</h4><p>Оберіть перевірений номер. Запис автоматично оновить поле «Артикул» у картці товару.</p><div className="cp-am-offers-scroll">{offers[active].slice(0,80).map(a=><div key={a.art_id}><span><strong>{a.article_nr}</strong><small>{a.brand} · {a.part_name}</small></span><button type="button" className="secondary" disabled={saving||!stockRows.find(r=>r.category.pt_id===active)?.stock} onClick={()=>{const stock=stockRows.find(r=>r.category.pt_id===active)?.stock;if(stock)setProposed({ptId:active,offer:a,partId:stock.id})}}>Обрати артикул</button></div>)}</div>{offers[active].length>80&&<small>Показано перші 80 варіантів. Уточніть відповідність деталі перед записом.</small>}</section>}
   <footer className="cp-am-footer"><span>Показано {Math.min((page+1)*pageSize,rows.length)} із {rows.length}</span><button type="button" className="secondary" disabled={page===0} onClick={()=>setPage(p=>p-1)}>Назад</button><span>{page+1} / {Math.max(1,Math.ceil(rows.length/pageSize))}</span><button type="button" className="secondary" disabled={(page+1)*pageSize>=rows.length} onClick={()=>setPage(p=>p+1)}>Далі</button></footer>
  </div>}
 </section>;
}
