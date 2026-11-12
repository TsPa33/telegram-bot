/** CarPot constructive reference for resaleable assemblies.
 * These are OPTIONAL generic physical components, not VIN fitment or a factory BOM.
 * Rendering a template must never create Part, DismantlingItem or AssemblyMembership.
 * One root Part remains one stock unit until an explicit recorded physical dismantling.
 */
export type AssemblyUnitNode={
 id?:string;name?:string;position?:string|null;
 parent_id?:string|null;plan_parent_id?:string|null;
 part_id?:string|null;consumed_operation_id?:string|null;archived?:boolean;
};
export type UnitSpec={id:string;title:string;root:RegExp;parts:readonly string[]};
const UNIT_CATALOG:readonly UnitSpec[]=[
 {id:'doors',title:'Компоненти дверей',root:/^двері$/iu,
  parts:['Каркас дверей','Скло дверей','Склопідіймач','Замок дверей','Зовнішня ручка дверей','Внутрішня ручка дверей','Обшивка дверей','Проводка дверей','Ущільнювач дверей']},
 {id:'tailgate',title:'Склад дверей багажника',root:/^(?:кришка багажника(?:\s*\/\s*двері багажного відділення)?|двері багажника|двері багажного відділення)$/iu,
  parts:['Каркас кришки багажника','Скло багажника','Замок багажника','Привід замка','Обшивка кришки багажника','Проводка кришки багажника','Механізм відкривання']},
 {id:'hood',title:'Склад капота',root:/^капот$/iu,
  parts:['Панель капота','Замок капота','Трос відкривання капота','Утеплювач капота','Петлі капота','Газові упори капота']},
 {id:'bumper',title:'Склад бампера',root:/^бампер$/iu,
  parts:['Облицювання бампера','Підсилювач бампера','Поглинач енергії','Решітка бампера','Кронштейни кріплення','Датчики паркування','Протитуманні фари']},
 {id:'mirror',title:'Склад зовнішнього дзеркала',root:/^(?:зовнішнє дзеркало|дзеркало заднього виду зовнішнє)$/iu,
  parts:['Корпус дзеркала','Дзеркальний елемент','Механізм регулювання','Електропривід складання','Повторювач повороту','Підігрів дзеркала','Проводка дзеркала']},
 {id:'headlamp',title:'Склад фари',root:/^(?:фара|передня фара)$/iu,
  parts:['Корпус фари','Скло / лінза фари','Світловий модуль','Блок керування фарою','Механізм коректора','Кріплення фари']},
 {id:'taillight',title:'Склад заднього ліхтаря',root:/^(?:задній ліхтар|ліхтар задній)$/iu,
  parts:['Корпус ліхтаря','Розсіювач','Світловий модуль','Плата / патрон ламп','Ущільнювач ліхтаря','Роз’єм проводки']},
 {id:'engine',title:'Склад двигуна',root:/^(?:двигун|двигун у зборі)$/iu,
  parts:['Блок циліндрів','Головка блока циліндрів','Піддон двигуна','Клапанна кришка','Колінчастий вал','Розподільний вал','Привід ГРМ','Навісні агрегати']},
 {id:'gearbox',title:'Склад коробки передач',root:/^(?:коробка передач|кпп|акпп|мкпп)$/iu,
  parts:['Корпус коробки передач','Вхідний вал','Вихідний вал','Зубчасті передачі','Механізм перемикання','Мехатронік / гідроблок','Датчики коробки передач']},
 {id:'transfer',title:'Склад роздавальної коробки',root:/^роздавальна коробка$/iu,
  parts:['Корпус роздавальної коробки','Вхідний вал','Вихідні вали','Передавальний механізм','Муфта підключення приводу','Привід перемикання']},
 {id:'differential',title:'Склад диференціала',root:/^диференціал$/iu,
  parts:['Корпус диференціала','Головна пара','Сателіти','Півосьові шестерні','Підшипники','Механізм блокування']},
 {id:'starter',title:'Склад стартера',root:/^стартер$/iu,
  parts:['Корпус стартера','Електродвигун','Втягувальне реле','Бендикс','Щіткотримач','Редуктор']},
 {id:'alternator',title:'Склад генератора',root:/^генератор$/iu,
  parts:['Корпус генератора','Ротор','Статор','Регулятор напруги','Діодний міст','Шків генератора']},
 {id:'ac-compressor',title:'Склад компресора кондиціонера',root:/^компресор кондиціонера$/iu,
  parts:['Корпус компресора','Компресорний механізм','Шків','Муфта компресора','Регулювальний клапан','Ущільнення']},
 {id:'turbo',title:'Склад турбокомпресора',root:/^турбокомпресор$/iu,
  parts:['Корпус турбіни','Корпус компресора','Картридж / вал','Геометрія турбіни','Актуатор','Масляні з’єднання']},
 {id:'cooling',title:'Склад радіатора',root:/^радіатор охолодження$/iu,
  parts:['Серцевина радіатора','Бачки радіатора','Патрубки','Кронштейни радіатора','Датчик температури','Вентилятор / кожух']},
 {id:'steering-rack',title:'Склад кермової рейки',root:/^кермова рейка$/iu,
  parts:['Корпус рейки','Зубчаста рейка','Вхідний вал','Пильовики','Внутрішні тяги','Електропідсилювач / гідравлічний вузол']},
 {id:'steering-column',title:'Склад кермової колонки',root:/^кермова колонка$/iu,
  parts:['Вал кермової колонки','Корпус колонки','Механізм регулювання','Замок кермової колонки','Проміжний вал','Датчик кута повороту']},
 {id:'caliper',title:'Склад гальмівного супорта',root:/^гальмівний супорт$/iu,
  parts:['Корпус супорта','Поршень супорта','Скоба супорта','Напрямні','Пильовики й ущільнення','Електропривід стоянкового гальма']},
 {id:'seat',title:'Склад сидіння',root:/^сидіння$/iu,
  parts:['Каркас сидіння','Подушка сидіння','Спинка сидіння','Обшивка сидіння','Напрямні / салазки','Механізм регулювання','Підігрів / електропривід']},
 {id:'dashboard',title:'Склад панелі приладів',root:/^(?:панель приладів|торпедо)$/iu,
  parts:['Корпус панелі','Декоративні накладки','Повітроводи','Бардачок','Кріплення панелі','Джгут проводки','Блоки керування / індикації']},
 {id:'subframe',title:'Склад підрамника',root:/^підрамник$/iu,
  parts:['Каркас підрамника','Опори / сайлентблоки','Кронштейни','Кріплення агрегатів','Траверси']},
 {id:'fuel-tank',title:'Склад паливного бака',root:/^паливний бак$/iu,
  parts:['Корпус бака','Модуль паливного насоса','Датчик рівня пального','Клапан вентиляції','Паливні магістралі','Кріплення бака']},
 {id:'ev-motor',title:'Склад тягового електродвигуна',root:/^тяговий електродвигун$/iu,
  parts:['Корпус електродвигуна','Ротор','Статор','Датчики положення','Система охолодження','Редуктор приводу']},
] as const;

