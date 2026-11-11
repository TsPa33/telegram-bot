/** Read-only, evidence-bound labels. A display group never creates a Part, membership or stock operation. */
export type PositionAxes={side:'left'|'right'|null;position:'front'|'rear'|null};
export type AssemblyDisplayNode={
 id?:string;name?:string;position?:string|null;
 installation_position?:{side?:string;position?:string}|null;
 completeness?:string|null;parent_id?:string|null;part_id?:string|null;
 consumed_operation_id?:string|null;archived?:boolean;
};
function uniqueAxis(text:string,left:RegExp,right:RegExp):'left'|'right'|null{
 const l=left.test(text),r=right.test(text);
 return l&&!r?'left':r&&!l?'right':null;
}
function uniqueEnd(text:string,front:RegExp,rear:RegExp):'front'|'rear'|null{
 const f=front.test(text),r=rear.test(text);
 return f&&!r?'front':r&&!f?'rear':null;
}
export function installationAxes(node:AssemblyDisplayNode):PositionAxes{
 const placement=node.installation_position;
 const storedSide=placement?.side==='left'||placement?.side==='right'?placement.side:null;
 const storedPosition=placement?.position==='front'||placement?.position==='rear'?placement.position:null;
 const text=(node.position||'').toLocaleLowerCase('uk');
 const textSide=uniqueAxis(text,/лів[а-яіїєґ]*|left/iu,/прав[а-яіїєґ]*|right/iu);
 const textPosition=uniqueEnd(text,/передн[а-яіїєґ]*|front/iu,/задн[а-яіїєґ]*|rear/iu);
 // Conflicting source fields are not resolved by guessing. Require manual review.
 return {side:storedSide&&textSide&&storedSide!==textSide?null:storedSide||textSide,
         position:storedPosition&&textPosition&&storedPosition!==textPosition?null:storedPosition||textPosition};
}
export function isGenericDoor(node:AssemblyDisplayNode):boolean{
 return /^двері$/iu.test((node.name||'').trim());
}
export function doorKey(node:AssemblyDisplayNode):string|null{
 if(!isGenericDoor(node))return null;
 const {side,position}=installationAxes(node);
 return side&&position?position+':'+side:null;
}
export function assemblyLabel(node:AssemblyDisplayNode):string{
 if(!isGenericDoor(node))return node.name||'';
 const {side,position}=installationAxes(node);
 const leading=position==='front'?'Передні':position==='rear'?'Задні':'';
 const trailing=side==='left'?'ліві':side==='right'?'праві':'';
 const title=[leading,'двері',trailing].filter(Boolean).join(' ');
 const complete=node.completeness==='complete';
 const suffix=complete?' в зборі':!side||!position?' · уточнити розташування':'';
 return title.charAt(0).toUpperCase()+title.slice(1)+suffix;
}
export function doorOrder(node:AssemblyDisplayNode):number{
 const axis=installationAxes(node);
 return (axis.position==='front'?0:axis.position==='rear'?2:4)+(axis.side==='left'?0:axis.side==='right'?1:2);
}
/** Components are shown as suggestions only when the car's stored placement identifies both axes. */
export function isKnownDoorComponent(node:AssemblyDisplayNode):boolean{
 return /(?:каркас|скло|склопідіймач|замок|ручк|обшивк|молдинг|ущільнювач|петл|проводк|динамік|механізм)/iu.test(node.name||'')
  && /(?:двер|склопідіймач|каркас двер|скло двер|обшивк двер)/iu.test(node.name||'');
}
export function sameDoorInstallation(parent:AssemblyDisplayNode,component:AssemblyDisplayNode):boolean{
 const p=installationAxes(parent),c=installationAxes(component);
 return !!p.side&&!!p.position&&p.side===c.side&&p.position===c.position;
}
/** Manual review may include a component with unknown location, never a confirmed mismatch. */
export function manuallyReviewableDoorComponent(parent:AssemblyDisplayNode,component:AssemblyDisplayNode):boolean{
 if(!isKnownDoorComponent(component))return false;
 const p=installationAxes(parent),c=installationAxes(component);
 if(p.side&&c.side&&p.side!==c.side)return false;
 if(p.position&&c.position&&p.position!==c.position)return false;
 return !sameDoorInstallation(parent,component);
}

/**
 * Suggestions are separate, existing plan positions — NOT membership edges.
 * Never use this list to infer stock, completeness, fitment or a physical assembly.
 */
export function suggestedDoorComponents<T extends AssemblyDisplayNode>(parent:T, rows:T[]):T[]{
 const key=doorKey(parent);
 if(!key)return [];
 return rows.filter(row=>row.id!==parent.id&&!row.parent_id&&!row.consumed_operation_id&&!row.archived
  &&isKnownDoorComponent(row)&&sameDoorInstallation(parent,row))
 .sort((a,b)=>(a.name||'').localeCompare(b.name||'','uk')||String(a.id||'').localeCompare(String(b.id||'')));
}


/**
 * A constructive REFERENCE template, not inventory or a factory BOM.
 * Render only for an identifiable door position. No generated row has a stock/plan ID.
 * Fitment and physical presence must be confirmed before any business operation.
 */
const DOOR_COMPONENT_TEMPLATE = [
 {key:'shell',label:'Каркас дверей',pattern:/каркас.*двер|двер.*каркас|панель.*двер.*метал/iu},
 {key:'glass',label:'Скло дверей',pattern:/скло.*двер|двер.*скло|віконн.*скло/iu},
 {key:'regulator',label:'Склопідіймач',pattern:/склопідіймач|механізм.*підйом.*скл/iu},
 {key:'lock',label:'Замок дверей',pattern:/замок.*двер|двер.*замок|защіпк.*двер/iu},
 {key:'outer-handle',label:'Зовнішня ручка дверей',pattern:/зовнішн.*ручк.*двер|ручк.*двер.*зовнішн/iu},
 {key:'inner-handle',label:'Внутрішня ручка дверей',pattern:/внутрішн.*ручк.*двер|ручк.*двер.*внутрішн/iu},
 {key:'trim',label:'Обшивка дверей',pattern:/обшивк.*двер|карт.*двер/iu},
 {key:'harness',label:'Проводка дверей',pattern:/проводк.*двер|джгут.*двер/iu},
 {key:'seal',label:'Ущільнювач дверей',pattern:/ущільнювач.*двер|двер.*ущільнювач/iu},
] as const;

export type DoorTemplateEntry = {
 key:string;
 label:string;
 kind:'physically_attached'|'source_candidate'|'template_only';
 linkedId?:string;
};
/** Display interpretation only; never insert templates into DismantlingItem, Part or AssemblyMembership. */
export function doorTemplateEntries<T extends AssemblyDisplayNode>(
 door:T,
 all:T[],
 attached:T[],
):DoorTemplateEntry[]{
 if(!doorKey(door))return [];
 const source=suggestedDoorComponents(door,all);
 return DOOR_COMPONENT_TEMPLATE.map(spec=>{
  const physical=attached.find(item=>spec.pattern.test(item.name||''));
  if(physical)return {key:spec.key,label:spec.label,kind:'physically_attached' as const,linkedId:physical.id};
  const candidate=source.find(item=>spec.pattern.test(item.name||''));
  if(candidate)return {key:spec.key,label:spec.label,kind:'source_candidate' as const,linkedId:candidate.id};
  return {key:spec.key,label:spec.label,kind:'template_only' as const};
 });
}
