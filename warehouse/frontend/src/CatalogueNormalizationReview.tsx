import {useState} from 'react';
import {Download,FileSearch,RefreshCw,ShieldAlert} from 'lucide-react';
import {api} from './api';
import {State,useLoad} from './shared';
import './catalogue-normalization-r14.css';

type Member={id:string;source:string;archived:boolean;linked_stock:number;child_nodes:number};
type Duplicate={workspace:string;kind:string;parent:string;parent_id:string;target:string;count:number;risk:string;linked_stock:number;child_nodes:number;sources:string[];members:Member[];action:string};
type GroupResponse={total:number;items:Duplicate[];risk_counts:Record<string,number>;base_groups:number};
type Proposal={type:'translation'|'hierarchy';source:string;target:string;approval:string;reason:string};
type ProposalResponse={total:number;status:string;items:Proposal[];version:string};
const riskLabels:Record<string,string>={linked_stock:'Є складські зв’язки',has_children:'Є дочірні вузли',cross_source:'Різні джерела',unreferenced_candidate:'Без прямих посилань'};
const categoryKinds:Record<string,string>={category:'Категорія',subcategory:'Підкатегорія',part:'Тип деталі'};
const n=(v:number)=>Number(v||0).toLocaleString('uk-UA');

function Group({group,index}:{group:Duplicate;index:number}){
 return <details className="r14-group">
  <summary>
   <span className="r14-group-number">{index}</span>
   <span className="r14-group-title"><strong>{group.target}</strong><small>{categoryKinds[group.kind]||group.kind}{group.parent?' · '+group.parent:''} · {group.sources.join(' / ')}</small></span>
   <span className="r14-group-figures">{group.count} ID · {n(group.linked_stock)} зв’язків</span>
   <span className="r14-risk">{riskLabels[group.risk]||group.risk}</span>
  </summary>
  <p className="r14-group-context">Робочий простір: <code>{group.workspace}</code>. Дочірніх вузлів: {n(group.child_nodes)}. Збіг назви — не дозвіл на об’єднання.</p>
  <div className="table-wrap"><table><thead><tr><th>Первинний ID</th><th>Джерело</th><th>Зв’язки зі складом</th><th>Дочірні вузли</th><th>Стан</th></tr></thead>
   <tbody>{group.members.map(m=><tr key={m.id}><td><code>{m.id}</code></td><td>{m.source}</td><td>{n(m.linked_stock)}</td><td>{n(m.child_nodes)}</td><td>{m.archived?'Архів':'Активний'}</td></tr>)}</tbody>
  </table></div>
 </details>;
}

