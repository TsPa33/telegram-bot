import type {Row} from './api';
export function allowed(user:Row|null,permission:string):boolean {
 return !!user&&(user.role==='DIRECTOR'||(['ADMIN','MANAGER'].includes(user.role)&&Array.isArray(user.permissions)&&user.permissions.includes(permission)));
}
export const roleLabel=(role:string)=>({DIRECTOR:'Директор',ADMIN:'Адміністратор',MANAGER:'Менеджер'}[role]||'Невідома роль');
// Changes invalidate protected React screens and their cached server responses.
export function identityKey(user:Row|null):string {
 return user?JSON.stringify([user.id,user.workspace_account_id,user.role,user.must_change_password,
  Array.isArray(user.permissions)?[...new Set(user.permissions)].sort():[]]):'anonymous';
}

export const ADVANCED_PERMISSIONS=['vehicles.view','catalog.view','inventory.view','inventory.create','inventory.edit','inventory.archive','inventory.adjust_quantity','inventory.transfer','inventory.reserve','inventory.write_off','parts.view_cost','parts.change_price','parts.notes','parts.inspect'];
