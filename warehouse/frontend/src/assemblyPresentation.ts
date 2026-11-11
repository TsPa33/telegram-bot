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