export default function CatalogueNormalizationReview(){
 const [view,setView]=useState<'duplicates'|'proposals'>('duplicates');
 const [draft,setDraft]=useState(''),[q,setQ]=useState(''),[risk,setRisk]=useState(''),[page,setPage]=useState(0);
 const [proposalType,setProposalType]=useState('all'),[proposalSearch,setProposalSearch]=useState('');
 const pageSize=15;
 const groups=useLoad<GroupResponse>(
  ()=>view==='duplicates'
   ? api<GroupResponse>('/catalogue/admin/audit/duplicate-groups?offset='+page*pageSize+'&limit='+pageSize+'&risk='+risk+'&q='+encodeURIComponent(q))
   : Promise.resolve({items:[],total:0,risk_counts:{},base_groups:0}),
  [view,page,risk,q]);
 const proposals=useLoad<ProposalResponse>(
  ()=>view==='proposals'
   ?api<ProposalResponse>('/catalogue/admin/audit/name-proposals')
   :Promise.resolve({total:0,items:[],status:'',version:''}),
  [view]);
 const list=(proposals.data?.items||[]).filter(p=>
  (proposalType==='all'||p.type===proposalType)&&
  (p.source+' '+p.target).toLocaleLowerCase('uk').includes(proposalSearch.trim().toLocaleLowerCase('uk')));
 const totalPages=Math.ceil((groups.data?.total||0)/pageSize);
 return <div className="r14-review">
  <section className="r14-intro">
   <div><h2>Нормалізація каталогу</h2><p>Перевірка повторів та українських назв без зміни первинних записів і складських прив’язок.</p></div>
   <span className="r14-readonly"><ShieldAlert size={15}/> Лише перегляд</span>
  </section>
  <div className="r14-review-tabs" role="group" aria-label="Вид перевірки">
   <button type="button" aria-pressed={view==='duplicates'} onClick={()=>setView('duplicates')}>Дублікати й залежності</button>
   <button type="button" aria-pressed={view==='proposals'} onClick={()=>setView('proposals')}>Українські назви</button>
  </div>
  {view==='duplicates'?<>
   <div className="r14-toolbar">
    <form onSubmit={event=>{event.preventDefault();setQ(draft.trim());setPage(0);}}>
     <label>Пошук назви / батьківського вузла<input value={draft} maxLength={100} placeholder="Наприклад, фара" onChange={e=>setDraft(e.target.value)}/></label>
     <button type="submit">Знайти</button>
    </form>
    <label>Ризик<select value={risk} onChange={e=>{setRisk(e.target.value);setPage(0);}}>
     <option value="">Усі групи</option>{Object.entries(riskLabels).map(([k,label])=><option key={k} value={k}>{label}</option>)}
    </select></label>
    <button type="button" className="secondary" onClick={groups.reload} disabled={groups.loading}><RefreshCw size={15}/>Оновити</button>
   </div>
   <State error={groups.error} loading={groups.loading}/>
   {!groups.loading&&!groups.error&&groups.data&&<>
    <div className="r14-overview">
     <span><strong>{n(groups.data.base_groups)}</strong><small>Груп у довіднику</small></span>
     <span><strong>{n(groups.data.risk_counts.linked_stock||0)}</strong><small>Зі складськими зв’язками</small></span>
     <span><strong>{n(groups.data.total)}</strong><small>За обраним фільтром</small></span>
    </div>
    <p className="r14-explanation">Збіги обчислені за назвою, рівнем, робочим простором і конкретним батьківським ID. Число зв’язків — посилання на категорії, а не фізичні одиниці.</p>
    <div className="r14-groups">{groups.data.items.map((g,i)=><Group key={g.workspace+':'+g.parent_id+':'+g.kind+':'+g.target} group={g} index={page*pageSize+i+1}/>)}</div>
    {!groups.data.items.length&&<p className="r14-empty">За цим фільтром груп не знайдено.</p>}
    {totalPages>1&&<div className="r14-pagination">
     <button type="button" disabled={page===0} onClick={()=>setPage(p=>Math.max(0,p-1))}>Попередня</button>
     <span>Сторінка {page+1} із {totalPages}</span>
     <button type="button" disabled={page+1>=totalPages} onClick={()=>setPage(p=>p+1)}>Наступна</button>
    </div>}
   </>}
   <div className="r14-downloads">
    <a href="/api/v1/catalogue/admin/audit/duplicate-review.csv"><Download size={15}/> Усі ID і зв’язки (CSV)</a>
    <a href="/api/v1/catalogue/admin/audit/catalogue-mapping.csv"><Download size={15}/> Повна таблиця назв (CSV)</a>
   </div>
  </>:<>
   <div className="r14-toolbar">
    <label>Тип пропозиції<select value={proposalType} onChange={e=>setProposalType(e.target.value)}>
     <option value="all">Усі пропозиції</option><option value="translation">Переклад назви</option><option value="hierarchy">Структура категорій</option>
    </select></label>
    <label className="r14-grow">Пошук за старою / новою назвою<input value={proposalSearch} onChange={e=>setProposalSearch(e.target.value)} placeholder="Пошук відповідника"/></label>
    <button type="button" className="secondary" onClick={proposals.reload} disabled={proposals.loading}><RefreshCw size={15}/>Оновити</button>
   </div>
   <State error={proposals.error} loading={proposals.loading}/>
   {!proposals.loading&&!proposals.error&&proposals.data&&<>
    <p className="r14-explanation"><FileSearch size={16}/> {n(proposals.data.total)} пропозиції в словнику. Усі очікують затвердження; зміна структури не означає тотожності типів деталей.</p>
    <div className="table-wrap r14-proposals"><table>
     <thead><tr><th>Тип</th><th>Поточна назва</th><th>Запропонована назва</th><th>Стан</th></tr></thead>
     <tbody>{list.map((p,i)=><tr key={p.type+':'+p.source+':'+i}>
      <td>{p.type==='hierarchy'?'Ієрархія':'Переклад'}</td><td>{p.source}</td><td><strong>{p.target}</strong></td><td><span className="r14-pending">На перевірці</span></td>
     </tr>)}</tbody>
    </table></div>
    {!list.length&&<p className="r14-empty">Для цього фільтра немає відповідників.</p>}
    <p className="r14-explanation">Затвердження не виконувалося: це попередній перегляд перед окремим контрольованим застосуванням.</p>
    <div className="r14-downloads"><a href="/api/v1/catalogue/admin/audit/catalogue-mapping.csv"><Download size={15}/> Відповідності з PostgreSQL (CSV)</a></div>
   </>}
  </>}
 </div>;
}