export function allAssemblyUnits():readonly UnitSpec[]{return UNIT_CATALOG;}
export function assemblyUnitFor(node:AssemblyUnitNode):UnitSpec|null{
 const name=(node.name||'').trim().replace(/\s+(?:у|в)\s+зборі$/iu,'').trim();
 return UNIT_CATALOG.find(unit=>unit.root.test(name))||null;
}

export type AssemblyReferenceLine={
 key:string;label:string;kind:'attached'|'existing_plan'|'reference';
 linkedId?:string;
};
/** This is a reference projection, never a source of stock or physical completeness. */
export function assemblyReferenceLines<T extends AssemblyUnitNode>(root:T,all:T[],attached:T[]):AssemblyReferenceLine[]{
 const unit=assemblyUnitFor(root);
 if(!unit)return [];
 const prior=all.filter(item=>item.id!==root.id&&!item.parent_id&&item.plan_parent_id===root.id
  &&!item.consumed_operation_id&&!item.archived);
 return unit.parts.map((label,i)=>{
  const physical=attached.find(node=>(node.name||'').trim().toLocaleLowerCase('uk')===label.toLocaleLowerCase('uk'));
  if(physical)return {key:unit.id+':'+i,label,kind:'attached' as const,linkedId:physical.id};
  const planned=prior.find(node=>(node.name||'').trim().toLocaleLowerCase('uk')===label.toLocaleLowerCase('uk'));
  if(planned)return {key:unit.id+':'+i,label,kind:'existing_plan' as const,linkedId:planned.id};
  return {key:unit.id+':'+i,label,kind:'reference' as const};
 });
}
