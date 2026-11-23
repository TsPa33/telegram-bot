import {useEffect,useState} from 'react';
import {api} from './api';

export type SourceIdentity={
  source_modification_id:number;
  model_id:number;
  manufacturer_id:number;
  kind:'passenger'|'commercial';
  model:string;
  modification:string;
  construction_interval:string|null;
};

type Maker={manufacturer_id:number;manufacturer:string;kind:'passenger'|'commercial'};
type Item={id:number;name:string;construction_interval:string|null};
type Page={items:Item[];next_after:number|null};
type Makers={items:Maker[];partial:boolean};

export default function VinSourcePicker({
  manufacturer,onSelect,selected
}:{
  manufacturer:string;
  onSelect:(item:SourceIdentity|null)=>void;
  selected:SourceIdentity|null;
}){
  const [makers,setMakers]=useState<Maker[]>([]);
  const [makerKey,setMakerKey]=useState('');
  const [models,setModels]=useState<Item[]>([]);
  const [modelId,setModelId]=useState('');
  const [modelAfter,setModelAfter]=useState<number|null>(null);
  const [variants,setVariants]=useState<Item[]>([]);
  const [variantId,setVariantId]=useState('');
  const [variantAfter,setVariantAfter]=useState<number|null>(null);
  const [loading,setLoading]=useState(false);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState('');
  const [loaded,setLoaded]=useState(false);
  const maker=makers.find(v=>v.kind+':'+v.manufacturer_id===makerKey);
  useEffect(()=>{
    let live=true;
    setMakers([]);setMakerKey('');setModels([]);setModelId('');setVariants([]);setVariantId('');
    setModelAfter(null);setVariantAfter(null);setError('');setLoaded(false);
    if(!manufacturer.trim())return;
    setLoading(true);
    api<Makers>('/vehicles/vin/source-manufacturers?manufacturer='+encodeURIComponent(manufacturer.trim()))
      .then(response=>{if(!live)return;setMakers(response.items);if(response.items.length===1)
        setMakerKey(response.items[0].kind+':'+response.items[0].manufacturer_id);setLoaded(true)})
      .catch(e=>{if(live){setError((e as Error).message);setLoaded(true)}})
      .finally(()=>{if(live)setLoading(false)});
    return()=>{live=false};
  },[manufacturer]);
  useEffect(()=>{
    let live=true;
    setModels([]);setModelId('');setModelAfter(null);
    setVariants([]);setVariantId('');setVariantAfter(null);
    if(!maker)return;
    setLoading(true);setError('');
    api<Page>('/vehicles/vin/source-models?manufacturer_id='+maker.manufacturer_id+'&kind='+maker.kind)
      .then(v=>{if(live){setModels(v.items);setModelAfter(v.next_after)}})
      .catch(e=>{if(live)setError((e as Error).message)})
      .finally(()=>{if(live)setLoading(false)});
    return()=>{live=false};
  },[makerKey]);
  useEffect(()=>{
    let live=true;
    setVariants([]);setVariantId('');setVariantAfter(null);
    if(!maker||!modelId)return;
    setLoading(true);setError('');
    api<Page>('/vehicles/vin/source-modifications?model_id='+modelId+'&kind='+maker.kind)
      .then(v=>{if(live){setVariants(v.items);setVariantAfter(v.next_after)}})
      .catch(e=>{if(live)setError((e as Error).message)})
      .finally(()=>{if(live)setLoading(false)});
    return()=>{live=false};
  },[modelId,makerKey]);
  async function more(section:'models'|'modifications'){
    if(!maker||working)return;
    const after=section==='models'?modelAfter:variantAfter;
    if(after===null)return;
    setWorking(true);setError('');
    try{
      const path=section==='models'?
        '/vehicles/vin/source-models?manufacturer_id='+maker.manufacturer_id:
        '/vehicles/vin/source-modifications?model_id='+modelId;
      const page=await api<Page>(path+'&kind='+maker.kind+'&after='+after);
      if(section==='models'){setModels(p=>[...p,...page.items]);setModelAfter(page.next_after)}
      else{setVariants(p=>[...p,...page.items]);setVariantAfter(page.next_after)}
    }catch(e){setError((e as Error).message)}
    finally{setWorking(false)}
  }
  const chosenModel=models.find(m=>String(m.id)===modelId);
  const chosenVariant=variants.find(m=>String(m.id)===variantId);
  const canConfirm=!!maker&&!!chosenModel&&!!chosenVariant&&!loading&&!working;
  return <div className="vin-source-picker">
    <p><strong>Каталог моделей і модифікацій</strong></p>
    <p>У підготовленому каталозі запчастин ця марка поки відсутня. Нижче — окремий довідник автомобілів. Він дозволяє уточнити модифікацію, але не підтверджує сумісність запчастин за VIN.</p>
    {(loading||working)&&<small role="status">Завантаження варіантів…</small>}
    {loaded&&!makers.length&&!error&&<p role="status">Виробника немає у доступному джерелі. Можна додати автомобіль вручну.</p>}
    {makers.length>0&&<label>Тип автомобіля
      <select value={makerKey} disabled={loading||working} onChange={e=>{onSelect(null);setMakerKey(e.target.value)}}>
        <option value="">Оберіть тип транспорту</option>
        {makers.map(v=><option key={v.kind+':'+v.manufacturer_id} value={v.kind+':'+v.manufacturer_id}>{v.kind==='commercial'?'Вантажні та комерційні':'Легкові'} — {v.manufacturer}</option>)}
      </select>
    </label>}
    {maker&&<label>Модель із довідника
      <select value={modelId} disabled={loading||working||!models.length} onChange={e=>{onSelect(null);setModelId(e.target.value)}}>
        <option value="">Оберіть модель</option>
        {models.map(v=><option value={v.id} key={v.id}>{v.name} {v.construction_interval?'· '+v.construction_interval:''}</option>)}
      </select>
    </label>}
    {maker&&modelAfter!==null&&<button type="button" disabled={loading||working} onClick={()=>void more('models')}>Показати інші моделі</button>}
    {maker&&chosenModel&&<label>Модифікація
      <select value={variantId} disabled={loading||working||!variants.length} onChange={e=>{onSelect(null);setVariantId(e.target.value)}}>
        <option value="">Оберіть конкретну модифікацію</option>
        {variants.map(v=><option key={v.id} value={v.id}>{v.name} {v.construction_interval?'· '+v.construction_interval:''}</option>)}
      </select>
    </label>}
    {maker&&chosenModel&&variantAfter!==null&&<button type="button" disabled={loading||working} onClick={()=>void more('modifications')}>Показати інші модифікації</button>}
    {maker&&chosenModel&&!variants.length&&!loading&&!error&&<small>У довіднику немає модифікацій для цієї моделі.</small>}
    {canConfirm&&<button type="button" onClick={()=>onSelect({
      source_modification_id:chosenVariant!.id,model_id:chosenModel!.id,
      manufacturer_id:maker!.manufacturer_id,kind:maker!.kind,
      model:chosenModel!.name,modification:chosenVariant!.name,
      construction_interval:chosenVariant!.construction_interval
    })}>Підтвердити модифікацію автомобіля</button>}
    {selected&&<p role="status" className="vin-catalogue-confirmed">Обрано: {selected.model} — {selected.modification}. Каталожні дані про запчастини потребують окремого підтвердження.</p>}
    {error&&<p role="alert">Довідник недоступний: {error}. Можна продовжити з базовим каталогом.</p>}
  </div>;
}
